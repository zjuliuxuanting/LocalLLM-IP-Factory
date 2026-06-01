"""知识图谱操作

节点管理、自动边生成、批量语义边构建。
"""
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import (
    NODES_FILE, EDGES_FILE, SEMANTIC_STATE_FILE,
    DRAFTS_DIR, KG_SEMANTIC_BATCH_SIZE, KG_MAX_CARD_CONTENT,
)
from src.io.store import (
    get_nodes_store, get_edges_store, get_semantic_state_store,
)
from src.models.gateway import call_kg, call_kg_structured


def update_graph(card: dict, source_files: list[str]) -> None:
    """卡片产出后更新知识图谱"""
    cid = card["id"]
    nodes_store = get_nodes_store()
    edges_store = get_edges_store()

    nodes = nodes_store.read()
    edges = edges_store.read()

    # 更新/创建卡片节点
    new_node = {
        "id": cid,
        "name": card.get("subsection", ""),
        "type": card.get("node_type", "card"),
        "subsection": card.get("subsection", ""),
        "goal": card.get("goal", ""),
        "section": cid.split("-")[0] if "-" in cid else "",
        "updated": datetime.now().isoformat(),
    }
    existing = [n for n in nodes if n["id"] == cid]
    if existing:
        existing[0].update(new_node)
    else:
        nodes.append(new_node)

    # 信源引用边
    for fp in source_files:
        sname = os.path.basename(fp).rsplit(".", 1)[0][:40]
        edge = {"from": cid, "to": sname, "type": "cites"}
        if edge not in edges:
            edges.append(edge)

    nodes_store.write(nodes)
    edges_store.write(edges)


def add_anchor_node(card_id: str, anchors: list[str]) -> None:
    """为卡片创建知识锚点节点"""
    nodes_store = get_nodes_store()
    nodes = nodes_store.read()

    for i, anchor in enumerate(anchors):
        anchor_id = f"{card_id}_a{i+1}"
        if any(n["id"] == anchor_id for n in nodes):
            continue
        nodes.append({
            "id": anchor_id,
            "name": anchor[:80],
            "type": "anchor",
            "card_id": card_id,
            "updated": datetime.now().isoformat(),
        })

    nodes_store.write(nodes)


def add_semantic_edge(cid: str, card_text: str) -> Optional[str]:
    """为新卡片找最相关的已有卡片建语义边"""
    nodes_store = get_nodes_store()
    edges_store = get_edges_store()
    state_store = get_semantic_state_store()

    nodes = nodes_store.read()
    edges = edges_store.read()
    state = state_store.read()

    if not nodes:
        return None

    series = cid.split("-")[0] if "-" in cid else cid
    siblings = [n for n in nodes if n["id"] != cid and n["id"].startswith(series)]
    if not siblings:
        siblings = [n for n in nodes if n["id"] != cid][:5]
    if not siblings:
        return None

    existing_pairs = set()
    for e in edges:
        if e.get("type") in ("relates_to", "supports", "contrasts"):
            existing_pairs.add(tuple(sorted([e["from"], e["to"]])))

    target = None
    for sib in siblings:
        pair = tuple(sorted([cid, sib["id"]]))
        if pair not in existing_pairs:
            target = sib
            break
    if not target:
        return None

    target_path = DRAFTS_DIR / f"{target['id']}.md"
    if not target_path.exists():
        drafts_dir2 = Path(str(DRAFTS_DIR).replace("drafts", "cards"))
        target_path = drafts_dir2 / f"{target['id']}.md"
    if not target_path.exists():
        return None

    target_text = target_path.read_text(encoding="utf-8")[:KG_MAX_CARD_CONTENT]
    if not target_text:
        return None

    prompt = _classify_prompt(cid, card_text, target["id"], target_text)
    result = call_kg_structured(prompt)
    if not result:
        return None

    relation = result.get("relation", "none")
    if relation == "none":
        state["processed_pairs"].append(sorted([cid, target["id"]]))
        state_store.write(state)
        return None

    edge = {
        "edge_id": f"{cid}_{target['id']}_{relation}",
        "from": cid,
        "to": target["id"],
        "type": relation,
        "weight": result.get("weight", 0.5),
        "reason": result.get("reason", ""),
    }
    edges.append(edge)
    state["total_semantic"] = state.get("total_semantic", 0) + 1

    edges_store.write(edges)
    state_store.write(state)
    return relation


def build_next_edges(nodes: list, existing_edges: list) -> list:
    """自动生成 next 边（同章节连续卡片）"""
    existing = {(e["from"], e["to"]) for e in existing_edges if e.get("type") == "next"}
    new_edges = []

    by_chapter: dict[str, list[tuple[int, str]]] = {}
    for n in nodes:
        cid = n["id"]
        parts = cid.split("-")
        chapter = "-".join(parts[:2]) if len(parts) >= 2 else cid
        try:
            order = int(parts[-1]) if parts[-1].isdigit() else 0
        except ValueError:
            order = 0
        by_chapter.setdefault(chapter, []).append((order, cid))

    for chapter, cards in by_chapter.items():
        cards.sort()
        for i in range(len(cards) - 1):
            pair = (cards[i][1], cards[i + 1][1])
            if pair not in existing:
                new_edges.append({
                    "edge_id": f"{pair[0]}_to_{pair[1]}",
                    "from": pair[0],
                    "to": pair[1],
                    "type": "next",
                    "weight": 1.0,
                    "reason": "同一章节连续小节",
                })

    return new_edges


def _classify_prompt(card_a: str, text_a: str, card_b: str, text_b: str) -> str:
    """构建语义关系分类 prompt"""
    return f"""分析以下两张LocalLLM-IP-Factory卡片之间的关系，返回JSON。

卡片A ({card_a}): {text_a[:300]}
卡片B ({card_b}): {text_b[:300]}

返回格式（只输出JSON，不要其他文字）:
{{"relation": "relates_to|supports|contrasts|none", "reason": "简短原因", "weight": 0.5}}
- relates_to: 主题相关但不直接支撑
- supports: B为A提供证据或扩展
- contrasts: 不同观点或对比
- none: 无明显关系"""
