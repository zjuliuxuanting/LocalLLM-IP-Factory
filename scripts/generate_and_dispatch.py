#!/usr/bin/env python3
"""
阶段一+二：种子生成 + 信源缓存 + 卡片派发 (LLM增强版)

依赖: Crawl4AI (pip install crawl4ai, playwright install chromium)
运行: python3 scripts/generate_and_dispatch.py [--target 300] [--count 10]
"""
import argparse, asyncio, hashlib, json, re, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import LLMConfig

from src.models.gateway import call_xianka
from src.models.prompts.seed import build_seed_generation_prompt
from src.quality.seed_gate import inspect_seed
from src.io.store import AtomicJsonStore
from src.io.source_registry import SourceRecord, make_source_id
from src.utils.id_assigner import IdAssigner
from config.series_definitions import all_series_keys, get_series, get_source_policy
from config.settings import (
    PROXY, SEED_POOL_FILE, XIANKA_GATEWAY, XIANKA_MODEL,
    MAX_TOKENS, TEMPERATURE, path_to_rel, rel_to_abs,
)
from src.pipeline.series_expansion import run_expansion_check
from src.utils.logging import get_logger, ts_print, setup as setup_logging
from config.settings import LOGS_DIR

glog = get_logger("dispatch")

# ── 代理 opener：PubMed/arXiv/Wikipedia API 走代理 ──
import urllib.request as _ur
_proxy_handler = _ur.ProxyHandler({"http": PROXY, "https": PROXY}) if PROXY else _ur.ProxyHandler()
_ur.install_opener(_ur.build_opener(_proxy_handler))

SHARED = SCRIPT_DIR / "data" / "source_cache" / "shared"
REG_INDEX = SCRIPT_DIR / "data" / "source_registry" / "index.json"
CARDS_FILE = SCRIPT_DIR / "data" / "queue" / "cards.json"
SHARED.mkdir(parents=True, exist_ok=True)
REG_INDEX.parent.mkdir(parents=True, exist_ok=True)
CARDS_FILE.parent.mkdir(parents=True, exist_ok=True)

CHAPTER_COOLING_DAYS = 3
CHAPTER_COOLING_FILE = SCRIPT_DIR / "data" / "chapter_cooling.json"

EXCLUDE_DOMAINS = [
    "bing.com", "duckduckgo.com", "go.microsoft.com", "facebook.com",
    "twitter.com", "instagram.com", "youtube.com", "tiktok.com", "reddit.com",
]

SOURCE_WHITELIST = [
    ("pubmed.ncbi.nlm.nih.gov", "pubmed", 10, "PubMed"),
    ("ncbi.nlm.nih.gov", "pubmed", 9, "NCBI"),
    ("arxiv.org", "arxiv", 9, "arXiv"),
    ("export.arxiv.org", "arxiv", 9, "arXiv"),
    ("semanticscholar.org", "semantic", 8, "Semantic Scholar"),
    ("britannica.com", "britannica", 7, "大英百科"),
    ("patents.google.com", "patent", 7, "Google Patents"),
    ("baike.baidu.com", "baike", 6, "百度百科"),
    ("36kr.com", "research", 6, "36氪"),
    ("iresearch.cn", "research", 5, "艾瑞咨询"),
    ("iresearchchina.com", "research", 5, "艾瑞咨询"),
    ("nih.gov", "nih", 5, "NIH"),
    ("zhihu.com", "zhihu", 4, "知乎"),
    (".edu", "edu", 3, "教育机构"),
    (".gov", "gov", 3, "政府机构"),
    (".org", "org", 2, "组织"),
]

STOP_WORDS = frozenset({
    "the","and","for","with","how","are","has","was","its","can",
    "not","but","all","from","that","this","have","been","about",
    "more","than",
})

def _get_priority():
    return all_series_keys()

# LLM LLM 配置（供 Crawl4AI 的 LLM extraction strategy 使用）
# LLM API = OpenAI 兼容: {XIANKA_GATEWAY}/v1/chat/completions
XIANKA_LLM_CONFIG = LLMConfig(
    provider=f"openai/{XIANKA_MODEL}",
    api_token="",
    base_url=XIANKA_GATEWAY,
    temperature=0.3,
    max_tokens=1024,
)

store = AtomicJsonStore(SEED_POOL_FILE, {})
_crawler_instance = None


async def get_crawler():
    global _crawler_instance
    if _crawler_instance is None:
        _crawler_instance = AsyncWebCrawler(proxy=PROXY)
        await _crawler_instance.start()
    return _crawler_instance


async def close_crawler():
    global _crawler_instance
    if _crawler_instance:
        await _crawler_instance.close()
        _crawler_instance = None


def step0_series_expansion(pool: dict):
    result = run_expansion_check(pool, auto_generate=True)
    if result.get("proposal"):
        p = result["proposal"]
        ts_print(f"  🆕 新系列提案: {p['code']} {p['name']} (验证分 {p['validation']['score']}/10)")
    return pool


