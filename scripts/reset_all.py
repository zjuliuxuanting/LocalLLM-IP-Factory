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

# source_registry/index.json → 空
json.dump({}, open(root / "data/source_registry/index.json", "w"))
print("  ✅ source_registry/index.json → {}")

# source_cache/shared/ → 清空
shared = root / "data/source_cache/shared"
for f in list(shared.iterdir()):
    if f.is_file():
        f.unlink()
print(f"  ✅ source_cache/shared/ → 清空")

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

print("\n全部清空完成")
