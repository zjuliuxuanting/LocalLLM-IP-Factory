"""种子多样性保障引擎

防止大批量生产时陷入模式循环。多层次保障：
  1. 语义去重 — 新种子与已有种子的语义距离
  2. 系列轮转 — 追踪各系列产出比例，优先补充弱势系列
  3. 覆盖度追踪 — 追踪每个系列内子话题的覆盖情况
  4. 反模式检测 — 检测标题/叙事的模板化趋势
  5. 温度调度 — 根据多样性指标动态调整生成温度
"""
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from config.series_definitions import get_target_ratio, get_subtopics, all_series_keys
from src.utils.logging import get_logger

logger = get_logger("seed_diversity")


@dataclass
class DiversityReport:
    """一次多样性检查的综合报告"""
    series_balance: dict = field(default_factory=dict)    # {series: count}
    dominant_series: str = ""
    weakest_series: str = ""
    pattern_alert: bool = False
    pattern_detail: str = ""
    suggested_temperature: float = 0.8
    suggested_series: str = ""
    overall_health: str = "good"  # good | warning | critical


# ══════════════════════════════════════════════════════════════
# 1. 语义去重
# ══════════════════════════════════════════════════════════════

def _ngrams(text: str, n: int = 3) -> set:
    """提取中文 n-gram"""
    chars = re.sub(r'[^一-鿿]', '', text)
    return {chars[i:i+n] for i in range(len(chars) - n + 1)}


def semantic_novelty(title: str, goal: str, existing_seeds: list[dict]) -> float:
    """计算一个新种子与已有种子池的语义新颖度 (0-1, 越高越新)

    使用 n-gram Jaccard 距离。0.0 = 完全重复, 1.0 = 全新。
    """
    if not existing_seeds:
        return 1.0

    new_text = title + goal
    new_ngrams = _ngrams(new_text, 3)

    max_overlap = 0.0
    for s in existing_seeds:
        old_text = s.get("title", "") + s.get("goal", "")
        old_ngrams = _ngrams(old_text, 3)
        if not new_ngrams or not old_ngrams:
            continue
        overlap = len(new_ngrams & old_ngrams) / len(new_ngrams | old_ngrams)
        max_overlap = max(max_overlap, overlap)

    return round(1.0 - max_overlap, 3)


def check_batch_diversity(seeds: list[dict]) -> float:
    """检查一批种子内部的多样性

    Returns:
        批次内平均 pairwise 新颖度 (0-1)
    """
    if len(seeds) <= 1:
        return 1.0

    scores = []
    for i, s1 in enumerate(seeds):
        for s2 in seeds[i+1:]:
            t1 = s1.get("title", "") + s1.get("goal", "")
            t2 = s2.get("title", "") + s2.get("goal", "")
            n1 = _ngrams(t1, 3)
            n2 = _ngrams(t2, 3)
            if n1 and n2:
                overlap = len(n1 & n2) / len(n1 | n2)
                scores.append(1.0 - overlap)

    return round(sum(scores) / len(scores), 3) if scores else 1.0


# ══════════════════════════════════════════════════════════════
# 2. 系列轮转
# ══════════════════════════════════════════════════════════════

# 理想比例从 config/series_definitions 读取，此处不再硬编码
def _target_ratios() -> dict:
    return {k: get_target_ratio(k) for k in all_series_keys()}


def analyze_series_balance(pool: dict) -> DiversityReport:
    """分析种子池的系列平衡度"""
    report = DiversityReport()
    counts = {}

    total = 0
    for series, data in pool.items():
        c = len(data.get("seeds", []))
        counts[series] = c
        total += c

    if total == 0:
        report.series_balance = {s: 0 for s in _target_ratios()}
        report.dominant_series = "N/A"
        report.weakest_series = min(_target_ratios(), key=_target_ratios().get)
        report.overall_health = "critical"
        return report

    report.series_balance = counts

    # 找占比最大的系列
    ratios = {s: c/total for s, c in counts.items()}
    report.dominant_series = max(ratios, key=ratios.get)

    # 找最弱势的系列（相比目标比例差距最大）
    gaps = {}
    for s, target in _target_ratios().items():
        actual = ratios.get(s, 0)
        gaps[s] = target - actual
    report.weakest_series = max(gaps, key=gaps.get)

    # 健康度
    max_deviation = max(
        abs(ratios.get(s, 0) - target)
        for s, target in _target_ratios().items()
    )
    if max_deviation > 0.2:
        report.overall_health = "critical"
    elif max_deviation > 0.1:
        report.overall_health = "warning"
    else:
        report.overall_health = "good"

    report.suggested_series = report.weakest_series

    return report


# ══════════════════════════════════════════════════════════════
# 3. 覆盖度追踪
# ══════════════════════════════════════════════════════════════

# 子话题从 config/series_definitions 读取
def _subtopics(series: str) -> list[str]:
    return get_subtopics(series)


