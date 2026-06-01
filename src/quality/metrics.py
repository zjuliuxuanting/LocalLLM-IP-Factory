"""多维评分引擎

对卡片正文进行 7 个维度的独立打分，返回结构化评分结果。
"""
import re
from dataclasses import dataclass, field
from typing import Optional

from config.rubric import (
    DIMENSIONS, score_length as _len_score,
    PASS_THRESHOLD, WARN_THRESHOLD,
)


@dataclass
class DimensionScore:
    dimension: str
    score: float        # 0-10
    weight: float
    details: str = ""
    hard_gate_fail: bool = False


@dataclass
class QualityResult:
    card_id: str
    dimensions: list[DimensionScore] = field(default_factory=list)
    weighted_total: float = 0.0
    verdict: str = "pass"    # pass | warn | fail
    block_issues: list[str] = field(default_factory=list)
    soft_issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
# 各维度打分函数（纯规则）
# ══════════════════════════════════════════════════════════════

def score_length(text: str, min_chars: int, max_chars: int, section: str = "") -> DimensionScore:
    """字数评分。F 系列（搞笑段子）不启用 hard_gate，段子方向对长度不作硬性要求"""
    actual = len(text)
    s = _len_score(actual, min_chars, max_chars)

    # F 系列是搞笑段子场景，以方向引导为主，不应以文字长短作为硬门禁
    if section == "F":
        hard_gate_fail = False
    else:
        hard_gate_fail = s < 5.0

    return DimensionScore(
        dimension="length",
        score=s,
        weight=0.15,
        details=f"实际 {actual} 字, 要求 {min_chars}-{max_chars}",
        hard_gate_fail=hard_gate_fail,
    )


def score_format(text: str) -> DimensionScore:
    """检查格式违规：代码块、content=、元描述"""
    issues = []
    stripped = text.strip()
    if stripped.startswith("```"):
        issues.append("以代码块开头")
    if "content =" in stripped[:100]:
        issues.append("含 content= 赋值")
    if "with open(" in stripped[:100]:
        issues.append("含 with open(")
    for w in ["完成", "已写入", "让我先", "现在让我"]:
        if w in text[:50]:
            issues.append(f"开头含'{w}'")
            break

    if not issues:
        s = 10.0
    elif len(issues) == 1:
        s = 5.0
    elif len(issues) == 2:
        s = 2.0
    else:
        s = 0.0

    return DimensionScore(
        dimension="format",
        score=s,
        weight=0.10,
        details="; ".join(issues) if issues else "格式合规",
        hard_gate_fail=s < 3.0,
    )


def score_source_alignment(text: str, source_text: str) -> DimensionScore:
    """检查生成内容与信源的实体/年份匹配度"""
    if not source_text or len(source_text) < 100:
        return DimensionScore(
            dimension="source_alignment",
            score=5.0,
            weight=0.20,
            details="无信源或信源内容过少，无法评估",
        )

    source_years = set(re.findall(r'\b(19\d\d|20[0-2]\d)\b', source_text))
    content_years = set(re.findall(r'\b(19\d\d|20[0-2]\d)\b', text))
    year_overlap = len(source_years & content_years) if source_years else 0
    year_ratio = year_overlap / max(len(source_years), 1)

    source_entities = set(re.findall(
        r'\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2}', source_text
    ))
    content_entities = set(re.findall(
        r'\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2}', text
    ))
    entity_overlap = len(source_entities & content_entities) if source_entities else 0
    entity_ratio = entity_overlap / max(len(source_entities), 1)

    combined = (year_ratio * 0.5 + entity_ratio * 0.5)
    s = round(min(10, combined * 12), 1)

    return DimensionScore(
        dimension="source_alignment",
        score=s,
        weight=0.20,
        details=f"年份匹配 {year_ratio:.0%}, 实体匹配 {entity_ratio:.0%}",
        hard_gate_fail=s < 4.0,
    )


def score_style(text: str, expected_style: str) -> DimensionScore:
    """基于文本特征评估风格一致性"""
    features = {}
    issues = []

    sentences = [s.strip() for s in re.split(r'[。！？\n]', text) if s.strip()]
    avg_len = sum(len(s) for s in sentences) / max(len(sentences), 1)
    exclude_ratio = (text.count("！") + text.count("!")) / max(len(text), 1)
    modal_words = ["吧", "吗", "呢", "啊", "哦", "嗯", "呀", "嘛", "啦"]
    modal_ratio = sum(text.count(w) for w in modal_words) / max(len(text), 1)

    if "学术" in expected_style or "严谨" in expected_style:
        if exclude_ratio > 0.01:
            issues.append(f"感叹号过多({exclude_ratio:.3f})")
        if modal_ratio > 0.02:
            issues.append(f"语气词过多({modal_ratio:.3f})")
    elif "幽默" in expected_style or "轻松" in expected_style or "趣味" in expected_style:
        if exclude_ratio < 0.002:
            issues.append(f"可增加感叹号({exclude_ratio:.3f})")
    elif "小说" in expected_style or "故事" in expected_style:
        if avg_len > 50:
            issues.append(f"句子偏长({avg_len:.0f}字/句)")

    s = 10.0 - len(issues) * 3.0
    s = max(0, s)

    return DimensionScore(
        dimension="style",
        score=s,
        weight=0.10,
        details="; ".join(issues) if issues else "风格匹配",
    )


