"""S5 修订阶段

调主模型基于自审结果修订初稿（纯文本）。
"""
from src.pipeline.card_state import CardContext
from src.models.gateway import call_xianka, clean_response
from src.models.prompts.revise import build_revise_prompt
from src.quality.gate import gate
from src.utils.logging import get_logger, log_stage_start, log_stage_done

logger = get_logger("revise")


async def execute(ctx: CardContext, context: str = "") -> CardContext:
    import time; t0 = time.time()
    log_stage_start(ctx.card_id, "S5修订")
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
            logger.warning(f"  ⚠️ {ctx.card_id} 修订验证失败，重试 ({ctx.stage_retries})")
            return await execute(ctx, context)
        ctx.mark_failed(f"S5: 修订验证失败 — {reason}")
        return ctx

    draft_len = len(ctx.draft or "")
    revised_len = len(text)
    delta = revised_len - draft_len
    logger.info(f"  ✏️ {ctx.card_id}: 修订 {draft_len}→{revised_len}字 ({delta:+d})")
    ctx.revised = text
    log_stage_done(ctx.card_id, "S5修订", time.time() - t0)
    return ctx