def step0b_recycle_dead(pool: dict, max_retries: int = 2):
    """回收 source_failed 种子：重置为 pending（给网络波动第二次机会）"""
    recycled = 0
    for key in list(pool.keys()):
        if not isinstance(pool[key], dict):
            continue
        seeds = pool[key].get("seeds", [])
        for s in seeds:
            if s.get("status") in ("source_failed",):
                retries = s.get("_recycles", 0)
                if retries < max_retries:
                    s["status"] = "pending"
                    s["_recycles"] = retries + 1
                    recycled += 1
    if recycled:
        store.write(pool)
        ts_print(f"  ♻️  回收 {recycled} 个 source_failed → pending (max_retries={max_retries})")


def step1_generate_seeds(pool: dict, target: int, engine_status=None):
    base_keys = all_series_keys()
    cooling = json.loads(CHAPTER_COOLING_FILE.read_text()) if CHAPTER_COOLING_FILE.exists() else {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for series_key in base_keys:
        # 确定当前最新章节的 pool key
        chapter_keys = sorted(k for k in pool if k.startswith(series_key) and (k == series_key or k[len(series_key):].isdigit()))
        if series_key in pool and chapter_keys and chapter_keys[-1] == series_key:
            # 旧版: 把 base key 下的种子迁移到 {series_key}1
            old_seeds = pool[series_key].get("seeds", [])
            if old_seeds:
                pool[f"{series_key}1"] = {
                    "topic": pool[series_key].get("topic", ""),
                    "style": pool[series_key].get("style", ""),
                    "forbidden": pool[series_key].get("forbidden", []),
                    "avg_chars": pool[series_key].get("avg_chars", 450),
                    "seeds": old_seeds,
                }
                chapter_keys = [f"{series_key}1"]
            pool[series_key]["seeds"] = []  # base key 不再存种子
        current_key = chapter_keys[-1] if chapter_keys else f"{series_key}1"
        data = pool.get(current_key) or pool.get(series_key)
        if not data:
            current_key = f"{series_key}1"
            pool[current_key] = {
                "topic": pool.get(series_key, {}).get("topic", ""),
                "style": pool.get(series_key, {}).get("style", ""),
                "forbidden": pool.get(series_key, {}).get("forbidden", []),
                "avg_chars": pool.get(series_key, {}).get("avg_chars", 450),
                "seeds": [],
            }
            data = pool[current_key]
        seeds = data.get("seeds", [])
        pending_count = sum(1 for s in seeds if s.get("status") == "pending")
        dead_count = sum(1 for s in seeds if s.get("status") in ("source_failed", "failed"))
        active_total = len(seeds) - dead_count
        per_series = target // len(base_keys)
        # 硬上限：active 种子 ≥ per_series 则不再补种（排除 source_failed）
        if active_total >= per_series:
            continue
        needed = min(per_series - active_total, 10)
        ts_print(f"  🌱 {current_key}: {active_total} active (dead={dead_count}, pending={pending_count}), 需补 {needed} 个")
        _generate_seeds_for(current_key, pool, needed, series_key, engine_status)
        # 首次生成种子记冷却（初始代 = 1 冷却）
        cooling_key = f"{series_key}ch"
        if cooling_key not in cooling:
            cooling[cooling_key] = today

    # ── 系列章节轮换：已耗尽且冷却 ≥3 天的 → 生成下一章种子 ──
    cooling = json.loads(CHAPTER_COOLING_FILE.read_text()) if CHAPTER_COOLING_FILE.exists() else {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for base_key in base_keys:
        if base_key not in pool:
            continue
        # 找该系列的最新章节
        chapter_keys = sorted(k for k in pool if k.startswith(base_key) and (k == base_key or k[len(base_key):].isdigit()))
        if not chapter_keys:
            continue
        latest = chapter_keys[-1]
        latest_seeds = pool[latest].get("seeds", [])
        remaining = sum(1 for s in latest_seeds if s.get("status") == "pending")
        if remaining > 0:
            continue  # 还有 pending 种子，不轮换
        cooling_key = f"{base_key}ch"
        last_date = cooling.get(cooling_key, "")
        if last_date and last_date >= today:
            continue  # 冷却中
        next_ch = 1
        for ck in chapter_keys:
            num = ck[len(base_key):]
            if num.isdigit() and int(num) >= next_ch:
                next_ch = int(num) + 1
        new_key = f"{base_key}{next_ch}"
        ts_print(f"  🔄 {base_key} 种子耗尽 → 生成 {new_key} 种子")
        pool[new_key] = {
            "topic": pool[base_key].get("topic", ""),
            "style": pool[base_key].get("style", ""),
            "forbidden": pool[base_key].get("forbidden", []),
            "avg_chars": pool[base_key].get("avg_chars", 450),
            "seeds": [],
        }
        _generate_seeds_for(new_key, pool, max(1, target // len(base_keys) // 2), base_key, engine_status)
        cooling[cooling_key] = today
    CHAPTER_COOLING_FILE.write_text(json.dumps(cooling, indent=2))


def _generate_seeds_for(pool_key: str, pool: dict, needed: int, series_key: str, engine_status=None):
    """为指定 pool_key 生成种子"""
    data = pool[pool_key]
    seeds = data.get("seeds", [])
    s = get_series(series_key)
    if not s:
        return

    # 收集全系列种子（跨章节：B1/B2/B3...）用于覆盖度计算 + 标题去重
    from src.pipeline.seed_diversity import get_series_seeds, analyze_coverage
    from config.series_definitions import get_subtopics
    all_series_seeds = get_series_seeds(pool, series_key)
    existing_titles = [s.get("title", "") for s in all_series_seeds]
    coverage = analyze_coverage(series_key, all_series_seeds)
    subtopics = get_subtopics(series_key)
    covered = coverage.get("covered_topics", [])

    # 章节信息
    chapter_info = ""
    if pool_key != series_key and pool_key.startswith(series_key):
        ch_num = pool_key[len(series_key):]
        if ch_num.isdigit():
            chapter_info = f"第{ch_num}卷 · {pool_key}"

    prompt = build_seed_generation_prompt(
        series=series_key,
        topic=s.get("topic", ""),
        style=s.get("style", ""),
        existing_titles=existing_titles,
        needed=needed,
        subtopics=subtopics,
        covered_topics=covered,
        chapter_info=chapter_info,
        engine_status=engine_status,
    )
    raw = call_xianka(prompt, max_tokens=4096, temperature=0.8)
    if not raw:
        ts_print(f"    ⚠️ LLM调用失败，重试...")
        raw = call_xianka(prompt, max_tokens=4096, temperature=0.8)
    if not raw:
        ts_print(f"    ❌ LLM调用失败，跳过 {pool_key}")
        return
    m = re.search(r'\[[\s\S]*\]', raw)
    if not m:
        ts_print(f"    ⚠️ 返回无 JSON 数组，回退提取 JSON 对象...")
        m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        ts_print(f"    ❌ 无法从返回中提取任何 JSON，跳过 {pool_key}")
        return
    try:
        candidates = json.loads(m.group())
        if isinstance(candidates, dict):
            candidates = [candidates]
    except json.JSONDecodeError:
        ts_print(f"    ❌ JSON 解析失败，跳过 {pool_key}")
        return
    if not isinstance(candidates, list):
        ts_print(f"    ⚠️ 返回非数组 JSON，跳过")
        return
    accepted = 0
    for seed in candidates:
        if all(k in seed for k in ("title", "goal", "engine", "kw")):
            result = inspect_seed(seed, series_key, existing_titles, check_source=False)
            if result.passed:
                seed["status"] = "pending"
                seeds.append(seed)
                existing_titles.append(seed["title"])
                accepted += 1
    pool[pool_key]["seeds"] = seeds
    store.write(pool)
    ts_print(f"    ✅ +{accepted} 种子")


def url_to_source_id(url: str) -> str:
    domain = re.sub(r'^https?://(www\.)?', '', url).split('/')[0].replace('.', '_')
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"src_crawl_{domain}_{h}"


def is_valid_url(url: str) -> bool:
    if not url.startswith("http"):
        return False
    domain = re.sub(r'^https?://(www\.)?', '', url).split('/')[0].lower()
    for excluded in EXCLUDE_DOMAINS:
        if excluded in domain:
            return False
    if not domain or "." not in domain:
        return False
    return True


def classify_url(url: str) -> tuple[str, int, str]:
    """按白名单分类 URL

    Returns: (category: str, priority: int, label: str)
    """
    if url.startswith("local://"):
        return "local", 10, "本地信源"
    domain = re.sub(r'^https?://(www\.)?', '', url).split('/')[0].lower()
    for suffix, cat, pri, label in SOURCE_WHITELIST:
        if suffix.startswith("."):
            if domain.endswith(suffix):
                return cat, pri, label
        else:
            if domain == suffix or domain.endswith("." + suffix):
                return cat, pri, label
    return "other", 1, "其他"


def downgrade_kw(kw: str, level: int) -> str:
    """OR 降级关键词

    L0: 原样
    L2: 2-4 核心词 OR 连接
    L3: 最简 2 词 OR 连接
    """
    if level == 0:
        return kw
    words = [w for w in kw.split()
             if len(w) >= 3 and w.lower() not in STOP_WORDS]
    if level == 2:
        selected = words[:4]
    elif level >= 3:
        selected = words[:2]
    else:
        return kw
    return " OR ".join(selected) if selected else kw


import urllib.parse


from src.utils.engine_check import check_api_engines  # noqa: E402


async def check_connectivity(crawler) -> dict:
    """启动时检查各搜索引擎可达性 + LLM 验证结果质量

    先硬测试（HTTP 可达 + 内容长度），再软测试（LLM 判断是否真实搜索结果）。
    避免 DDG 返回图片页/验证码、百度返回空壳页骗过阈值。

    Returns: {ddg_ok, baidu_ok, local_count, has_fallback}
    """
    status = {"ddg_ok": False, "baidu_ok": False, "local_count": 0, "has_fallback": False}

    # 本地信源（永远可用）
    local_dir = SCRIPT_DIR / "data" / "source_cache" / "local"
    if local_dir.exists():
        status["local_count"] = len([f for f in local_dir.iterdir() if f.is_file() and f.suffix not in (".json", ".yml", ".yaml")])
    if REG_INDEX.exists():
        reg = json.loads(REG_INDEX.read_text())
        local_translated = [s for s in reg.values() if s.get("source_type") == "local_translated" and s.get("cache_path") and rel_to_abs(s["cache_path"]).exists()]
        if local_translated:
            status["local_count"] += len(local_translated)
    status["has_fallback"] = status["local_count"] > 0

    # DuckDuckGo（硬测试：抓到 >200 字就算通）
    ts_print("  ⏳ DuckDuckGo...")
    try:
        r = await crawler.arun("https://html.duckduckgo.com/html/?q=dog+communication", {"timeout": 15})
        if r and r.markdown and len(r.markdown) > 200:
            status["ddg_ok"] = True
            ts_print("    ✓")
        else:
            ts_print("    ✗ 硬测试失败（内容不足）")
    except Exception as e:
        ts_print(f"    ✗ {type(e).__name__}")

    # 百度（硬测试：抓到 >200 字就算通）
    ts_print("  ⏳ 百度...")
    try:
        r = await crawler.arun("https://www.baidu.com/s?wd=狗沟通按钮", {"timeout": 15})
        if r and r.markdown and len(r.markdown) > 200:
            status["baidu_ok"] = True
            ts_print("    ✓")
        else:
            ts_print("    ✗ 硬测试失败（内容不足）")
    except Exception as e:
        ts_print(f"    ✗ {type(e).__name__}")

    return status


async def search_web(crawler, kw: str, max_results=8) -> list[dict]:
    """用 DuckDuckGo 搜索，从 redirect URL 中提取真实链接"""
    search_url = f"https://html.duckduckgo.com/html/?q={kw.replace(' ', '+')}"
    r = await crawler.arun(search_url)
    if not r or not r.markdown:
        return []
    md = r.markdown
    # DuckDuckGo 的链接格式: https://duckduckgo.com/l/?uddg={URL_ENCODED_URL}&rut=...
    redirects = re.findall(r'https://duckduckgo\.com/l/\?uddg=([^&\s]+)', md)
    seen = set()
    hits = []
    for encoded in redirects:
        try:
            real_url = urllib.parse.unquote(encoded)
        except Exception:
            continue
        if not is_valid_url(real_url):
            continue
        if real_url in seen:
            continue
        seen.add(real_url)
        hits.append({"url": real_url, "title": "", "snippet": ""})
        if len(hits) >= max_results:
            break
    return hits


async def search_baidu(crawler, kw: str, max_results=5) -> list[dict]:
    search_url = f"https://www.baidu.com/s?wd={kw.replace(' ', '+')}"
    r = await crawler.arun(search_url)
    if not r or not r.markdown:
        return []
    md = r.markdown
    urls = re.findall(r'https?://[^\s)\"<>\'\[\]]+', md)
    seen = set()
    hits = []
    for u in urls:
        u = u.rstrip(".,;:)!?")
        if not is_valid_url(u):
            continue
        if u in seen:
            continue
        seen.add(u)
        hits.append({"url": u, "title": "", "snippet": ""})
        if len(hits) >= max_results:
            break
    return hits


async def search_pubmed(kw: str, max_results=8) -> list[dict]:
    """用 PubMed E-utilities API 搜索并直接获取摘要"""
    import urllib.request, urllib.parse
    query = urllib.parse.quote(kw)
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={query}&retmax={max_results}&retmode=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        ids = data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return []
        fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={','.join(ids)}&rettype=abstract&retmode=text"
        req2 = urllib.request.Request(fetch_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            abstracts = resp2.read().decode("utf-8")
        sections = re.split(r'\n\d+\.\s*\n', '\n' + abstracts)
        hits = []
        for i, pmid in enumerate(ids):
            abstract_text = sections[i+1].strip() if i+1 < len(sections) else ""
            if not abstract_text or len(abstract_text) < 100:
                abstract_text = f"PubMed article {pmid}"
            hits.append({
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "title": f"PubMed {pmid}",
                "snippet": "",
                "_raw_content": abstract_text,
            })
        return hits
    except Exception:
        return []


async def search_arxiv(kw: str, max_results=8) -> list[dict]:
    """用 arXiv API 搜索"""
    import urllib.request, urllib.parse
    query = urllib.parse.quote(kw)
    url = f"https://export.arxiv.org/api/query?search_query=all:{query}&max_results={max_results}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode("utf-8")
        hits = []
        for m in re.finditer(r'<entry>.*?<id>(.*?)</id>.*?<title>(.*?)</title>', data, re.DOTALL):
            url = m.group(1).strip()
            title = re.sub(r'\s+', ' ', m.group(2).strip())
            hits.append({"url": url, "title": title, "snippet": ""})
            if len(hits) >= max_results:
                break
        return hits
    except Exception:
        return []


async def search_patents(crawler, kw: str, max_results=6) -> list[dict]:
    """搜索 Google Patents + 拉取专利摘要（crawler 搜索 + urllib 取全文）"""
    import urllib.request, ssl
    hits = []
    # 1. crawler 搜索
    search_url = f"https://patents.google.com/?q={kw.replace(' ', '+')}&num={max_results}"
    try:
        r = await crawler.arun(search_url)
        if not r or not r.markdown:
            return []
        md = r.markdown
    except Exception:
        return []

    # 2. 提取专利 ID
    patent_ids = set(re.findall(r'([A-Z]{2}\d{6,12}[A-Z]?\d?)', md))
    if not patent_ids:
        return []

    # 3. urllib 取每个专利的摘要 + 权利要求
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    for pid in sorted(patent_ids)[:max_results]:
        try:
            req = urllib.request.Request(
                f"https://patents.google.com/patent/{pid}/en?output=plaintext",
                headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        if len(text) < 500:
            continue
        # 摘取摘要段落
        abs_match = re.search(r'(?:abstract|summary|technical field)[:\s]+(.+?)(?:\n\n|\n[A-Z])', text, re.I | re.DOTALL)
        abstract = abs_match.group(1).strip()[:2000] if abs_match else text[:2000]
        hits.append({
            "url": f"https://patents.google.com/patent/{pid}/en",
            "title": f"Patent {pid}",
            "snippet": abstract[:300],
            "_raw_content": abstract,
            "_is_prefetched": True,
        })
    return hits


async def search_wikipedia(kw: str, max_results=6) -> list[dict]:
    """用 Wikipedia API 搜索"""
    import urllib.request, urllib.parse
    query = urllib.parse.quote(kw)
    url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&format=json&srlimit={max_results}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        hits = []
        for r in data.get("query", {}).get("search", []):
            title = r.get("title", "")
            page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
            hits.append({"url": page_url, "title": title, "snippet": r.get("snippet", "")[:200]})
        return hits
    except Exception:
        return []


async def search_stackexchange(kw: str, max_results=6) -> list[dict]:
    """用 StackExchange Pets API 搜索宠物问答"""
    import urllib.request, urllib.parse
    query = urllib.parse.quote(kw)
    url = f"https://api.stackexchange.com/2.3/search?order=desc&sort=relevance&q={query}&pagesize={max_results}&site=pets"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        hits = []
        for item in data.get("items", []):
            title = item.get("title", "")
            link = item.get("link", "")
            snippet = item.get("body_markdown", "")[:300] if item.get("body_markdown") else ""
            hits.append({"url": link, "title": title, "snippet": snippet})
        return hits
    except Exception:
        return []


async def crawl_page(crawler, url: str) -> tuple[str, str]:
    r = await crawler.arun(url)
    if not r or not r.success:
        return "", ""
    md = (r.markdown or "").strip()
    title = ""
    if md:
        lines = md.split("\n")
        for line in lines[:5]:
            s = line.strip()
            if s.startswith("# ") or s.startswith("#"):
                title = s.lstrip("#").strip()
                break
        if not title and r.metadata:
            title = r.metadata.get("title", "")
    if len(md) < 200:
        return "", ""
    return title, md[:12000]


def llm_rank_sources(goal: str, sources: list[dict]) -> list[dict]:
    """用 LLM对抓取的原文按 goal 相关性排序 + 提取关键段落

    返回 [{"url": ..., "title": ..., "relevance": 0-10, "key_paragraphs": [...], "summary": ...}]
    """
    if not sources:
        return []

    src_text = ""
    for i, s in enumerate(sources):
        raw = s["raw_content"]
        # 跳过前 500 字（导航/菜单），取 3000 字正文
        body = raw[500:3500] if len(raw) > 500 else raw
        content_preview = body.replace("\n", " ")
        label = s.get("source_label", "")
        src_text += f"\n--- 信源 {i+1} [{label}]---\nURL: {s['url']}\n标题: {s.get('title','')}\n内容: {content_preview[:2500]}\n"

    prompt = f"""你是一个科研助手。你的任务是对搜索结果进行筛选和排序。

卡片写作目标: {goal}

以下是抓取到的 {len(sources)} 个信源。请做三件事：
1. 按与写作目标的相关性排序（10最相关，0完全不相关）
2. 从每个信源中提取 2-3 个最相关的关键段落（原文引用）
3. 用一句话概括每个信源的核心价值

只返回 JSON 数组，不要其他内容：
[
  {{
    "url": "...",
    "title": "...",
    "relevance": 8,
    "key_paragraphs": ["...", "..."],
    "summary": "..."
  }}
]

{src_text}"""

    raw = call_xianka(prompt, max_tokens=2048, temperature=0.3)
    if not raw:
        return sources

    m = re.search(r'\[[\s\S]*\]', raw)
    if not m:
        return sources

    try:
        ranked = json.loads(m.group())
    except json.JSONDecodeError:
        return sources

    ranked.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    return ranked


def llm_check_sufficiency(goal: str, sources: list[dict]) -> tuple[bool, str]:
    """检查信源是否足够支撑卡片写作

    Returns: (sufficient: bool, reason: str)
    """
    if len(sources) < 2:
        return False, "信源数量不足（<2）"

    src_text = ""
    for i, s in enumerate(sources):
        kp = s.get("key_paragraphs", [])
        kp_text = "\n".join(kp) if kp else s.get("raw_content", "")[:1500]
        src_text += f"\n--- 信源 {i+1} (相关度 {s.get('relevance', 5)}/10) ---\n{kp_text[:1500]}\n"

    prompt = f"""你是卡片内容审核员。卡片目标: {goal}

以下是已筛选的信源。判断这些信源是否足够写一篇 300-600 字的中文科普短文。

标准：
- 足够：关键事实覆盖 goal 的核心要点
- 不足：关键事实缺失，无法支撑 goal
- 如果不足，给出缺什么内容

只返回 JSON：
{{"sufficient": true/false, "reason": "...", "missing": "缺什么"}}

{src_text}"""

    raw = call_xianka(prompt, max_tokens=512, temperature=0.2)
    if not raw:
        return True, ""

    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return True, ""

    try:
        result = json.loads(m.group())
    except json.JSONDecodeError:
        return True, ""

    return result.get("sufficient", True), result.get("reason", "")


async def dispatch_one(crawler, seed: dict, series_key: str, pool: dict, net_status=None):
    kw = seed.get("kw", "")
    goal = seed.get("goal", "")
    title = seed.get("title", "")

    all_hits = []
    has_cn = bool(re.search(r'[\u4e00-\u9fff]', kw))

    # ═════ 本地信源优先检查（通过注册中心关键词匹配）═════
    if REG_INDEX.exists():
        reg = json.loads(REG_INDEX.read_text())
        kw_words = set(kw.lower().split())
        local_sources = [
            s for s in reg.values()
            if s.get("source_type") == "local_translated"
            and s.get("cache_path") and rel_to_abs(s["cache_path"]).exists()
        ]
        for src in local_sources:
            src_kws = set(k.lower() for k in src.get("keywords", []))
            matched_kws = kw_words & src_kws
            if not matched_kws:
                for src_kw in src_kws:
                    if any(w in src_kw or src_kw in w for w in kw_words):
                        matched_kws = {src_kw}
                        break
            if matched_kws:
                try:
                    content = rel_to_abs(src["cache_path"]).read_text(encoding="utf-8", errors="ignore")[:12000]
                except Exception:
                    continue
                if len(content) < 200:
                    continue
                all_hits.append({
                    "url": src.get("url", f"local://{src['title']}"),
                    "title": src.get("title", src["source_id"]),
                    "raw_content": content,
                    "source_category": "local",
                    "source_priority": 10,
                    "source_label": "本地信源",
                    "_is_local": True,
                })
                ts_print(f"    📁 本地信源匹配: {src.get('title', '')} (kw: {', '.join(matched_kws)})")
                if len(all_hits) >= 1:
                    break
    # ═════ 本地信源结束 ═════

    engine = seed.get("engine", "web")
    if net_status is None:
        net_status = {}

    # ── 引擎路由：按 seed.engine 选择搜索后端 ──
    if engine == "pubmed":
        ts_print(f"    🔬 PubMed 引擎")
        hits = await search_pubmed(kw)
        ts_print(f"    pubmed: {len(hits)} hits")
        for h in hits:
            h["_is_prefetched"] = True  # 已含摘要，跳过 crawl
        all_hits.extend(hits)
        # PubMed 不够 → web 兜底
        if len(all_hits) < 3:
            if net_status.get("baidu_ok", True):
                bhits = await search_baidu(crawler, kw)
                ts_print(f"    baidu(兜底): +{len(bhits)}")
                all_hits.extend(bhits)
    elif engine == "arxiv":
        ts_print(f"    📄 arXiv 引擎")
        hits = await search_arxiv(kw)
        ts_print(f"    arxiv: {len(hits)} hits")
        all_hits.extend(hits)
        if len(all_hits) < 3:
            if net_status.get("baidu_ok", True):
                bhits = await search_baidu(crawler, kw)
                ts_print(f"    baidu(兜底): +{len(bhits)}")
                all_hits.extend(bhits)
    elif engine == "patent":
        ts_print(f"    📜 Patent 引擎")
        hits = await search_patents(crawler, kw)
        ts_print(f"    patent: {len(hits)} hits")
        all_hits.extend(hits)
        if len(all_hits) < 3:
            if net_status.get("baidu_ok", True):
                bhits = await search_baidu(crawler, kw)
                ts_print(f"    baidu(兜底): +{len(bhits)}")
                all_hits.extend(bhits)
    elif has_cn:
        if net_status.get("baidu_ok", True):
            ts_print(f"    🌏 中文 kw，优先百度")
            for level in (0, 2, 3):
                search_kw = downgrade_kw(kw, level) if level > 0 else kw
                hits = await search_baidu(crawler, search_kw)
                label = f"L{level}" if level > 0 else "L0"
                ts_print(f"    baidu({label}): {len(hits)} hits")
                all_hits.extend(hits)
                if len(all_hits) >= 3:
                    break
        else:
            ts_print(f"    ⏭️ 百度不可达（预检），跳过")
        if len(all_hits) < 3:
            if net_status.get("ddg_ok", True):
                whits = await search_web(crawler, kw)
                existing_urls = {h["url"] for h in all_hits}
                for h in whits:
                    if h["url"] not in existing_urls:
                        all_hits.append(h)
                        existing_urls.add(h["url"])
                ts_print(f"    web: +{len(whits)}")
            else:
                ts_print(f"    ⏭️ DDG 不可达（预检），跳过")
    else:
        # 英文 kw + web 引擎：优先 Wikipedia API，其次百度
        whits = await search_wikipedia(kw)
        ts_print(f"    wiki: {len(whits)} hits")
        all_hits.extend(whits)
        if len(all_hits) < 3:
            if net_status.get("baidu_ok", True):
                bhits = await search_baidu(crawler, kw)
                existing_urls = {h["url"] for h in all_hits}
                for h in bhits:
                    if h["url"] not in existing_urls:
                        all_hits.append(h)
                        existing_urls.add(h["url"])
                ts_print(f"    baidu: +{len(bhits)}")
            else:
                ts_print(f"    ⏭️ 百度不可达（预检），跳过")

    if not all_hits:
        ts_print(f"    ❌ 0 信源")
        return None

    # 按白名单优先级排序（高优先级的先抓取）
    all_hits.sort(key=lambda h: classify_url(h["url"])[1], reverse=True)

    # 去重
    seen = set()
    deduped = []
    for h in all_hits:
        if h["url"] not in seen:
            seen.add(h["url"])
            deduped.append(h)
    all_hits = deduped

    raw_sources = []
    for hit in all_hits[:6]:
        if hit.get("_is_local"):
            raw_sources.append(hit)
            continue
        if hit.get("_is_prefetched"):
            # PubMed/arXiv 已含摘要，直接使用，跳过爬取
            if hit.get("_raw_content") and len(hit["_raw_content"]) >= 100:
                raw_sources.append({
                    "url": hit["url"],
                    "title": hit.get("title", hit["url"]),
                    "raw_content": hit["_raw_content"],
                    "source_category": engine,
                    "source_priority": 8,
                    "source_label": engine.upper(),
                })
            continue
        cat, pri, label = classify_url(hit["url"])
        page_title, content = await crawl_page(crawler, hit["url"])
        if not content:
            continue
        raw_sources.append({
            "url": hit["url"],
            "title": page_title or hit["url"],
            "raw_content": content,
            "source_category": cat,
            "source_priority": pri,
            "source_label": label,
        })

    if not raw_sources:
        ts_print(f"    ❌ 抓取全失败")
        return None

    ts_print(f"    📄 抓取 {len(raw_sources)} 个页面，LLM 排序中...")
    ranked = llm_rank_sources(goal, raw_sources)

    ranked = [r for r in ranked if r.get("relevance", 0) >= 4]
    if not ranked:
        ts_print(f"    ❌ LLM 过滤后无有效信源")
        return None

    ranked = ranked[:3]
    ts_print(f"    🔍 LLM 筛选后保留 {len(ranked)} 个信源")
    sufficient, reason = llm_check_sufficiency(goal, ranked)
    ts_print(f"    📊 信源充足性: {'✅' if sufficient else '⚠️'} {reason}")

    cached_sources = []
    for r in ranked:
        content_parts = []
        content_parts.append(f"# {r.get('title', 'Source')}")
        content_parts.append(f"> Source: {r['url']}")
        content_parts.append(f"> LLM 相关度: {r.get('relevance', 0)}/10")
        content_parts.append(f"> LLM 摘要: {r.get('summary', '')}")
        content_parts.append("")

        kp = r.get("key_paragraphs", [])
        if kp:
            content_parts.append("【关键段落】")
            content_parts.extend(kp)
        else:
            orig = next((s["raw_content"] for s in raw_sources if s["url"] == r["url"]), "")
            content_parts.append(orig)

        text = "\n\n".join(content_parts)

        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in r.get("title", "source"))[:50]
        if not safe_name:
            safe_name = f"src_{hashlib.md5(r['url'].encode()).hexdigest()[:8]}"
        fname = f"auto_{safe_name}.txt"
        fpath = SHARED / fname
        fpath.write_text(text, encoding="utf-8")
        cached_sources.append({
            "path": path_to_rel(str(fpath)),
            "url": r["url"],
            "title": r.get("title", r["url"]),
            "content": text,
            "relevance": r.get("relevance", 5),
        })

    if not cached_sources:
        ts_print(f"    ❌ 缓存全失败")
        return None

    reg = {}
    if REG_INDEX.exists():
        reg = json.loads(REG_INDEX.read_text())
    for src in cached_sources:
        sid = url_to_source_id(src["url"])
        if sid not in reg:
            reg[sid] = {
                "source_id": sid,
                "source_type": "web_crawl_llm",
                "title": src["title"][:200],
                "url": src["url"],
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "cache_path": src["path"],
                "content_hash": hashlib.md5(src["content"].encode()).hexdigest()[:12],
                "content_length": len(src["content"]),
                "keywords": kw.split(),
                "llm_relevance": src["relevance"],
                "used_by": [],
            }
    REG_INDEX.write_text(json.dumps(reg, indent=2, ensure_ascii=False))

    q = {"cards": []}
    if CARDS_FILE.exists():
        q = json.loads(CARDS_FILE.read_text())
    existing_ids = {c["id"] for c in q["cards"]}
    assigner = IdAssigner(existing_ids)
    cid = assigner.assign(series_key)

    series_data = pool.get(series_key, {})
    card = {
        "id": cid,
        "section": series_key,
        "topic": series_data.get("topic", "") if isinstance(series_data, dict) else "",
        "subsection": title,
        "status": "ready",
        "retries": 0,
        "goal": goal,
        "style": series_data.get("style", "") if isinstance(series_data, dict) else "",
        "search": [{"engine": "crawl4ai_llm", "query": kw}],
        "forbidden": series_data.get("forbidden", []) if isinstance(series_data, dict) else [],
        "min_chars": max(series_data.get("avg_chars", 350) - 100, 150) if isinstance(series_data, dict) else 200,
        "max_chars": (series_data.get("avg_chars", 350) + 100) if isinstance(series_data, dict) else 500,
        "node_type": "card",
        "source_files": [s["path"] for s in cached_sources],
    }
    q["cards"].append(card)
    CARDS_FILE.write_text(json.dumps(q, indent=2, ensure_ascii=False))

    for src in cached_sources:
        sid = url_to_source_id(src["url"])
        if sid in reg:
            used = set(reg[sid].get("used_by", []))
            used.add(cid)
            reg[sid]["used_by"] = sorted(used)
    REG_INDEX.write_text(json.dumps(reg, indent=2, ensure_ascii=False))

    return cid, sufficient, reason


async def step2_dispatch(pool: dict, count: int):
    setup_logging(log_dir=LOGS_DIR)
    crawler = await get_crawler()

    # 启动时预检搜索引擎可达性
    ts_print("🔍 网络预检...")
    net_status = await check_connectivity(crawler)
    engine_summary = []
    if net_status["ddg_ok"]:
        engine_summary.append("DDG ✓")
    else:
        engine_summary.append("DDG ✗")
    if net_status["baidu_ok"]:
        engine_summary.append("百度 ✓")
    else:
        engine_summary.append("百度 ✗")
    ts_print(f"  {' | '.join(engine_summary)} | 本地信源: {net_status['local_count']} 个")
    glog.info(f"网络预检: {net_status}")
    ts_print()

    all_pending = []
    for series in _get_priority():
        chapter_keys = sorted(k for k in pool if k.startswith(series) and (k == series or k[len(series):].isdigit()))
        for ck in chapter_keys if chapter_keys else [series]:
            if ck not in pool or not isinstance(pool[ck], dict):
                continue
            seeds = pool[ck].get("seeds", [])
            pending = [s for s in seeds if s.get("status") == "pending"]
            all_pending.extend([(series, s) for s in pending])

    import random; random.shuffle(all_pending)

    glog.info(f"▶ 阶段二派发: {min(count, len(all_pending))} 张 (pending pool: {len(all_pending)})")

    dispatched = 0
    for series_key, seed in all_pending[:count]:
        title = seed.get("title", "")[:50]
        kw = seed.get("kw", "")[:50]
        ts_print(f"\n  [{series_key}] {title}")
        ts_print(f"  kw: {kw}")

        result = await dispatch_one(crawler, seed, series_key, pool, net_status)
        if result:
            cid, sufficient, reason = result
            seed["status"] = "dispatched"
            dispatched += 1
            if sufficient:
                glog.info(f"  ✅ {cid} ready | 信源充足")
                ts_print(f"  ✅ {cid} ready（信源充足）")
            else:
                glog.info(f"  ⚠️ {cid} ready | 信源不足: {reason[:60]}")
                ts_print(f"  ⚠️ {cid} ready（信源不足: {reason[:60]}）")
        else:
            policy = get_source_policy(series_key)
            if policy == "required":
                seed["status"] = "source_failed"
                glog.warning(f"  ❌ {series_key} source_failed (required)")
                ts_print(f"  ❌ source_failed")
            else:
                seed["status"] = "dispatched"
                dispatched += 1
                glog.info(f"  ⚠️ {series_key} dispatched (no source, optional)")
                ts_print(f"  ⚠️ no source but optional, dispatched anyway")

        store.write(pool)

    q = json.loads(CARDS_FILE.read_text()) if CARDS_FILE.exists() else {"cards": []}
    statuses = dict(Counter(c["status"] for c in q["cards"]))
    glog.info(f"✓ 阶段二完成: {dispatched}/{count} dispatched | 队列: {statuses}")
    ts_print(f"\n📊 派发: {dispatched}/{count} | 队列: {statuses}")


def main():
    parser = argparse.ArgumentParser(description="LocalLLM-IP-Factory · 阶段一+二：种子生成 + 信源派发 (LLM增强)")
    parser.add_argument("--target", type=int, default=50, help="种子池每系列上限")
    parser.add_argument("--count", type=int, default=10, help="本次派发卡片数")
    args = parser.parse_args()

    ts_print(f"🚀 LocalLLM-IP-Factory · 阶段一+二 (target≥{args.target}, dispatch={args.count})")
    ts_print(f"   LLM: {XIANKA_MODEL} @ {XIANKA_GATEWAY}")
    ts_print()

    pool = store.read()

    ts_print("第零步: 系列扩展检查")
    pool = step0_series_expansion(pool)
    ts_print()

    # API 引擎预检（种子生成前，不需要 crawler）
    ts_print("🔍 引擎可用性预检...")
    engine_status = check_api_engines()
    for code, info in engine_status.items():
        ts_print(f"  {info['label']} ({code}): {'✓' if info['ok'] else '✗'}")
    ts_print()

    ts_print("阶段一: 种子生成")
    step0b_recycle_dead(pool)
    step1_generate_seeds(pool, args.target, engine_status)
    ts_print()

    ts_print("阶段二: 信源缓存 + 卡片派发 (LLM增强)")
    asyncio.run(step2_dispatch(pool, args.count))
    ts_print()

    pool = store.read()
    total_pending = 0
    for key in all_series_keys():
        if key in pool:
            c = sum(1 for s in pool[key].get("seeds", []) if s.get("status") == "pending")
            if c > 0:
                ts_print(f"  {key}: {c} pending")
            total_pending += c
    ts_print(f"\n📊 pending 总计: {total_pending}/{args.target}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        ts_print("\n⏹️ 用户中断")
    # close_crawler 不在这里调：crawler 是在 step2_dispatch 的
    # asyncio.run() 事件循环中创建的，在另一个事件循环里关它会
    # 因跨循环资源绑定而永久挂起。进程退出时 OS 会自动清理。
