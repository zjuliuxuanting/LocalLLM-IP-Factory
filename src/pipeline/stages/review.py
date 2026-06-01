"""S4 自审阶段

调 douhua 模型对初稿进行多维度自审（JSON）。
自审结果用于指导 S5 修订，即使判 fail 也继续推进——由 S5 来修改。
"""
from src.pipeline.card_state import CardContext
from src.models.gateway import call_douhua
from src.models.prompts.review import build_review_prompt
from src.quality.gate import gate
from src.utils.logging import get_logger

logger = get_logger("review")


async def execute(ctx: CardContext) -> CardContext:
    prompt = build_review_prompt(ctx.card, ctx.draft, ctx.source_text)
    raw = call_douhua(prompt, max_tokens=2048, temperature=0.3, structured=True)

    if raw is None:
        # 自审调用失败不阻断，用空 review 继续
        ctx.review_result = {"review": {"factual_issues": [], "style_issues": [],
                                         "coherence_issues": [], "verdict": "warn",
                                         "revision_priority": ["检查事实准确性"]}}
        return ctx

    if isinstance(raw, dict):
        review = raw
    else:
        ctx.review_result = {"review": {"factual_issues": [], "style_issues": [],
                                         "coherence_issues": [], "verdict": "warn"}}
        return ctx

    # 无论自审判定如何，都继续推进到 S5 修订
    # S5 会利用 review 中的 issues 来修改
    ctx.review_result = review
    return ctx
