"""S7 事实核查阶段

调 douhua 模型逐条核查正文中的事实断言与信源的一致性（JSON）。
"""
from src.pipeline.card_state import CardContext
from src.models.gateway import call_douhua
from src.models.prompts.factcheck import build_factcheck_prompt
from src.quality.gate import gate
from src.utils.logging import get_logger

logger = get_logger("factcheck")


async def execute(ctx: CardContext) -> CardContext:
    text = ctx.polished or ctx.revised or ctx.draft
    prompt = build_factcheck_prompt(ctx.card, text, ctx.source_text)
    raw = call_douhua(prompt, max_tokens=2048, temperature=0.2, structured=True)

    if raw is None:
        # 核查失败不阻塞，标记一下
        ctx.factcheck_result = {"factcheck": {"overall_accuracy": 0.5, "risk_level": "cautious"}}
        return ctx

    if isinstance(raw, dict):
        fc = raw
    else:
        ctx.factcheck_result = {"factcheck": {"overall_accuracy": 0.5, "risk_level": "cautious"}}
        return ctx

    ctx.factcheck_result = fc
    ctx.final = text
    return ctx
