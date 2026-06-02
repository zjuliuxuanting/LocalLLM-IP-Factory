"""S2 大纲设计阶段

调 xianka 模型生成结构化内容大纲（JSON）。
"""
from src.pipeline.card_state import CardContext
from src.models.gateway import call_xianka
from src.models.prompts.outline import build_outline_prompt
from src.quality.gate import gate
from src.utils.logging import get_logger

logger = get_logger("outline")


async def execute(ctx: CardContext, context: str = "") -> CardContext:
    prompt = build_outline_prompt(ctx.card, ctx.source_text, context)
    raw = call_xianka(prompt, max_tokens=2048, temperature=0.7, structured=True)

    if raw is None:
        print(f"  ⚠️ {ctx.card_id} S2 模型未返回 JSON，重试...")
        raw = call_xianka(prompt, max_tokens=2048, temperature=0.7, structured=True)

    if raw is None:
        ctx.mark_failed("S2: 模型调用失败")
        return ctx

    if isinstance(raw, dict):
        outline = raw
    else:
        ctx.mark_failed("S2: 无法解析大纲 JSON")
        return ctx

    ok, reason = gate.check_outline(outline)
    if not ok:
        ctx.mark_failed(f"S2: 大纲质检失败 — {reason}")
        return ctx

    ctx.outline = outline
    sec_count = len(outline.get("outline", outline).get("sections", []))
    logger.info(f"S2 大纲通过: {sec_count} sections")
    return ctx
