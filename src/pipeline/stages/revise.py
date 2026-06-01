"""S5 修订阶段

调 xianka 模型基于自审结果修订初稿（纯文本）。
"""
from src.pipeline.card_state import CardContext
from src.models.gateway import call_xianka, clean_response
from src.models.prompts.revise import build_revise_prompt
from src.quality.gate import gate
from src.utils.logging import get_logger

logger = get_logger("revise")


async def execute(ctx: CardContext, context: str = "") -> CardContext:
    review = ctx.review_result or {}

    prompt = build_revise_prompt(ctx.card, ctx.draft, review, context)
    raw = call_xianka(prompt, max_tokens=4096, temperature=0.7)
    text = clean_response(raw) if raw else ""

    if not text:
        ctx.mark_failed("S5: 修订版为空")
        return ctx

    ok, reason = gate.check_revision(
        ctx.draft, text,
        review.get("review", review).get("revision_priority", []),
    )
    if not ok:
        if gate.should_retry_stage(ctx.stage_retries):
            ctx.stage_retries += 1
            return await execute(ctx, context)
        ctx.mark_failed(f"S5: 修订验证失败 — {reason}")
        return ctx

    ctx.revised = text
    return ctx
