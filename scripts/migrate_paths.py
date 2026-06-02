#!/usr/bin/env python3
"""一次性迁移：将 cards.json 和 index.json 中所有绝对路径转为 PROJECT_ROOT 相对路径。

用法: python3 scripts/migrate_paths.py [--dry-run]
"""
import json, sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from config.settings import PROJECT_ROOT, path_to_rel


def migrate_file(filepath: Path, array_fields: set[str], scalar_fields: set[str]) -> int:
    """递归遍历 JSON，对 array_fields 数组中的字符串元素 + scalar_fields 中的字符串值执行 path_to_rel()"""
    if not filepath.exists():
        print(f"  ⚠️ 文件不存在: {filepath}")
        return 0
    data = json.loads(filepath.read_text())
    count = _walk(data, array_fields, scalar_fields)
    if count > 0:
        filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return count


def _walk(obj, array_fields, scalar_fields):
    count = 0
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key in scalar_fields and isinstance(val, str) and val:
                new = path_to_rel(val)
                if new != val:
                    obj[key] = new
                    count += 1
            elif key in array_fields and isinstance(val, list):
                for i, item in enumerate(val):
                    if isinstance(item, str) and item:
                        new = path_to_rel(item)
                        if new != item:
                            val[i] = new
                            count += 1
            elif isinstance(val, (dict, list)):
                count += _walk(val, array_fields, scalar_fields)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                count += _walk(item, array_fields, scalar_fields)
    return count


def main():
    dry_run = "--dry-run" in sys.argv

    c_count = migrate_file(
        SCRIPT_DIR / "data" / "queue" / "cards.json",
        array_fields={"source_files"},
        scalar_fields=set(),
    )
    r_count = migrate_file(
        SCRIPT_DIR / "data" / "source_registry" / "index.json",
        array_fields=set(),
        scalar_fields={"cache_path", "original_file"},
    )

    print(f"cards.json source_files: {c_count} paths")
    print(f"index.json cache_path/original_file: {r_count} paths")
    total = c_count + r_count
    if dry_run:
        print(f"\n⏸️  dry-run — {total} paths would be migrated")
    elif total == 0:
        print("\n✅ 所有路径已是相对路径，无需迁移")
    else:
        print(f"\n✅ {total} paths migrated")


if __name__ == "__main__":
    main()
