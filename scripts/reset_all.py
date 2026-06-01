#!/usr/bin/env python3
"""一次清空所有卡片、种子、缓存"""
import json, pathlib, shutil

root = pathlib.Path(__file__).resolve().parent.parent

# cards.json → 空
json.dump({"cards": []}, open(root / "data/queue/cards.json", "w"), indent=2)
print("  ✅ cards.json → []")

# seed_pool.json → 清空所有种子，保留系列定义
pool = json.loads(open(root / "data/seed_pool.json").read())
for v in pool.values():
    if isinstance(v, dict):
        v["seeds"] = []
json.dump(pool, open(root / "data/seed_pool.json", "w"), indent=2, ensure_ascii=False)
print("  ✅ seed_pool.json → 0 种子")

# source_registry/index.json → 保留本地信源，清空其余
reg_path = root / "data/source_registry/index.json"
reg = json.loads(reg_path.read_text()) if reg_path.exists() else {}
local_reg = {k: v for k, v in reg.items() if v.get("source_type") == "local_translated"}
reg_path.write_text(json.dumps(local_reg, indent=2, ensure_ascii=False))
print(f"  ✅ source_registry/index.json → 保留 {len(local_reg)} 个本地信源")

# source_cache/shared/ → 清空非本地信源缓存（保留 local_* 翻译结果）
shared = root / "data/source_cache/shared"
for f in list(shared.iterdir()):
    if f.is_file() and not f.name.startswith("local_"):
        f.unlink()
print(f"  ✅ source_cache/shared/ → 清空爬取缓存（保留 local_* 翻译结果）")

# output/cards/ → 清空
cards_out = root / "output/cards"
for f in cards_out.glob("*.md"):
    f.unlink()
print("  ✅ output/cards/ → 清空")

# output/logs/ → 清空
logs_dir = root / "output/logs"
if logs_dir.exists():
    for f in logs_dir.glob("*"):
        if f.is_file():
            f.unlink()
    print("  ✅ output/logs/ → 清空")

# data/series_proposals/ → 清空
props = root / "data/series_proposals"
if props.exists():
    for f in props.glob("*.json"):
        f.unlink()
    print("  ✅ data/series_proposals/ → 清空")

# series_definitions.py → 清空系列定义（留空壳，第1次跑 pipeline 时自动生成）
sd_file = root / "config/series_definitions.py"
sd_file.chmod(0o644)
EMPTY_SD = '''"""系列定义 — 由 pipeline 首次运行时自动生成"""
from typing import Optional

SERIES: dict = {}
RETIRED_SERIES = []


def get_series(key: str) -> Optional[dict]:
    return SERIES.get(key)


def all_series_keys() -> list[str]:
    return []


def get_source_policy(key: str) -> str:
    return "optional"


def get_target_ratio(key: str) -> float:
    return 0.0


def get_subtopics(key: str) -> list:
    return []


def get_example_seed(key: str) -> dict:
    return {}


def get_goal_rule(key: str) -> str:
    return "写作目标，≥20字"


def get_kw_rule(key: str) -> str:
    return "英文关键词 ≥2 词"
'''
sd_file.write_text(EMPTY_SD, encoding="utf-8")
print("  ✅ series_definitions.py -> 已清空（等待 pipeline 首次运行生成）")

print("\n全部清空完成")
