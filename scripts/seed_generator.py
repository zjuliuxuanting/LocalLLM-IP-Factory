#!/usr/bin/env python3
"""
阶段一：种子生成

从已有系列中检查 pending 种子数，不足时调 LLM补种。
包含第零步：系列扩展（检测饱和→自动提案→写入）。

用法: python3 scripts/seed_generator.py --target 500
"""
import argparse, json, sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from src.models.gateway import call_xianka
from src.models.prompts.seed import build_seed_generation_prompt
from src.quality.seed_gate import inspect_seed
from src.io.store import AtomicJsonStore
from src.pipeline.series_expansion import run_expansion_check
from config.series_definitions import all_series_keys, get_series
from config.settings import SEED_POOL_FILE

store = AtomicJsonStore(SEED_POOL_FILE, {})
from src.utils.engine_check import check_api_engines


def step0_series_expansion(pool: dict):
    """第零步：检测饱和，自动提案新系列"""
    result = run_expansion_check(pool, auto_generate=True)
    if result.get("proposal"):
        p = result["proposal"]
        print(f"  🆕 新系列提案: {p['code']} {p['name']} (验证分 {p['validation']['score']}/10)")
        if p["validation"]["passed"]:
            print(f"  ✅ 自动通过: {p['rationale'][:80]}...")
            # 系列写入由 series_expansion._add_series_to_definitions 完成
    return pool


def step1_generate_seeds(pool: dict, target: int, engine_status=None):
    """阶段一：检查各系列 pending，不足时补种"""
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

        s = get_series(series_key)
        if not s:
            continue

        from src.pipeline.seed_diversity import get_series_seeds, analyze_coverage
        from config.series_definitions import get_subtopics
        all_s = get_series_seeds(pool, series_key)
        existing_titles = [s.get("title", "") for s in all_s]
        coverage = analyze_coverage(series_key, all_s)
        subtopics = get_subtopics(series_key)

        prompt = build_seed_generation_prompt(
            series=series_key,
            topic=s.get("topic", ""),
            style=s.get("style", ""),
            existing_titles=existing_titles,
            needed=needed,
            subtopics=subtopics,
            covered_topics=coverage.get("covered_topics", []),
            chapter_info="",
            engine_status=engine_status,
        )

        raw = call_xianka(prompt, max_tokens=4096, temperature=0.8)
        if not raw:
            print(f"    ❌ LLM调用失败")
            continue

        import re
        m = re.search(r'\[[\s\S]*\]', raw)
        if not m:
            continue
        try:
            candidates = json.loads(m.group())
        except json.JSONDecodeError:
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
        print(f"    ✅ +{accepted} 种子 (pending 总计 {len([s for s in seeds if s.get('status')=='pending'])}）")


def main():
    parser = argparse.ArgumentParser(description="LocalLLM-IP-Factory · 阶段一：种子生成")
    parser.add_argument("--target", type=int, default=500, help="种子池 pending 目标数")
    args = parser.parse_args()

    print(f"🌱 LocalLLM-IP-Factory · 阶段一 (目标 pending ≥ {args.target})")
    print()

    print("🔍 引擎可用性预检...")
    engine_status = check_api_engines()
    for code, info in engine_status.items():
        print(f"  {info['label']} ({code}): {'✓' if info['ok'] else '✗'}")
    print()

    pool = store.read()

    print("第零步: 系列扩展检查")
    pool = step0_series_expansion(pool)
    print()

    print("阶段一: 种子补种")
    step1_generate_seeds(pool, args.target, engine_status)
    print()

    # 报告
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
    main()
