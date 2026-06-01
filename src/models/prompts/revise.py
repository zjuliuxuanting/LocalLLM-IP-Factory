"""S5 修订 prompt

基于自审结果修订初稿。输出纯文本。
"""


def build_revise_prompt(
    card: dict,
    draft_text: str,
    review_result: dict,
    context: str = "",
) -> str:
    cid = card["id"]
    min_c = card.get("min_chars", 300)
    max_c = card.get("max_chars", 600)
    style = card.get("style", "")

    review = review_result.get("review", review_result)
    factual = review.get("factual_issues", [])
    style_issues = review.get("style_issues", [])
    coherence_issues = review.get("coherence_issues", [])
    priority = review.get("revision_priority", [])

    fix_items = []
    for f in factual:
        fix_items.append(f"- [事实] {f.get('claim', '')}: {f.get('issue', '')} (严重: {f.get('severity', '')})")
    for s in style_issues:
        fix_items.append(f"- [风格] {s.get('location', '')}: {s.get('suggestion', '')}")
    for c in coherence_issues:
        fix_items.append(f"- [连贯] {c.get('description', '')}")
    fix_block = "\n".join(fix_items) if fix_items else "无重大问题"

    parts = [
        f"请根据以下审稿意见修订卡片正文。直接输出纯文本。",
        f"",
        f"卡片: {cid}",
        f"期望风格: {style}",
        f"字数: {min_c}-{max_c} 字",
        f"",
        f"=== 需要修改的问题 ===",
        fix_block,
        f"",
        f"优先修改: {', '.join(priority) if priority else '无特定优先级'}",
        f"",
        f"=== 当前正文 ===",
        draft_text,
        f"=== 正文结束 ===",
        f"",
        f"要求: 保留原文中正确的内容，只修改有问题的地方。直接输出修订后的完整正文。",
    ]

    if context:
        parts.append(f"\n前文上下文:\n{context}")

    return "\n".join(parts)
