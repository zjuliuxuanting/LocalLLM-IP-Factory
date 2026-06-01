#!/usr/bin/env python3
"""用 LLM 从 SERIES_TOPICS.md 生成 series_definitions.py

结构定死：从 config/series_schema.json 读取固定字段结构。
数据来源：docs/SERIES_TOPICS.md（系列定义唯一入口）。

用法:
    python3 scripts/import_series_names.py          # 预览
    python3 scripts/import_series_names.py --apply  # 写入
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.models.gateway import call_xianka


SCHEMA_FILE = ROOT / "config" / "series_schema.json"
MD_FILE = ROOT / "docs" / "SERIES_TOPICS.md"
PY_FILE = ROOT / "config" / "series_definitions.py"


def build_prompt(md_text: str, schema: dict) -> str:
    """构建 LLM prompt：schema 定结构，MD 给数据"""
    return f"""你是一个配置生成器。根据以下 JSON Schema 和 Markdown 文档，生成一个完整的 Python dict。

## JSON Schema（结构定义）
{json.dumps(schema, indent=2, ensure_ascii=False)}

## Markdown 数据源
{md_text}

## 要求
1. 严格按 JSON Schema 的结构和字段生成
2. 每个系列用 Markdown 中的内容填充对应字段
3. forbidden 字段全部用：["在本文中", "值得注意的是", "综上所述"]
4. source_policy: 小说叙事(S)用 "optional"，其他用 "required"
5. target_ratio: B=0.18, R=0.15, M=0.12, S=0.15, Q=0.15, F=0.15, P=0.10
6. avg_chars: B=450, R=400, M=350, S=500, Q=300, F=400, P=500
7. topic 格式：'{{代码}} {{name}}'，如 'B 背景知识 / 沟通简史'
8. name 从 ## 标题行提取（如 '## B：背景知识 / 沟通简史' → name='背景知识 / 沟通简史'）
9. 只输出 Python dict，不要多余文字和代码块标记"""


def parse_llm_response(raw: str) -> dict:
    """从 LLM 返回中提取 JSON"""
    import re
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        raise ValueError("LLM 返回中没有找到 JSON")
    return json.loads(m.group())


def validate_series(data: dict, schema: dict) -> list[str]:
    """简单校验：确保每个条目有 required 字段"""
    errors = []
    required = schema["patternProperties"]["^[A-Z]$"]["required"]
    for code, entry in data.items():
        if not isinstance(entry, dict):
            errors.append(f"{code}: 不是 dict")
            continue
        for field in required:
            if field not in entry:
                errors.append(f"{code}: 缺少字段 '{field}'")
    return errors


def main():
    parser = argparse.ArgumentParser(description="LLM 导入系列名称")
    parser.add_argument("--apply", action="store_true", help="实际写入文件")
    args = parser.parse_args()

    schema = json.loads(SCHEMA_FILE.read_text())
    md_text = MD_FILE.read_text(encoding="utf-8")

    print("📞 调用 LLM 生成系列定义...")
    prompt = build_prompt(md_text, schema)

    raw = call_xianka(prompt, max_tokens=4096, temperature=0.3)
    if not raw:
        print("❌ LLM 调用失败")
        sys.exit(1)

    try:
        data = parse_llm_response(raw)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"❌ JSON 解析失败: {e}")
        print(f"    LLM 原始返回前 500 字: {raw[:500]}")
        sys.exit(1)

    errors = validate_series(data, schema)
    if errors:
        print(f"❌ 校验发现 {len(errors)} 个问题:")
        for e in errors:
            print(f"   {e}")
        sys.exit(1)

    print(f"📖 LLM 生成了 {len(data)} 个系列:")
    for code, entry in sorted(data.items()):
        print(f"   {code}: {entry.get('topic', entry.get('name', '?'))}")

    py_output = f'"""系列定义 — 单一数据源\n\n由 scripts/import_series_names.py 自动生成\n数据源: docs/SERIES_TOPICS.md\n结构定义: config/series_schema.json\n"""\nfrom typing import Optional\n\n\nSERIES = {json.dumps(data, indent=2, ensure_ascii=False)}\n\n\nRETIRED_SERIES = []\n\n\ndef get_series(key: str) -> Optional[dict]:\n    return SERIES.get(key)\n\n\ndef all_series_keys() -> list[str]:\n    return [k for k in SERIES if k not in RETIRED_SERIES]\n\n\ndef get_source_policy(key: str) -> str:\n    s = SERIES.get(key, {{}})\n    return s.get("source_policy", "optional")\n\n\ndef get_target_ratio(key: str) -> float:\n    s = SERIES.get(key, {{}})\n    return s.get("target_ratio", 0.0)\n\n\ndef get_subtopics(key: str) -> list[str]:\n    s = SERIES.get(key, {{}})\n    return s.get("subtopics", [])\n\n\ndef get_example_seed(key: str) -> dict:\n    s = SERIES.get(key, {{}})\n    return s.get("example_seed", {{}})\n\n\ndef get_goal_rule(key: str) -> str:\n    s = SERIES.get(key, {{}})\n    return s.get("goal_rule", "写作目标，≥20字")\n\n\ndef get_kw_rule(key: str) -> str:\n    s = SERIES.get(key, {{}})\n    return s.get("kw_rule", "英文关键词 ≥2 词")\n'

    if not args.apply:
        print("\n💡 预览模式，使用 --apply 实际写入")
        print(f"   将写入 {len(py_output)} 字符到 {PY_FILE}")
        return

    PY_FILE.write_text(py_output, encoding="utf-8")
    print(f"\n✅ 已写入 {PY_FILE} ({len(data)} 个系列)")


if __name__ == "__main__":
    main()
