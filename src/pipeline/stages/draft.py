"""S3 初稿写作阶段

调主模型基于大纲生成正文（纯文本）。
"""
from src.pipeline.card_state import CardContext
from src.models.gateway import call_xianka, clean_response
from src.models.prompts.draft import build_draft_prompt
from src.quality.gate import gate
from src.utils.logging import get_logger, log_stage_start, log_stage_done

logger = get_logger("draft")


async def execute(ctx: CardContext, context: str = "") -> CardContext:
    log_stage_start(ctx.card_id, "S3初稿")
    outline = ctx.outline or {}
    import time; t0 = time.time()

    prompt = build_draft_prompt(
        card=ctx.card,
        outline=outline,
        source_text=ctx.source_text,
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
        print(f"    [draft] 质检失败: {reason}")
        print(f"    [draft] 草稿前200字: {text[:200].replace(chr(10), ' ')}")
        if gate.should_retry_stage(ctx.draft_retries):
            ctx.draft_retries += 1
            ctx.stage_retries = ctx.draft_retries
            return await execute(ctx, context)
        ctx.mark_failed(f"S3: 初稿质检失败 — {reason}")
        return ctx

    log_stage_done(ctx.card_id, "S3初稿", time.time() - t0)
    return ctx
