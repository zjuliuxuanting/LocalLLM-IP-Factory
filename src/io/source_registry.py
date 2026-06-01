"""信源注册中心

管理所有外部信源的结构化元数据，提供：
- 跨卡共享去重：同一信源不重复抓取
- 来源溯源：记录抓取时间/URL/内容摘要/关键词
- 反向索引：从卡片查信源、从信源查卡片
- 质量标注：同行评审/可信度/完整度

所有信源数据存在 data/source_registry/ 下。
"""
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import PROJECT_ROOT, CACHE_DIR
from src.io.store import AtomicJsonStore

# ── 注册中心路径 ──
REGISTRY_DIR = PROJECT_ROOT / "data" / "source_registry"
REGISTRY_INDEX = REGISTRY_DIR / "index.json"       # 信源ID → 元数据
REGISTRY_CLAIMS = REGISTRY_DIR / "claims.json"     # 卡片ID → claim列表
REGISTRY_SHARED = CACHE_DIR / "shared"             # 共享缓存目录


@dataclass
class SourceRecord:
    """单条信源的结构化记录"""
    source_id: str                          # 唯一ID，如 src_pubmed_38291023
    source_type: str                        # pubmed | arxiv | wikipedia | web | paper
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    journal: str = ""
    url: str = ""
    retrieved_at: str = ""                  # ISO时间戳
    cache_path: str = ""                    # 缓存文件路径（相对PROJECT_ROOT）
    content_hash: str = ""                  # sha256 前16位
    content_length: int = 0
    keywords: list[str] = field(default_factory=list)
    abstract: str = ""                      # 前500字摘要
    used_by: list[str] = field(default_factory=list)  # 引用此信源的卡片ID列表
    quality: dict = field(default_factory=lambda: {
        "peer_reviewed": False,
        "relevance_score": 0.0,
        "completeness": "unknown",          # full_text | abstract | summary | snippet
    })

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SourceRecord":
        return cls(**{k: d.get(k, v.default if hasattr(v, 'default') else None)
                      for k, v in cls.__dataclass_fields__.items()})


class SourceRegistry:
    """信源注册中心"""

    def __init__(self):
        self._index_store = AtomicJsonStore(REGISTRY_INDEX, {})
        self._claims_store = AtomicJsonStore(REGISTRY_CLAIMS, {})
        REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        REGISTRY_SHARED.mkdir(parents=True, exist_ok=True)

    # ══════════════════════════════════════════════════════════
    # 信源 CRUD
    # ══════════════════════════════════════════════════════════

    def register(self, record: SourceRecord) -> str:
        """注册一条新信源，返回 source_id"""
        if not record.retrieved_at:
            record.retrieved_at = datetime.now(timezone.utc).isoformat()
        index = self._index_store.read()
        index[record.source_id] = record.to_dict()
        self._index_store.write(index)
        return record.source_id

    def get(self, source_id: str) -> Optional[SourceRecord]:
        index = self._index_store.read()
        d = index.get(source_id)
        return SourceRecord.from_dict(d) if d else None

    def exists(self, source_id: str) -> bool:
        return source_id in self._index_store.read()

    def link_to_card(self, source_id: str, card_id: str) -> None:
        """将信源关联到卡片"""
        index = self._index_store.read()
        if source_id in index:
            used = set(index[source_id].get("used_by", []))
            used.add(card_id)
            index[source_id]["used_by"] = sorted(used)
            self._index_store.write(index)

    def find_by_keyword(self, keyword: str) -> list[SourceRecord]:
        """按关键词搜索已缓存的信源（避免重复抓取）"""
        index = self._index_store.read()
        results = []
        for d in index.values():
            all_text = f"{d.get('title','')} {' '.join(d.get('keywords',[]))}"
            if keyword.lower() in all_text.lower():
                results.append(SourceRecord.from_dict(d))
        return results

    def find_by_content_hash(self, content: str) -> Optional[str]:
        """通过内容哈希查找已有信源"""
        h = _hash_content(content)
        index = self._index_store.read()
        for sid, d in index.items():
            if d.get("content_hash") == h:
                return sid
        return None

    def get_cards_using_source(self, source_id: str) -> list[str]:
        """反向索引：哪些卡片引用了此信源"""
        rec = self.get(source_id)
        return rec.used_by if rec else []

    def get_sources_for_card(self, card_id: str) -> list[SourceRecord]:
        """获取一张卡片引用的所有信源"""
        index = self._index_store.read()
        results = []
        for d in index.values():
            if card_id in d.get("used_by", []):
                results.append(SourceRecord.from_dict(d))
        return results

    # ══════════════════════════════════════════════════════════
    # Claim 溯源
    # ══════════════════════════════════════════════════════════

    def record_claims(self, card_id: str, claims: list[dict]) -> None:
        """记录一张卡片中的所有断言及其信源关联

        claims: [{"claim": "...", "sources": ["src_xxx"], "confidence": "verified|likely|unverifiable"}]
        """
        all_claims = self._claims_store.read()
        all_claims[card_id] = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "claims": claims,
        }
        self._claims_store.write(all_claims)

    def get_claims(self, card_id: str) -> Optional[dict]:
        return self._claims_store.read().get(card_id)

    def get_trace_report(self, card_id: str) -> dict:
        """生成一张卡片的完整溯源报告

        用于纠纷时快速定位每句话的信源。
        """
        claims_data = self.get_claims(card_id)
        sources = self.get_sources_for_card(card_id)

        return {
            "card_id": card_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "claims_traced": len(claims_data.get("claims", [])) if claims_data else 0,
            "claims": claims_data.get("claims", []) if claims_data else [],
            "sources": [{
                "source_id": s.source_id,
                "title": s.title,
                "url": s.url,
                "retrieved_at": s.retrieved_at,
                "type": s.source_type,
                "peer_reviewed": s.quality.get("peer_reviewed", False),
                "cache_path": s.cache_path,
            } for s in sources],
        }

    # ══════════════════════════════════════════════════════════
    # 统计
    # ══════════════════════════════════════════════════════════

    def stats(self) -> dict:
        index = self._index_store.read()
        claims = self._claims_store.read()
        type_dist = {}
        total_cards = set()
        for d in index.values():
            t = d.get("source_type", "unknown")
            type_dist[t] = type_dist.get(t, 0) + 1
            total_cards.update(d.get("used_by", []))

        return {
            "total_sources": len(index),
            "total_cards_with_sources": len(total_cards),
            "total_claims_traced": sum(
                len(c.get("claims", [])) for c in claims.values()
            ),
            "source_types": type_dist,
        }


# ── 工具 ──

def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def make_source_id(source_type: str, identifier: str) -> str:
    """生成规范的信源ID，如 src_pubmed_38291023"""
    safe_id = identifier.replace("/", "_").replace(" ", "_")[:40]
    return f"src_{source_type}_{safe_id}"


# ── 单例 ──

_registry: Optional[SourceRegistry] = None


def get_registry() -> SourceRegistry:
    global _registry
    if _registry is None:
        _registry = SourceRegistry()
    return _registry
