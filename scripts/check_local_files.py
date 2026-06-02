#!/usr/bin/env python3
"""检测 data/source_cache/local/ 中需要翻译的新文件或已修改文件。
输出: 每行一个文件名（🆕 新文件 / 🔄 已修改）
用法: python3 scripts/check_local_files.py
"""
import json, pathlib, sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

LOCAL_DIR = SCRIPT_DIR / "data" / "source_cache" / "local"
REG_FILE = SCRIPT_DIR / "data" / "source_registry" / "index.json"

if not LOCAL_DIR.exists():
    sys.exit(0)

reg = json.loads(REG_FILE.read_text()) if REG_FILE.exists() else {}

# 建立 原始文件绝对路径 → registry 条目 映射
tracked = {}
for v in reg.values():
    if v.get("source_type") == "local_translated" and v.get("original_file"):
        fp = str((SCRIPT_DIR / v["original_file"]).resolve())
        tracked[fp] = v

need = []
for p in sorted(LOCAL_DIR.iterdir()):
    if not p.is_file():
        continue
    # 跳过 macOS 资源分支和隐藏文件
    if p.name.startswith("._") or p.name.startswith(".DS_Store"):
        continue
    fp = str(p.resolve())
    if fp not in tracked:
        print(f"\U0001f195 {p.name}")
    else:
        org_mtime = p.stat().st_mtime
        cache_path = tracked[fp].get("cache_path", "")
        if cache_path:
            cache_abs = SCRIPT_DIR / cache_path
            cache_mtime = cache_abs.stat().st_mtime if cache_abs.exists() else 0
            if org_mtime > cache_mtime + 5:
                print(f"\U0001f504 {p.name}")
