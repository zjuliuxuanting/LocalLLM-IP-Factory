"""S7 事实核查 prompt

逐条核对卡片中的事实断言与信源的一致性，输出结构化结果（JSON）。
"""
import json

FACTCHECK_SCHEMA = {
    "factcheck": {
        "claims_checked": [
            {
                "claim": "核查的具体断言",
                "in_sources": True,
                "source_evidence": "信源中的对应原文或 '无'",
                "confidence": 0.95,
                "correction": "纠错建议（如需要，否则 null）",
            }
        ],
        "unverifiable_claims": ["无法在信源中确认的断言"],
        "overall_accuracy": 0.85,
        "risk_level": "safe|cautious|risky",
    }
}


def build_factcheck_prompt(card: dict, polished_text: str, source_text: str) -> str:
    cid = card["id"]
    subsection = card.get("subsection", "")

    parts = [
        f"你是LocalLLM-IP-Factory的事实核查员。请逐条核查以下卡片正文中的关键断言是否可以在信源中找到支撑。",
        f"",
        f"卡片: {cid} | {subsection}",
        f"",
        f"=== 信源材料 ===",
        source_text[:4000] if source_text else "(无信源)",
        f"=== 信源结束 ===",
        f"",
        f"=== 待核查正文 ===",
        polished_text,
        f"=== 正文结束 ===",
        f"",
        f"核查要求:",
        f"- 提取正文中的 3-6 个关键事实断言",
        f"- 逐条确认是否能在信源中找到对应支撑",
        f"- 对无法确认的断言标注在 unverifiable_claims 中",
        f"- confidence 表示你对此判断的确信度 (0-1)",
        f"- risk_level: safe=所有关键断言可验证, cautious=有少量无法验证, risky=有重要断言与信源矛盾",
        f"",
        f"只输出 JSON，格式如下:",
        json.dumps(FACTCHECK_SCHEMA, ensure_ascii=False, indent=2),
    ]

    return "\n".join(parts)
