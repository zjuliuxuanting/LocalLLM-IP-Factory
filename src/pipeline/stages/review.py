"""S4 自审阶段

调辅助模型对初稿进行多维度自审（JSON）。
自审结果用于指导 S5 修订，即使判 fail 也继续推进——由 S5 来修改。
"""
from src.pipeline.card_state import CardContext
from src.models.gateway import call_xianka, clean_response
from src.models.prompts.review import build_review_prompt
from src.quality.gate import gate
from src.utils.logging import get_logger, log_stage_start, log_stage_done

logger = get_logger("review")


async def execute(ctx: CardContext, context: str = "") -> CardContext:
    import time; t0 = time.time()
    log_stage_start(ctx.card_id, "S4自审")

    prompt = build_review_prompt(ctx.card, ctx.draft, ctx.source_text)
    raw = call_xianka(prompt, max_tokens=2048, temperature=0.3, structured=True)

    if raw is None:
        logger.info(f"  🔍 {ctx.card_id}: 自审调用失败，跳过")
        ctx.review_result = {"review": {"factual_issues": [], "style_issues": [],
                                         "coherence_issues": [], "verdict": "warn",
                                         "revision_priority": ["检查事实准确性"]}}
        return ctx

    if not isinstance(raw, dict):
        ctx.review_result = {"review": {"factual_issues": [], "style_issues": [],
                                         "coherence_issues": [], "verdict": "warn"}}
        return ctx

    review = raw.get("review", raw)
    f_issues = len(review.get("factual_issues", []))
    s_issues = len(review.get("style_issues", []))
    c_issues = len(review.get("coherence_issues", []))
    verdict = review.get("verdict", "?")
    logger.info(f"  🔍 {ctx.card_id}: 自审 {verdict} | 事实{f_issues} 风格{s_issues} 连贯{c_issues}")

    ctx.review_result = raw
    log_stage_done(ctx.card_id, "S4自审", time.time() - t0)
    return ctx
