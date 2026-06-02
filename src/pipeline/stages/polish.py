"""S6 润色阶段

调 douhua 模型做最终文字润色（纯文本）。
"""
from src.pipeline.card_state import CardContext
from src.models.gateway import call_xianka, clean_response
from src.models.prompts.polish import build_polish_prompt
from src.utils.logging import get_logger, log_stage_start, log_stage_done

logger = get_logger("polish")


async def execute(ctx: CardContext, context: str = "") -> CardContext:
    import time; t0 = time.time()
    log_stage_start(ctx.card_id, "S6润色")

    prompt = build_polish_prompt(ctx.card, ctx.revised or ctx.draft)
    raw = call_xianka(prompt, max_tokens=4096, temperature=0.5)
    text = clean_response(raw) if raw else ""

    if not text:
        ctx.polished = ctx.revised or ctx.draft
        logger.warning(f"  ⚠️ {ctx.card_id}: 润色失败，回退")
        return ctx

    ctx.polished = text
    log_stage_done(ctx.card_id, "S6润色", time.time() - t0)
    return ctx
