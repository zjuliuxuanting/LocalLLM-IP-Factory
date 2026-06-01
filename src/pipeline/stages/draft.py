"""S3 初稿写作阶段

调 xianka 模型基于大纲生成正文（纯文本）。
"""
from src.pipeline.card_state import CardContext
from src.models.gateway import call_xianka, clean_response
from src.models.prompts.draft import build_draft_prompt
from src.quality.gate import gate
from src.utils.logging import get_logger

logger = get_logger("draft")


async def execute(ctx: CardContext, context: str = "") -> CardContext:
    outline = ctx.outline or {}

    prompt = build_draft_prompt(
        card=ctx.card,
        outline=outline,
        retry_num=ctx.draft_retries,
        last_text=ctx.draft,
        context=context,
    )
    raw = call_xianka(prompt, max_tokens=4096, temperature=0.8)
    text = clean_response(raw) if raw else ""

    if not text:
        ctx.mark_failed("S3: 模型返回为空")
        return ctx

    ctx.draft = text
    ok, reason = gate.check_draft(text, ctx.card)
    if not ok:
        if gate.should_retry_stage(ctx.draft_retries):
            ctx.draft_retries += 1
            ctx.stage_retries = ctx.draft_retries
            return await execute(ctx, context)
        ctx.mark_failed(f"S3: 初稿质检失败 — {reason}")
        return ctx

    return ctx
