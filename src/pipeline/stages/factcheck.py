"""S7 事实核查阶段

调 douhua 模型逐条核查正文中的事实断言与信源的一致性（JSON）。
"""
from src.pipeline.card_state import CardContext
from src.models.gateway import call_xianka
from src.models.prompts.factcheck import build_factcheck_prompt
from src.quality.gate import gate
from src.utils.logging import get_logger, log_stage_start, log_stage_done

logger = get_logger("factcheck")


async def execute(ctx: CardContext) -> CardContext:
    log_stage_start(ctx.card_id, "S7查证")
    import time; t0 = time.time()
    text = ctx.polished or ctx.revised or ctx.draft
    prompt = build_factcheck_prompt(ctx.card, text, ctx.source_text)
    raw = call_xianka(prompt, max_tokens=2048, temperature=0.2, structured=True)

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

    # 轻拦：高严重度事实错误 → 记入 ctx 并触发重写
    issues = fc.get("factcheck", {}).get("claims_checked", [])
    high_severity = [i for i in issues if i.get("severity") == "high" and not i.get("in_sources", True)]
    if high_severity and gate.should_retry_stage(ctx.draft_retries):
        ctx.draft_retries += 1
        ctx.stage_retries = ctx.draft_retries
        ctx.factcheck_issues = [i["issue"][:200] for i in high_severity[:3]]
        fc_context = "事实核查发现以下问题，请在重写时修正：\n" + "\n".join(f"- {i}" for i in ctx.factcheck_issues)
        logger.warning(f"  ⚠️ {ctx.card_id} 事实错误 {len(high_severity)} 处，重试初稿")
        from src.pipeline.stages.draft import execute as draft_execute
        return await draft_execute(ctx, context=fc_context)

    log_stage_done(ctx.card_id, "S7查证", time.time() - t0)
    return ctx
