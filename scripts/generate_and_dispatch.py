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
    MAX_TOKENS, TEMPERATURE,
)
from src.pipeline.series_expansion import run_expansion_check

SHARED = SCRIPT_DIR / "data" / "source_cache" / "shared"
REG_INDEX = SCRIPT_DIR / "data" / "source_registry" / "index.json"
CARDS_FILE = SCRIPT_DIR / "data" / "queue" / "cards.json"
SHARED.mkdir(parents=True, exist_ok=True)
REG_INDEX.parent.mkdir(parents=True, exist_ok=True)
CARDS_FILE.parent.mkdir(parents=True, exist_ok=True)

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
    ("baike.baidu.com", "baike", 6, "百度百科"),
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

PRIORITY = ["A", "B", "C", "D", "E", "F", "G"]

# 显卡妹 LLM 配置（供 Crawl4AI 的 LLM extraction strategy 使用）
# 显卡妹 API = OpenAI 兼容: {XIANKA_GATEWAY}/v1/chat/completions
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
        print(f"  🆕 新系列提案: {p['code']} {p['name']} (验证分 {p['validation']['score']}/10)")
    return pool


def step1_generate_seeds(pool: dict, target: int):
    for series_key in all_series_keys():
        if series_key not in pool:
            print(f"  ⚠️ {series_key} 不在 seed_pool，跳过")
            continue
        data = pool[series_key]
        seeds = data.get("seeds", [])
        pending_count = sum(1 for s in seeds if s.get("status") == "pending")
        needed = max(0, target // len(all_series_keys()) - pending_count)
        if needed <= 0:
            continue
        print(f"  🌱 {series_key}: pending={pending_count}, 需补 {needed} 个")
        existing_titles = [s.get("title", "") for s in seeds]
        s = get_series(series_key)
        if not s:
            continue
        prompt = build_seed_generation_prompt(
            series=series_key,
            topic=s.get("topic", ""),
            style=s.get("style", ""),
            existing_titles=existing_titles,
            needed=needed,
        )
        raw = call_xianka(prompt, max_tokens=4096, temperature=0.8)
        if not raw:
            print(f"    ⚠️ 显卡妹调用失败，重试...")
            raw = call_xianka(prompt, max_tokens=4096, temperature=0.8)
        if not raw:
            print(f"    ❌ 显卡妹调用失败，跳过 {series_key}")
            continue
        m = re.search(r'\[[\s\S]*\]', raw)
        if not m:
            print(f"    ⚠️ 返回无 JSON 数组，回退提取 JSON 对象...")
            m = re.search(r'\{[\s\S]*\}', raw)
        if not m:
            print(f"    ❌ 无法从返回中提取任何 JSON，跳过 {series_key}")
            continue
        try:
            candidates = json.loads(m.group())
            if isinstance(candidates, dict):
                candidates = [candidates]
        except json.JSONDecodeError:
            print(f"    ❌ JSON 解析失败，跳过 {series_key}")
            continue
        if not isinstance(candidates, list):
            print(f"    ⚠️ 返回非数组 JSON，跳过")
            continue
        accepted = 0
        for seed in candidates:
            if all(k in seed for k in ("title", "goal", "engine", "kw")):
                result = inspect_seed(seed, series_key, existing_titles, check_source=False)
                if result.passed:
                    seed["status"] = "pending"
                    seeds.append(seed)
                    existing_titles.append(seed["title"])
                    accepted += 1
        pool[series_key]["seeds"] = seeds
        store.write(pool)
        print(f"    ✅ +{accepted} 种子")


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
    """用显卡妹对抓取的原文按 goal 相关性排序 + 提取关键段落

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


async def dispatch_one(crawler, seed: dict, series_key: str, pool: dict):
    kw = seed.get("kw", "")
    goal = seed.get("goal", "")
    title = seed.get("title", "")

    all_hits = []
    has_cn = bool(re.search(r'[\u4e00-\u9fff]', kw))
    if has_cn:
        print(f"    🌏 中文 kw，优先百度")
        for level in (0, 2, 3):
            search_kw = downgrade_kw(kw, level) if level > 0 else kw
            hits = await search_baidu(crawler, search_kw)
            label = f"L{level}" if level > 0 else "L0"
            print(f"    baidu({label}): {len(hits)} hits")
            all_hits.extend(hits)
            if len(all_hits) >= 3:
                break
        if len(all_hits) < 3:
            whits = await search_web(crawler, kw)
            existing_urls = {h["url"] for h in all_hits}
            for h in whits:
                if h["url"] not in existing_urls:
                    all_hits.append(h)
                    existing_urls.add(h["url"])
            print(f"    web: +{len(whits)}")
    else:
        for level in (0, 2, 3):
            search_kw = downgrade_kw(kw, level) if level > 0 else kw
            hits = await search_web(crawler, search_kw)
            label = f"L{level}" if level > 0 else "L0"
            print(f"    web({label}): {len(hits)} hits")
            all_hits.extend(hits)
            if len(all_hits) >= 3:
                break
        if len(all_hits) < 3:
            bhits = await search_baidu(crawler, kw)
            existing_urls = {h["url"] for h in all_hits}
            for h in bhits:
                if h["url"] not in existing_urls:
                    all_hits.append(h)
                    existing_urls.add(h["url"])
            print(f"    baidu: +{len(bhits)}")

    if not all_hits:
        print(f"    ❌ 0 信源")
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
        print(f"    ❌ 抓取全失败")
        return None

    print(f"    📄 抓取 {len(raw_sources)} 个页面，LLM 排序中...")
    ranked = llm_rank_sources(goal, raw_sources)

    ranked = [r for r in ranked if r.get("relevance", 0) >= 4]
    if not ranked:
        print(f"    ❌ LLM 过滤后无有效信源")
        return None

    ranked = ranked[:4]
    print(f"    🔍 LLM 筛选后保留 {len(ranked)} 个信源")
    sufficient, reason = llm_check_sufficiency(goal, ranked)
    print(f"    📊 信源充足性: {'✅' if sufficient else '⚠️'} {reason}")

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
            "path": str(fpath),
            "url": r["url"],
            "title": r.get("title", r["url"]),
            "content": text,
            "relevance": r.get("relevance", 5),
        })

    if not cached_sources:
        print(f"    ❌ 缓存全失败")
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
    crawler = await get_crawler()

    all_pending = []
    for series in PRIORITY:
        if series not in pool or not isinstance(pool[series], dict):
            continue
        seeds = pool[series].get("seeds", [])
        pending = [s for s in seeds if s.get("status") == "pending"]
        import random; random.shuffle(pending)
        all_pending.extend([(series, s) for s in pending])

    dispatched = 0
    for series_key, seed in all_pending[:count]:
        title = seed.get("title", "")[:50]
        kw = seed.get("kw", "")[:50]
        print(f"\n  [{series_key}] {title}")
        print(f"  kw: {kw}")

        result = await dispatch_one(crawler, seed, series_key, pool)
        if result:
            cid, sufficient, reason = result
            seed["status"] = "dispatched"
            dispatched += 1
            if sufficient:
                print(f"  ✅ {cid} ready（信源充足）")
            else:
                print(f"  ⚠️ {cid} ready（信源不足: {reason[:60]}）")
        else:
            policy = get_source_policy(series_key)
            if policy == "required":
                seed["status"] = "source_failed"
                print(f"  ❌ source_failed")
            else:
                seed["status"] = "dispatched"
                dispatched += 1
                print(f"  ⚠️ no source but optional, dispatched anyway")

        store.write(pool)

    q = json.loads(CARDS_FILE.read_text()) if CARDS_FILE.exists() else {"cards": []}
    statuses = Counter(c["status"] for c in q["cards"])
    print(f"\n📊 派发: {dispatched}/{count} | 队列: {dict(statuses)}")


def main():
    parser = argparse.ArgumentParser(description="喵言汪语 V3 · 阶段一+二：种子生成 + 信源派发 (LLM增强)")
    parser.add_argument("--target", type=int, default=300, help="种子池 pending 目标数")
    parser.add_argument("--count", type=int, default=10, help="本次派发卡片数")
    args = parser.parse_args()

    print(f"🚀 喵言汪语 V3 · 阶段一+二 (target≥{args.target}, dispatch={args.count})")
    print(f"   LLM: {XIANKA_MODEL} @ {XIANKA_GATEWAY}")
    print()

    pool = store.read()

    print("第零步: 系列扩展检查")
    pool = step0_series_expansion(pool)
    print()

    print("阶段一: 种子生成")
    step1_generate_seeds(pool, args.target)
    print()

    print("阶段二: 信源缓存 + 卡片派发 (LLM增强)")
    asyncio.run(step2_dispatch(pool, args.count))
    print()

    pool = store.read()
    total_pending = 0
    for key in all_series_keys():
        if key in pool:
            c = sum(1 for s in pool[key].get("seeds", []) if s.get("status") == "pending")
            if c > 0:
                print(f"  {key}: {c} pending")
            total_pending += c
    print(f"\n📊 pending 总计: {total_pending}/{args.target}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⏹️ 用户中断")
    # close_crawler 不在这里调：crawler 是在 step2_dispatch 的
    # asyncio.run() 事件循环中创建的，在另一个事件循环里关它会
    # 因跨循环资源绑定而永久挂起。进程退出时 OS 会自动清理。
