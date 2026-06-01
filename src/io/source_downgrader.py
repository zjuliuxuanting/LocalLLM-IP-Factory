"""信源搜索降级链

四层降级 + 每层先查注册中心。不调网络——WebSearch 由 Claude 在 source_dispatcher 中执行。
"""
from pathlib import Path
from src.io.source_registry import get_registry
from src.utils.logging import get_logger

logger = get_logger("downgrader")

ENGINE_FALLBACK = ["pubmed", "wikipedia", "web"]


def downgrade_kw(kw: str, level: int) -> str:
    """按降级级别处理关键词

    L0: 原样  L2: 2-4核心词OR  L3: 最简2词OR
    """
    if level == 0:
        return kw
    words = [w for w in kw.split()
             if len(w) >= 3
             and w.lower() not in ('the','and','for','with','how','are','has',
                                    'was','its','can','not','but','all','from',
                                    'that','this','have','been','about','more','than')]
    if level == 2:
        selected = words[:4]
    elif level == 3:
        selected = words[:2]
    else:
        return kw
    return " OR ".join(selected) if selected else kw


def try_registry(kw: str, card_id: str) -> list[str]:
    """查注册中心。命中 → 返回缓存路径列表。否则 → 空。"""
    registry = get_registry()
    existing = registry.find_by_keyword(kw)
    if existing:
        files = []
        for rec in existing:
            if rec.cache_path and Path(rec.cache_path).exists():
                registry.link_to_card(rec.source_id, card_id)
                files.append(str(rec.cache_path))
        if files:
            logger.info(f"  ✅ registry hit: {len(files)} sources")
            return files
    return []


def get_fallback_kw(kw: str, level: int) -> str:
    """获取某降级级别的搜索词，供 Claude WebSearch 使用"""
    if level == 0:
        return kw
    if level == 1:
        return kw  # 引擎降级，kw 不变
    return downgrade_kw(kw, level)


def get_fallback_engine(original_engine: str, level: int) -> str:
    """获取某降级级别的引擎"""
    if level == 0:
        return original_engine
    if level == 1:
        idx = ENGINE_FALLBACK.index(original_engine) if original_engine in ENGINE_FALLBACK else 0
        return ENGINE_FALLBACK[min(idx + 1, len(ENGINE_FALLBACK) - 1)]
    if level >= 3:
        return "web"
    return ENGINE_FALLBACK[-1]
