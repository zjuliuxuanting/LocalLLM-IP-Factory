"""S6 润色阶段

调 douhua 模型做最终文字润色（纯文本）。
"""
from src.pipeline.card_state import CardContext
from src.models.gateway import call_douhua, clean_response
from src.models.prompts.polish import build_polish_prompt
from src.utils.logging import get_logger

logger = get_logger("polish")


async def execute(ctx: CardContext) -> CardContext:
    prompt = build_polish_prompt(ctx.card, ctx.revised or ctx.draft)
    raw = call_douhua(prompt, max_tokens=4096, temperature=0.5)
    text = clean_response(raw) if raw else ""

    if not text:
        # 润色失败不阻塞——回退到修订版
        ctx.polished = ctx.revised or ctx.draft
        return ctx

    ctx.polished = text
    return ctx
