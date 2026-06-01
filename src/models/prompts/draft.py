"""S3 初稿写作 prompt

基于大纲和信源生成正文。这是唯一输出纯文本（非 JSON）的阶段。
"""
import json


DRAFT_SYSTEM = """根据以下大纲和信源材料撰写卡片正文。

要求：
- 严格基于下面提供的信源材料写作，大量引用其中的事实和数据
- 不要写"完成""已写入""输出""让我""首先"等元描述词
- 不要用代码块包裹（不要 ``` 符号）
- 不要包在 Python 代码里（不要 content = 不要 with open）
- 第一句话就是正文，不要前缀标题
- 直接从正文第一个字写到最后一个字，其他一概不要"""


def build_draft_prompt(
    card: dict,
    outline: dict,
    source_text: str = "",
    retry_num: int = 0,
    last_text: str = "",
    context: str = "",
) -> str:
    cid = card["id"]
    min_c = card.get("min_chars", 300)
    max_c = card.get("max_chars", 600)
    style = card.get("style", "")
    subsection = card.get("subsection", "")

    # 从大纲中提取叙事指引
    outline_data = outline.get("outline", outline)
    narrative = outline_data.get("narrative_arc", "")
    sections = outline_data.get("sections", [])
    section_guide = "\n".join(
        f"  {s.get('heading', '')}: {'; '.join(s.get('key_points', []))}"
        for s in sections
    )

    parts = [
        DRAFT_SYSTEM,
        f"",
        f"根据以下大纲和信源材料撰写卡片正文。直接输出纯文本，不要任何包装。",
        f"",
        f"卡片: {cid} | {subsection}",
        f"期望风格: {style}",
        f"字数: {min_c}-{max_c} 字",
    ]

    # 信源材料——写稿的核心依据
    if source_text:
        parts.append(f"")
        parts.append(f"=== 信源材料（必须引用其中的事实和数据）===")
        parts.append(source_text[:6000])
        parts.append(f"")
        parts.append(f"=== 信源结束 ===")

    parts.extend([
        f"",
        f"叙事线索: {narrative}",
        f"",
        f"大纲结构:",
        section_guide,
        f"",
        f"要求: 严格遵循大纲结构展开内容，不要遗漏任何 key_point。",
        f"每个部分必须引用信源材料中的具体事实、数据或研究结论。",
    ])

    if context:
        parts.append(f"\n前文上下文（参考，不要重复）:\n{context}")

    # 重试改进指令
    if retry_num >= 1 and last_text:
        reasons = []
        if len(last_text) <= 200:
            reasons.append(f"太短（只有{len(last_text)}字，需要>{min_c}字），请展开写")
        if "完成" in last_text[:50] or "已写入" in last_text[:50]:
            reasons.append("开头出现了禁词'完成'/'已写入'，直接从正文开始")
        if last_text.startswith("```") or "content =" in last_text[:100]:
            reasons.append("被代码块包裹了，请输出纯文字不要包在 ``` 或 Python 代码里")
        if not reasons:
            reasons.append("请确保：纯正文、够字数、有事实引用、无禁词、不用代码格式")
        parts.append(f"\n🔧 重试——上次失败原因:\n" + "\n".join(f"- {r}" for r in reasons))

    return "\n".join(parts)
