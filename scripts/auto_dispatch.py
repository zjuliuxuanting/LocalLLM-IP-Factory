#!/usr/bin/env python3
"""阶段二自动化：Crawl4AI 抓取 + Wikipedia API 搜索。走 7897 代理。python3.11 scripts/auto_dispatch.py 10"""
import asyncio, json, os, re, hashlib, sys, time, random
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

import httpx
from crawl4ai import AsyncWebCrawler, BrowserConfig

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
os.chdir(str(SCRIPT_DIR))

PROXY = "http://<PROXY_HOST>:7897"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
SHARED = SCRIPT_DIR / "data" / "source_cache" / "shared"
SHARED.mkdir(parents=True, exist_ok=True)


async def search_wikipedia(client, kw, n=3):
    """Wikipedia API 搜索"""
    q = kw[:100].replace(" ", "+")
    r = await client.get(
        f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={q}&format=json&srlimit={n}"
    )
    if r.status_code != 200:
        return []
    try:
        return [{
            "title": h["title"],
            "url": f"https://en.wikipedia.org/wiki/{h['title'].replace(' ','_')}",
            "snippet": re.sub(r"<[^>]+>", "", h.get("snippet", ""))
        } for h in r.json().get("query", {}).get("search", [])[:n]]
    except Exception:
        return []


def cache_source(title, url, content):
    safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in title)[:50]
    fpath = SHARED / f"c4a_{safe.strip()}.md"
    fpath.write_text(f"# {title}\n> Source: {url}\n\n{content[:8000]}", encoding="utf-8")
    return path_to_rel(str(fpath))


def register(reg_file, title, url, cache_path, content, kw):
    idx = json.loads(reg_file.read_text()) if reg_file.exists() else {}
    sid = f"src_c4a_{hashlib.md5(url.encode()).hexdigest()[:10]}"
    idx[sid] = {
        "source_id": sid, "source_type": "web", "title": title[:200],
        "url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "cache_path": cache_path, "content_hash": hashlib.md5(content.encode()).hexdigest()[:12],
        "content_length": len(content), "keywords": kw.split(), "used_by": [],
    }
    reg_file.write_text(json.dumps(idx, indent=2, ensure_ascii=False))
    return sid


async def dispatch_batch(count=5):
    seed_file = SCRIPT_DIR / "data" / "seed_pool.json"
    reg_file = SCRIPT_DIR / "data" / "source_registry" / "index.json"
    reg_file.parent.mkdir(parents=True, exist_ok=True)
    cards_file = SCRIPT_DIR / "data" / "queue" / "cards.json"
    cards_file.parent.mkdir(parents=True, exist_ok=True)

    pool = json.loads(seed_file.read_text())
    q = json.loads(cards_file.read_text()) if cards_file.exists() else {"cards": []}

    priority = ["R", "Q", "M", "F", "P", "S", "B"]
    all_pending = []
    for s in priority:
        if s not in pool or not isinstance(pool[s], dict):
            continue
        seeds = [x for x in pool[s].get("seeds", []) if x.get("status") == "pending"]
        # 只取 kw 含英文的种子
        seeds = [x for x in seeds if any(ord(c) < 128 and c.isalpha() for c in x.get("kw", "")[:10])]
        random.shuffle(seeds)
        all_pending.extend([(s, x) for x in seeds])

    browser_cfg = BrowserConfig(proxy=PROXY, headless=True, verbose=False)
    headers = {"User-Agent": UA}
    async with httpx.AsyncClient(proxy=PROXY, headers=headers, timeout=20, follow_redirects=True) as client:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            dispatched = 0
            for series_key, seed in all_pending[:count]:
                kw = seed.get("kw", "")
                goal = seed.get("goal", "")
                title = seed.get("title", "")
                print(f"\n  [{series_key}] {title[:50]}")
                print(f"  kw: {kw[:60]}")

                # 1. 搜索
                hits = await search_wikipedia(client, kw)
                print(f"  search: {len(hits)} hits")

                if not hits:
                    print(f"  ❌ 0 hits")
                    seed["status"] = "source_failed"
                    seed_file.write_text(json.dumps(pool, indent=2, ensure_ascii=False))
                    continue

                # 2. 用 Crawl4AI 抓取每个命中
                source_files = []
                for hit in hits[:3]:
                    url = hit["url"]
                    try:
                        result = await crawler.arun(url)
                        content = result.markdown
                    except Exception:
                        content = hit.get("snippet", hit["title"])

                    if len(content) < 100:
                        content = hit.get("snippet", hit["title"])

                    cp = cache_source(hit["title"], url, content)
                    source_files.append(cp)
                    register(reg_file, hit["title"], url, cp, content, kw)
                    print(f"    📄 {hit['title'][:40]}: {len(content)} chars")

                # 3. 创建卡片
                from src.utils.id_assigner import IdAssigner
from config.settings import path_to_rel
                assigner = IdAssigner({c["id"] for c in q["cards"]})
                cid = assigner.assign(series_key)
                topic = pool[series_key].get("topic", "") if isinstance(pool[series_key], dict) else ""
                style = pool[series_key].get("style", "") if isinstance(pool[series_key], dict) else ""
                forbidden = pool[series_key].get("forbidden", []) if isinstance(pool[series_key], dict) else []
                avg = pool[series_key].get("avg_chars", 350) if isinstance(pool[series_key], dict) else 350

                q["cards"].append({
                    "id": cid, "section": series_key, "topic": topic, "subsection": title,
                    "status": "ready", "retries": 0, "goal": goal, "style": style,
                    "search": [{"engine": "web_fetch", "query": kw}],
                    "forbidden": forbidden, "min_chars": max(avg-100, 150), "max_chars": avg+100,
                    "node_type": "card", "source_files": source_files,
                })
                seed["status"] = "dispatched"
                dispatched += 1
                print(f"  ✅ {cid} ready ({len(source_files)} sources)")

                seed_file.write_text(json.dumps(pool, indent=2, ensure_ascii=False))
                cards_file.write_text(json.dumps(q, indent=2, ensure_ascii=False))

    statuses = Counter(c["status"] for c in q["cards"])
    print(f"\n📊 派发: {dispatched}/{count} | 队列: {dict(statuses)}")


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    print(f"📡 Crawl4AI 自动化阶段二：{count} 张")
    asyncio.run(dispatch_batch(count))


if __name__ == "__main__":
    main()
