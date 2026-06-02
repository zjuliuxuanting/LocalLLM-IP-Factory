"""信源溯源器

在事实核查(S7)之后，将卡片中的关键断言与注册的信源进行关联。
提供完整的溯源报告，用于：
- 纠纷时逐句回溯信源
- 审核时验证事实准确性
- 审计时检查信源引用质量
"""
import re
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from config.settings import rel_to_abs

from config.settings import CARDS_DIR
from src.io.source_registry import get_registry, SourceRecord
from src.utils.logging import get_logger

logger = get_logger("source_tracer")


@dataclass
class TraceRecord:
    card_id: str
    claim: str
    source_id: Optional[str] = None
    source_title: str = ""
    evidence: str = ""         # 信源中的对应原文
    confidence: str = "unverifiable"  # verified | likely | unverifiable | disputed
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "claim": self.claim,
            "source_id": self.source_id,
            "source_title": self.source_title,
            "evidence": self.evidence[:300],
            "confidence": self.confidence,
            "note": self.note,
        }


# ══════════════════════════════════════════════════════════════
# 断言提取与溯源
# ══════════════════════════════════════════════════════════════

def extract_claims(text: str, max_claims: int = 8) -> list[str]:
    """从卡片正文中提取关键事实断言

    优先提取含数字/年份/专名的句子——这些最需要信源支撑。
    """
    sentences = re.split(r'[。！？\n]', text)
    claims = []
    for s in sentences:
        s = s.strip()
        if len(s) < 15 or len(s) > 150:
            continue
        score = 0
        if re.search(r'\d{2,}', s):
            score += 3
        if re.search(r'[A-Z][a-z]{2,}', s):
            score += 2
        if re.search(r'(发现|证明|表明|显示|数据|研究|调查|报告|出版|发表)', s):
            score += 2
        if re.search(r'\d{4}年', s):
            score += 2
        if re.search(r'%|亿美元|万亿|万美元|亿元|万人|万只', s):
            score += 2

        if score >= 2:
            claims.append(s[:150])

    # 去重（相似句子）
    unique = []
    seen_prefixes = set()
    for c in claims:
        prefix = c[:15]
        if prefix not in seen_prefixes:
            unique.append(c)
            seen_prefixes.add(prefix)

    return unique[:max_claims]


def trace_claim_to_source(claim: str, sources: list[SourceRecord]) -> Optional[SourceRecord]:
    """将一个断言匹配到最可能的信源

    策略：关键词重叠 + 实体匹配。
    """
    if not sources:
        return None

    claim_words = set(re.findall(r'[a-zA-Z]{3,}', claim.lower()))
    claim_numbers = set(re.findall(r'\d+', claim))

    best_score = 0
    best_source = None

    for src in sources:
        score = 0
        src_text = f"{src.title} {src.abstract} {' '.join(src.keywords)}".lower()

        # 关键词匹配
        for w in claim_words:
            if w in src_text:
                score += 1

        # 数字匹配
        for n in claim_numbers:
            if n in src_text:
                score += 3

        # 同行评审加分
        if src.quality.get("peer_reviewed"):
            score += 2

        if score > best_score:
            best_score = score
            best_source = src

    return best_source if best_score >= 2 else None


def trace_card(card_id: str, card_text: str = "") -> list[TraceRecord]:
    """对一张卡片执行完整的断言溯源

    1. 提取关键断言
    2. 从注册中心获取卡片关联的信源
    3. 逐条匹配断言到信源
    4. 存储溯源数据
    """
    registry = get_registry()

    if not card_text:
        card_path = CARDS_DIR / f"{card_id}.md"
        if card_path.exists():
            card_text = card_path.read_text(encoding="utf-8")
        else:
            return []

    claims = extract_claims(card_text)
    sources = registry.get_sources_for_card(card_id)

    records = []
    for claim in claims:
        src = trace_claim_to_source(claim, sources)
        if src:
            # 尝试从信源文本中找证据
            evidence = _find_evidence(claim, src)
            confidence = "verified" if len(evidence) > 30 else "likely"
            records.append(TraceRecord(
                card_id=card_id,
                claim=claim,
                source_id=src.source_id,
                source_title=src.title[:80],
                evidence=evidence,
                confidence=confidence,
            ))
        else:
            records.append(TraceRecord(
                card_id=card_id,
                claim=claim,
                confidence="unverifiable",
                note="无匹配信源",
            ))

    # 存储到注册中心
    registry.record_claims(card_id, [r.to_dict() for r in records])

    return records


def _find_evidence(claim: str, source: SourceRecord) -> str:
    """在信源文件中查找与断言相关的原文段落"""
    if not source.cache_path:
        return ""
    cache_file = rel_to_abs(source.cache_path)
    if not cache_file.exists():
        return ""

    try:
        text = cache_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""

    # 提取断言中的关键词
    keywords = re.findall(r'[一-鿿]{2,}|[a-zA-Z]{3,}', claim)
    if not keywords:
        return ""

    # 找包含最多关键词的段落
    paragraphs = re.split(r'\n\s*\n', text)
    best_match = ""
    best_score = 0

    for para in paragraphs:
        para = para.strip()
        if len(para) < 30:
            continue
        score = sum(1 for kw in keywords if kw.lower() in para.lower())
        if score > best_score:
            best_score = score
            best_match = para[:300]

    return best_match if best_score >= 2 else ""


# ══════════════════════════════════════════════════════════════
# 溯源报告
# ══════════════════════════════════════════════════════════════

def generate_trace_report(card_id: str, card_text: str = "") -> dict:
    """生成一张卡片的完整溯源报告

    Returns:
        {
            "card_id": str,
            "generated_at": ISO timestamp,
            "summary": {"total_claims": int, "verified": int, "likely": int, "unverifiable": int},
            "claims": [TraceRecord.to_dict(), ...],
            "sources_used": [source metadata, ...],
        }
    """
    records = trace_card(card_id, card_text)
    registry = get_registry()
    sources = registry.get_sources_for_card(card_id)

    verified = sum(1 for r in records if r.confidence == "verified")
    likely = sum(1 for r in records if r.confidence == "likely")
    unverifiable = sum(1 for r in records if r.confidence == "unverifiable")

    return {
        "card_id": card_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_claims": len(records),
            "verified": verified,
            "likely": likely,
            "unverifiable": unverifiable,
            "verification_rate": f"{verified / max(len(records), 1) * 100:.0f}%",
        },
        "claims": [r.to_dict() for r in records],
        "sources_used": [
            {
                "source_id": s.source_id,
                "title": s.title,
                "type": s.source_type,
                "url": s.url,
                "retrieved_at": s.retrieved_at,
                "peer_reviewed": s.quality.get("peer_reviewed", False),
                "cache_path": s.cache_path,
            }
            for s in sources
        ],
    }
