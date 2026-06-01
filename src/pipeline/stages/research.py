"""S1 研究阶段 (V3)

纯读缓存，禁止联网。信源文件必须在阶段二已缓存到 shared/。
无缓存 → 标记 source_failed，不继续生成。
"""
from pathlib import Path
from src.pipeline.card_state import CardContext
from src.io.source_registry import get_registry
from src.utils.logging import get_logger

logger = get_logger("research")


async def execute(ctx: CardContext) -> CardContext:
    cid = ctx.card_id
    registry = get_registry()

    # 从注册中心读卡片关联的信源
    sources = registry.get_sources_for_card(cid)

    if not sources:
        # 尝试用卡片 search.query 关键词匹配
        searches = ctx.card.get("search", [])
        if searches:
            query = searches[0].get("query", "")
            matched = registry.find_by_keyword(query)
            for rec in matched:
                if rec.cache_path and Path(rec.cache_path).exists():
                    registry.link_to_card(rec.source_id, cid)
                    sources.append(rec)

    if not sources:
        # 兜底：直接读卡片的 source_files
        for sf in ctx.card.get("source_files", []):
            if Path(sf).exists():
                ctx.source_files.append(sf)
                parts = []
                try:
                    text = Path(sf).read_text(encoding="utf-8", errors="ignore")
                    parts.append(f"[信源:{Path(sf).name}]\n{text[:4000]}")
                except OSError:
                    continue
        ctx.source_text = "\n".join(parts) if parts else ""
        if not ctx.source_text:
            ctx.mark_failed("S1: 无可用信源缓存——该卡片信源未在阶段二准备好")
            return ctx
        logger.info(f"  📚 {cid}: {len(ctx.source_files)} 信源(from source_files), {len(ctx.source_text)} chars")
        return ctx

    # 加载信源文本
    parts = []
    for rec in sources[:5]:
        try:
            text = Path(rec.cache_path).read_text(encoding="utf-8", errors="ignore")
            parts.append(f"[信源:{rec.title[:60]}]\n{text[:4000]}")
        except OSError:
            continue

    ctx.source_files = [rec.cache_path for rec in sources if rec.cache_path]
    ctx.source_text = "\n".join(parts)

    logger.info(f"  📚 {cid}: {len(sources)} 信源, {len(ctx.source_text)} chars")
    return ctx
