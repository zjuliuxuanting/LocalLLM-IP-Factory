"""S6 润色 prompt

对修订版进行最终文字润色，输出纯文本。
"""


def build_polish_prompt(card: dict, revised_text: str) -> str:
    cid = card["id"]
    style = card.get("style", "")
    subsection = card.get("subsection", "")
    forbidden = card.get("forbidden") or []

    parts = [
        f"你是喵言汪语的首席编辑。请对以下卡片正文进行最终文字润色。直接输出纯文本。",
        f"",
        f"卡片: {cid} | {subsection}",
        f"期望风格: {style}",
        f"",
        f"=== 待润色正文 ===",
        revised_text,
        f"=== 正文结束 ===",
        f"",
        f"润色要求:",
        f"- 修正错别字和不通顺的句子",
        f"- 统一语气和用词风格",
        f"- 优化段落间的过渡衔接",
        f"- 删除多余的感叹号或重复用词",
        f"- 保持原意不动，只做文字层面的打磨",
    ]

    if forbidden:
        parts.append(f"- 避免使用以下词语: {', '.join(forbidden)}")

    parts.append(f"\n直接输出润色后的完整正文，不要任何说明文字。")

    return "\n".join(parts)