def score_fact_accuracy(text: str, factcheck_result: Optional[dict] = None) -> DimensionScore:
    """事实准确度——优先使用 S7 factcheck 结果"""
    if factcheck_result:
        fc = factcheck_result.get("factcheck", factcheck_result)
        acc = fc.get("overall_accuracy", 0.5)
        risk = fc.get("risk_level", "cautious")
        s = round(acc * 10, 1)
        if risk == "risky":
            s = min(s, 5.0)
        return DimensionScore(
            dimension="fact_accuracy",
            score=s,
            weight=0.25,
            details=f"准确率 {acc:.0%}, 风险{risk}",
            hard_gate_fail=s < 5.0,
        )
    return DimensionScore(
        dimension="fact_accuracy",
        score=5.0,
        weight=0.25,
        details="未执行事实核查",
    )


def score_coherence(text: str, prev_card_text: str = "") -> DimensionScore:
    """与前一卡片的连贯性（纯文本特征）"""
    if not prev_card_text:
        return DimensionScore(
            dimension="coherence",
            score=7.0,
            weight=0.10,
            details="无前文参考，默认通过",
        )
    # 简单检查关键词重叠但不完全相同
    prev_words = set(re.findall(r'[一-鿿]{2,4}', prev_card_text))
    card_words = set(re.findall(r'[一-鿿]{2,4}', text))
    overlap = len(prev_words & card_words) / max(len(card_words), 1)
    # 有少量重叠是好的（话题延续），太多是重复
    s = 10.0 if 0.05 <= overlap <= 0.3 else 7.0 if overlap <= 0.5 else 4.0
    return DimensionScore(
        dimension="coherence",
        score=s,
        weight=0.10,
        details=f"词重叠率 {overlap:.0%}",
    )


def score_novelty(text: str, series_texts: list[str]) -> DimensionScore:
    """与同系列卡片的重复度"""
    if not series_texts:
        return DimensionScore(
            dimension="novelty",
            score=10.0,
            weight=0.10,
            details="同系列无其他卡片",
        )
    text_sents = set(
        s.strip() for s in re.split(r'[。！？\n]', text)
        if len(s.strip()) > 8
    )
    if not text_sents:
        return DimensionScore(dimension="novelty", score=5.0, weight=0.10, details="文本过短")
    max_overlap = 0
    for other in series_texts:
        other_sents = set(
            s.strip() for s in re.split(r'[。！？\n]', other)
            if len(s.strip()) > 8
        )
        if not other_sents:
            continue
        overlap = len(text_sents & other_sents) / len(text_sents)
        max_overlap = max(max_overlap, overlap)
    s = round(10 - max_overlap * 12, 1)
    s = max(0, min(10, s))
    return DimensionScore(
        dimension="novelty",
        score=s,
        weight=0.10,
        details=f"最高重复率 {max_overlap:.0%}",
    )


# ══════════════════════════════════════════════════════════════
# 综合评分
# ══════════════════════════════════════════════════════════════

def compute_verdict(scores: list[DimensionScore]) -> tuple[str, list[str], list[str]]:
    """基于所有维度评分计算最终判定"""
    block = []
    soft = []

    for ds in scores:
        if ds.hard_gate_fail:
            block.append(f"[{ds.dimension}] {ds.details} (hard gate fail)")
        # 检查软门禁
        dim_spec = next((d for d in DIMENSIONS if d.name == ds.dimension), None)
        if dim_spec and dim_spec.soft_gate is not None and ds.score < dim_spec.soft_gate:
            soft.append(f"[{ds.dimension}] {ds.details} (soft gate: {ds.score}<{dim_spec.soft_gate})")

    weighted = sum(ds.score * ds.weight for ds in scores)
    weighted = round(weighted, 1)

    if block:
        verdict = "fail"
    elif weighted >= PASS_THRESHOLD:
        verdict = "pass"
    elif weighted >= WARN_THRESHOLD:
        verdict = "warn"
    else:
        verdict = "fail"

    return verdict, block, soft


def evaluate(
    text: str,
    card: dict,
    source_text: str = "",
    prev_card_text: str = "",
    series_texts: list[str] = None,
    factcheck_result: dict = None,
    stage: str = "final",
) -> QualityResult:
    """对一张卡片执行完整评分"""
    from config.rubric import STAGE_CHECKS

    active = STAGE_CHECKS.get(stage, STAGE_CHECKS["final"])
    dims = []

    min_c = card.get("min_chars", 300)
    max_c = card.get("max_chars", 600)
    style = card.get("style", "")
    section = card.get("section", "")

    for dim_name in active:
        if dim_name == "length":
            dims.append(score_length(text, min_c, max_c, section))
        elif dim_name == "format":
            dims.append(score_format(text))
        elif dim_name == "source_alignment":
            dims.append(score_source_alignment(text, source_text))
        elif dim_name == "fact_accuracy":
            dims.append(score_fact_accuracy(text, factcheck_result))
        elif dim_name == "style":
            dims.append(score_style(text, style))
        elif dim_name == "coherence":
            dims.append(score_coherence(text, prev_card_text))
        elif dim_name == "novelty":
            dims.append(score_novelty(text, series_texts or []))

    verdict, block, soft = compute_verdict(dims)
    weighted = round(sum(ds.score * ds.weight for ds in dims), 1)

    return QualityResult(
        card_id=card["id"],
        dimensions=dims,
        weighted_total=weighted,
        verdict=verdict,
        block_issues=block,
        soft_issues=soft,
        suggestions=[b.split("] ", 1)[-1] if "] " in b else b for b in block]
                  + [s.split("] ", 1)[-1] if "] " in s else s for s in soft],
    )
