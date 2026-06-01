"""S2 大纲生成 prompt

要求模型基于信源输出结构化的内容大纲（JSON 格式）。
"""
import json

OUTLINE_SYSTEM = """你是喵言汪语的资深内容策划。你的任务是为一张科普卡片设计结构化大纲。

你需要基于提供的信源材料，规划卡片的叙事结构。每个要点必须可以在信源中找到支撑。
如果信源不足以覆盖某个方面，请在 knowledge_gap 中标注。"""

OUTLINE_SCHEMA = {
    "outline": {
        "sections": [
            {
                "heading": "小节标题",
                "key_points": ["要点1", "要点2"],
                "estimated_chars": 120,
                "source_refs": ["信源文件名"],
            }
        ],
        "total_estimated_chars": 350,
        "narrative_arc": "起承转合的一句话描述",
        "knowledge_gap": "信源未覆盖但需要说明的部分（无可填'无'）",
    }
}


def build_outline_prompt(card: dict, source_text: str, context: str = "") -> str:
    cid = card["id"]
    min_c = card.get("min_chars", 300)
    max_c = card.get("max_chars", 600)
    style = card.get("style", "")
    goal = card.get("goal", "")
    subsection = card.get("subsection", "")

    parts = [
        f"为卡片 {cid} 设计内容大纲。",
        f"话题: {subsection}",
        f"目标: {goal}",
        f"期望风格: {style}",
        f"字数范围: {min_c}-{max_c} 字",
        "",
        f"信源材料:",
        source_text if source_text else "(无信源，基于常识规划)",
        "",
        f"大纲要求:",
        f"- 规划 2-4 个小节，每个小节有明确的要点",
        f"- 总预估字数在 {min_c}-{max_c} 之间",
        f"- narrative_arc 描述叙事线索（起承转合）",
        f"- 如果信源不足以覆盖某方面，在 knowledge_gap 中标注",
    ]

    if context:
        parts.append(f"\n前文上下文（避免重复）:\n{context}")

    parts.append(f"\n只输出 JSON，格式如下:\n{json.dumps(OUTLINE_SCHEMA, ensure_ascii=False, indent=2)}")

    return "\n".join(parts)
