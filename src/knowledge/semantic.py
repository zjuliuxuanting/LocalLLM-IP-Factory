"""语义边管理与存量补建

知识图谱的语义关系维护——批量补建、去重、统计。
"""
import re
from pathlib import Path

from config.settings import (
    DRAFTS_DIR, KG_SEMANTIC_BATCH_SIZE, KG_MAX_CARD_CONTENT,
)
from src.io.store import get_nodes_store, get_edges_store, get_semantic_state_store
from src.models.gateway import call_kg_structured
from src.utils.logging import get_logger

logger = get_logger("semantic")


def batch_build_semantic(batch_size: int = KG_SEMANTIC_BATCH_SIZE) -> dict:
    """存量批量补建语义边（纯本地模型）

    Returns:
        {"next_added": int, "semantic_added": int, "remaining": int}
    """
    nodes_store = get_nodes_store()
    edges_store = get_edges_store()
    state_store = get_semantic_state_store()

    nodes = nodes_store.read()
    edges = edges_store.read()
    state = state_store.read()

    # 1. 自动 next 边
    from src.knowledge.graph import build_next_edges
    next_edges = build_next_edges(nodes, edges)
    next_added = 0
    if next_edges:
        edges.extend(next_edges)
        edges_store.write(edges)
        next_added = len(next_edges)

    # 2. 语义边
    pairs = _get_unprocessed_pairs(nodes, edges, state)
    if not pairs:
        return {"next_added": next_added, "semantic_added": 0, "remaining": 0}

    batch = pairs[:batch_size]
    new_semantic = 0

    for aid, bid in batch:
        text_a = _read_card_text(aid)
        text_b = _read_card_text(bid)
        if not text_a or not text_b:
            state["processed_pairs"].append([aid, bid])
            continue

        from src.knowledge.graph import _classify_prompt
        prompt = _classify_prompt(aid, text_a, bid, text_b)
        result = call_kg_structured(prompt)
        if result and result.get("relation") != "none":
            edges.append({
                "edge_id": f"{aid}_{bid}_{result['relation']}",
                "from": aid,
                "to": bid,
                "type": result["relation"],
                "weight": result.get("weight", 0.5),
                "reason": result.get("reason", ""),
            })
            new_semantic += 1

        state["processed_pairs"].append([aid, bid])

    if new_semantic:
        edges_store.write(edges)
        state["total_semantic"] = state.get("total_semantic", 0) + new_semantic

    state_store.write(state)
    remaining = len(pairs) - len(batch)

    return {
        "next_added": next_added,
        "semantic_added": new_semantic,
        "remaining": remaining,
    }


def _get_unprocessed_pairs(nodes: list, edges: list, state: dict) -> list:
    """获取待分析的卡片对"""
    processed = set()
    for p in state.get("processed_pairs", []):
        processed.add(tuple(sorted(p)))

    by_chapter: dict[str, list[str]] = {}
    for n in nodes:
        cid = n["id"]
        parts = cid.split("-")
        chapter = "-".join(parts[:2]) if len(parts) >= 2 else cid
        by_chapter.setdefault(chapter, []).append(cid)

    pairs = []
    # 小章节内全量比对
    for chapter, cards in by_chapter.items():
        if len(cards) > 10:
            continue
        for i in range(len(cards)):
            for j in range(i + 1, len(cards)):
                pair = tuple(sorted([cards[i], cards[j]]))
                if pair not in processed:
                    pairs.append(pair)

    if pairs:
        return pairs

    # 大章节关键词匹配
    node_map = {n["id"]: n for n in nodes}
    for chapter, cards in by_chapter.items():
        if len(cards) <= 10:
            continue
        card_kw = {}
        for cid in cards:
            n = node_map.get(cid, {})
            kw = set()
            for field in ["subsection", "goal", "name"]:
                text = n.get(field, "")
                for w in re.findall(r'[一-鿿]{2,4}', text):
                    kw.add(w)
            card_kw[cid] = kw
        for i, ca in enumerate(cards):
            kwa = card_kw.get(ca, set())
            matches = []
            for cb in cards[i + 1:]:
                kwb = card_kw.get(cb, set())
                shared = kwa & kwb
                if shared:
                    pair = tuple(sorted([ca, cb]))
                    if pair not in processed:
                        matches.append((len(shared), pair))
            matches.sort(reverse=True)
            for _, pair in matches[:5]:
                pairs.append(pair)

    return pairs


def _read_card_text(card_id: str) -> str:
    """读取卡片正文"""
    for d in [DRAFTS_DIR, Path(str(DRAFTS_DIR).replace("drafts", "cards"))]:
        p = d / f"{card_id}.md"
        if p.exists():
            return p.read_text(encoding="utf-8")[:KG_MAX_CARD_CONTENT]
    return ""
