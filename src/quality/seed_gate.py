"""种子质量门禁

在种子进入 seed_pool.json 之前执行多维验证。
不合格的种子标记问题并拒绝入池，防止低质种子浪费 GPU 资源。
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from src.io.source_validator import validate_seed_source
from config.series_definitions import get_source_policy
from src.utils.logging import get_logger

logger = get_logger("seed_gate")


@dataclass
class SeedGateResult:
    passed: bool
    seed_title: str
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float = 0.0
    source_ok: Optional[bool] = None
    tier: str = "expansion"  # core | expansion | experimental


# ══════════════════════════════════════════════════════════════
# 原子检查函数
# ══════════════════════════════════════════════════════════════

def _check_goal_actionable(goal: str) -> tuple[bool, str]:
    """goal 必须是可执行的写作目标，不能是标签"""
    if not goal or len(goal) < 15:
        return False, f"goal 过短 ({len(goal)} 字)，无法指导写作"
    # 标签型 goal（只是主题词，没有动作描述）
    label_patterns = [
        r'^(幽默|娱乐|猎奇|科普|轻松|反转|真相|搞笑|暖心|实用|盘点)$',
        r'^(幽默|娱乐|猎奇|科普)\+',
        r'^[A-Za-z\s]+$',  # 纯英文
    ]
    for pat in label_patterns:
        if re.match(pat, goal.strip()):
            return False, f"goal 是标签而非写作目标: '{goal.strip()}'"
    # 好 goal 的特征：含动作词或目标描述
    action_words = ['写', '介绍', '分析', '讲述', '展示', '说明', '探讨', '对比',
                    '创作', '还原', '揭秘', '论证', '盘点', '描述', '记录',
                    '让', '以', '通过', '从', '用', '基于', '结合']
    has_action = any(w in goal for w in action_words)
    if not has_action:
        return False, f"goal 缺少动作词，不像可执行目标: '{goal[:30]}...'"
    return True, "OK"


def _check_kw_quality(kw: str, engine: str) -> tuple[bool, str]:
    """搜索关键词质量检查"""
    if not kw or len(kw.strip()) < 3:
        return False, "搜索词过短"
    # 检查是否含中文（LLM有时生成中文 kw，DuckDuckGo 搜不到）
    if re.search(r'[\u4e00-\u9fff]', kw):
        return False, f"kw 含中文，搜索引擎无法检索: '{kw[:40]}'"
    if engine == "web" and len(kw.split()) < 2:
        return False, f"Web 搜索需要至少 2 个词: '{kw}'"
    if engine in ("pubmed", "arxiv") and len(kw.split()) < 2:
        return False, f"学术搜索需要精确关键词 (≥2词): '{kw}'"
    # 检查是否是通用无意义词
    noise_words = {"test", "hello", "keyword", "search", "query", "example"}
    if set(kw.lower().split()) & noise_words:
        return False, f"搜索词含无意义通用词: '{kw}'"
    return True, "OK"


def _check_title_unique(title: str, existing_titles: list[str]) -> tuple[bool, str]:
    """标题去重检查"""
    # 精确匹配
    if title in existing_titles:
        return False, f"标题重复: '{title[:40]}'"
    # 模糊匹配（前 10 个字相同）
    prefix = title[:10]
    for et in existing_titles:
        if et[:10] == prefix:
            return False, f"标题前10字与已有种子重复: '{et[:30]}' ↔ '{title[:30]}'"
    return True, "OK"


def _check_title_engagement(title: str) -> tuple[bool, str]:
    """标题吸引力检查"""
    if len(title) < 6:
        return False, "标题过短 (<6字)"
    if len(title) > 60:
        return False, f"标题过长 ({len(title)}字 > 60)"
    # 检查是否有吸引力元素
    engagement = ['？', '?', '！', '!', '：', ':', '——']
    has_engagement = any(c in title for c in engagement)
    if not has_engagement and len(title) > 15:
        # 较长的标题如果没有标点分隔，可能不够吸引人—只给 warning
        return True, "OK (建议增加标点或问句增强吸引力)"
    return True, "OK"


# ══════════════════════════════════════════════════════════════
# 主题门禁
# ══════════════════════════════════════════════════════════════

def inspect_seed(
    seed: dict,
    series: str,
    existing_titles: list[str],
    check_source: bool = True,
) -> SeedGateResult:
    """对单个种子执行完整质量门禁

    Args:
        seed: 候选种子 {"title","goal","engine","kw"}
        series: 所属系列
        existing_titles: 已有种子标题列表
        check_source: 是否执行信源验证（生产环境应为 True）

    Returns:
        SeedGateResult 含通过/失败、问题列表、评分和分级
    """
    title = seed.get("title", "")
    goal = seed.get("goal", "")
    engine = seed.get("engine", "web")
    kw = seed.get("kw", "")

    issues = []
    warnings = []
    score = 10.0
    tier = "expansion"

    # 1. goal 可执行性 (权重高)
    ok, msg = _check_goal_actionable(goal)
    if not ok:
        issues.append(f"[goal] {msg}")
        score -= 4
    elif len(goal) >= 30:
        score += 1  # 详细 goal 加分

    # 2. kw 质量
    ok, msg = _check_kw_quality(kw, engine)
    if not ok:
        issues.append(f"[kw] {msg}")
        score -= 3

    # 3. 标题去重
    ok, msg = _check_title_unique(title, existing_titles)
    if not ok:
        issues.append(f"[title] {msg}")
        score -= 3

    # 4. 标题吸引力
    ok, msg = _check_title_engagement(title)
    if not ok:
        warnings.append(f"[title] {msg}")
        score -= 1

    # 5. 信源验证（对事实类系列关键）
    source_ok = None
    if check_source and kw:
        source_result = validate_seed_source(series, kw, engine)
        source_ok = source_result.available
        if not source_result.available:
            policy = get_source_policy(series)
            if policy == "required":
                issues.append(
                    f"[source] 强制信源验证失败: {source_result.error} | "
                    f"kw='{kw}' engine={engine}"
                )
                score -= 3
            else:
                warnings.append(
                    f"[source] 信源暂不可用: {source_result.error}"
                )
                score -= 1
        else:
            # 信源可用，记录样本
            score += 0.5

    # 6. 分级判断
    if not issues and len(goal) >= 30 and source_ok:
        tier = "core"
    elif not issues:
        tier = "expansion"
    else:
        tier = "experimental"

    passed = len(issues) == 0
    score = round(max(0, min(10, score)), 1)

    return SeedGateResult(
        passed=passed,
        seed_title=title,
        issues=issues,
        warnings=warnings,
        score=score,
        source_ok=source_ok,
        tier=tier,
    )


def filter_seeds(
    seeds: list[dict],
    series: str,
    existing_titles: list[str],
    min_score: float = 5.0,
    check_source: bool = True,
) -> tuple[list[dict], list[SeedGateResult]]:
    """批量筛选种子

    Returns:
        (通过的种子列表, 所有种子的gate结果)
    """
    accepted = []
    results = []

    for seed in seeds:
        result = inspect_seed(seed, series, existing_titles, check_source)
        results.append(result)
        if result.passed and result.score >= min_score:
            accepted.append(seed)
            existing_titles.append(seed["title"])  # 同一批次内去重

    return accepted, results