def extract_seed_subtopics(seed: dict) -> list[str]:
    """从一个种子的标题和 goal 中推测覆盖的子话题"""
    text = seed.get("title", "") + seed.get("goal", "")
    found = []
    for topic, keywords in {
        "驯化历史": ["驯化", "起源", "进化", "狼", "祖先"],
        "动物认知": ["认知", "理解", "智力", "思维", "意识"],
        "市场规模": ["市场", "规模", "增长", "融资", "估值"],
        "竞品分析": ["竞品", "对比", "对手", "FluentPet", "品牌"],
        "入门训练": ["入门", "第一步", "新手", "开始", "基础"],
        "翻车现场": ["翻车", "搞笑", "失败", "尴尬", "社死"],
        "创始人": ["创始人", "CEO", "创立", "创业", "故事"],
        "用户故事": ["用户", "主人", "家庭", "体验", "分享"],
        "Bunny叙事": ["Bunny", "网红", "TikTok", "成名"],
    }.items():
        if any(kw in text for kw in keywords):
            found.append(topic)
    return found


def analyze_coverage(series: str, seeds: list[dict]) -> dict:
    """分析一个系列的子话题覆盖度"""
    expected = _subtopics(series)
    covered = set()
    for s in seeds:
        for t in extract_seed_subtopics(s):
            covered.add(t)

    return {
        "expected": len(expected),
        "covered": len(covered),
        "coverage_rate": f"{len(covered)/max(len(expected),1)*100:.0f}%",
        "missing": [t for t in expected if t not in covered],
        "covered_topics": list(covered),
    }


# ══════════════════════════════════════════════════════════════
# 4. 反模式检测
# ══════════════════════════════════════════════════════════════

# 常见的模板化模式（如果大量种子匹配同一模式 → 陷入循环）
TITLE_PATTERNS = [
    (r'^宠物按钮.*(实录|翻车|曝光|揭秘)', "宠物按钮+事件型标题"),
    (r'^当.*(的时候|时)', "当...的时候 句式"),
    (r'^我.*用按钮', "我用按钮... 第一人称"),
    (r'^猫.*vs.*狗', "猫狗对比型"),
    (r'^如果.*会怎样', "假设型标题"),
]


def detect_patterns(seeds: list[dict], threshold: float = 0.3) -> list[str]:
    """检测种子池中的模板化趋势

    Returns:
        告警列表，空列表表示无问题
    """
    if len(seeds) < 10:
        return []

    alerts = []
    titles = [s.get("title", "") for s in seeds]

    for pattern, label in TITLE_PATTERNS:
        matches = sum(1 for t in titles if re.search(pattern, t))
        ratio = matches / len(titles)
        if ratio >= threshold:
            alerts.append(f"{label}: {matches}/{len(titles)} ({ratio:.0%}), 阈值{threshold:.0%}")

    return alerts


# ══════════════════════════════════════════════════════════════
# 5. 温度调度
# ══════════════════════════════════════════════════════════════

def suggest_temperature(series: str, recent_novelty: float,
                        pattern_alerts: list[str]) -> float:
    """根据多样性指标建议生成温度

    多样性充足 → 正常温度 (0.7-0.8)
    出现模式化 → 提高温度 (0.85-0.9)
    """
    base = 0.75

    if pattern_alerts:
        base += 0.1  # 有模板化趋势，提高温度增加随机性

    if recent_novelty < 0.6:
        base += 0.05  # 最近种子太雷同，提高温度

    if series == "S":  # 小说需要更多创意
        base += 0.05

    return round(min(0.95, max(0.6, base)), 2)


# ══════════════════════════════════════════════════════════════
# 综合检查
# ══════════════════════════════════════════════════════════════

def full_diversity_check(pool: dict,
                          recent_seeds: list[dict] = None) -> DiversityReport:
    """运行完整的多样性检查，生成综合报告和建议"""
    report = analyze_series_balance(pool)

    # 检查优势系列的模板化趋势
    if report.dominant_series in pool:
        dom_seeds = pool[report.dominant_series].get("seeds", [])
        patterns = detect_patterns(dom_seeds)
        if patterns:
            report.pattern_alert = True
            report.pattern_detail = "; ".join(patterns)

    # 检查最近一批种子的内部多样性
    if recent_seeds:
        novelty = check_batch_diversity(recent_seeds)
        if novelty < 0.5:
            report.pattern_alert = True
            if report.pattern_detail:
                report.pattern_detail += f"; 批次内新颖度={novelty:.2f}"
            else:
                report.pattern_detail = f"批次内新颖度过低: {novelty:.2f}"

    # 建议温度
    report.suggested_temperature = suggest_temperature(
        report.suggested_series,
        check_batch_diversity(recent_seeds or []),
        detect_patterns(pool.get(report.dominant_series, {}).get("seeds", [])),
    )

    return report
