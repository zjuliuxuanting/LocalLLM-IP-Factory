"""S4 自审 prompt

对初稿进行多维自审，输出结构化评审结果（JSON）。
"""
import json

REVIEW_SCHEMA = {
    "review": {
        "factual_issues": [
            {"claim": "原文中的具体断言", "issue": "问题描述", "severity": "high|medium|low"}
        ],
        "style_issues": [
            {"location": "原文位置描述", "suggestion": "改进建议"}
        ],
        "coherence_issues": [
            {"description": "逻辑不连贯之处"}
        ],
        "length_ok": True,
        "format_ok": True,
        "overall_score": 7.5,
        "verdict": "pass|warn|fail",
        "revision_priority": ["最高优先级修改项"],
    }
}


def build_review_prompt(card: dict, draft_text: str, source_text: str = "") -> str:
    cid = card["id"]
    style = card.get("style", "")
    subsection = card.get("subsection", "")

    parts = [
        f"你是LocalLLM-IP-Factory的审稿编辑。请对以下卡片初稿进行多维审核。",
        f"",
        f"卡片: {cid} | {subsection}",
        f"期望风格: {style}",
        f"",
        f"=== 初稿正文 ===",
        draft_text,
        f"=== 正文结束 ===",
    ]

    if source_text:
        parts.append(f"\n信源参考:\n{source_text[:2000]}")

    parts.append(f"""
审核要点:
1. 事实准确: 断言是否与信源一致？是否有编造的数据/人名/年份？
2. 风格一致: 是否符合期望风格？语气是否恰当？
3. 逻辑连贯: 段落之间衔接是否自然？
4. 格式检查: 是否有代码块包裹、元描述词等格式问题？
5. 字数检查: 正文是否在要求的字数范围内？

只输出 JSON，格式如下:
{json.dumps(REVIEW_SCHEMA, ensure_ascii=False, indent=2)}""")

    return "\n".join(parts)
