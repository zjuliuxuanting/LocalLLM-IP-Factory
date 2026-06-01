"""上下文注入引擎

从"前卡 500 字"升级为"知识锚点系统"：
- 每张卡片在完成时提取 3-5 个知识锚点（核心断言/数据/概念）
- 下一张卡片生成时注入已有锚点，确保逻辑递进和避免重复
"""
import re
from pathlib import Path
from typing import Optional

from config.settings import CARDS_DIR, KG_MAX_CARD_CONTENT
from src.io.store import get_nodes_store, get_edges_store


def extract_anchors(text: str, max_anchors: int = 5) -> list[str]:
    """从卡片正文中提取知识锚点

    锚点是正文中的核心断言，通常是含关键数字/专名的句子。
    """
    sentences = re.split(r'[。！？\n]', text)
    candidates = []
    for s in sentences:
        s = s.strip()
        if len(s) < 15 or len(s) > 120:
            continue
        score = 0
        # 含数字或年份
        if re.search(r'\d{2,}', s):
            score += 3
        # 含英文专名
        if re.search(r'[A-Z][a-z]{2,}', s):
            score += 2
        # 含中文关键词（判断/结论/转折）
        if re.search(r'(发现|证明|表明|关键|重要|核心|本质|根本|第一次|最)', s):
            score += 2
        # 叙事锚点
        if re.search(r'\d{4}年', s):
            score += 2

        if score >= 2:
            candidates.append((score, s[:100]))

    candidates.sort(reverse=True, key=lambda x: x[0])
    return [c[1] for c in candidates[:max_anchors]]


def get_series_anchors(series: str, exclude_card_id: str = "") -> list[str]:
    """获取同系列已建立的所有知识锚点"""
    all_anchors = []
    if not CARDS_DIR.exists():
        return all_anchors

    for card_path in sorted(CARDS_DIR.glob("*.md")):
        cid = card_path.stem
        if cid == exclude_card_id:
            continue
        if not cid.startswith(series):
            continue
        try:
            text = card_path.read_text(encoding="utf-8")
            anchors = extract_anchors(text, max_anchors=3)
            for a in anchors:
                all_anchors.append(f"[{cid}] {a}")
        except OSError:
            pass

    return all_anchors[-15:]  # 最多返回最近 15 个锚点


def get_prev_card_text(card_id: str) -> str:
    """获取前一张卡片的正文（用于连贯性参考）"""
    edges = get_edges_store().read()
    for e in edges:
        if e.get("to") == card_id and e.get("type") == "next":
            prev_id = e["from"]
            card_path = CARDS_DIR / f"{prev_id}.md"
            if card_path.exists():
                return card_path.read_text(encoding="utf-8")[:KG_MAX_CARD_CONTENT]
            break

    # fallback: 按编号推算前一张
    parts = card_id.split("-")
    if len(parts) >= 2 and parts[-1].isdigit():
        prev_num = int(parts[-1]) - 1
        if prev_num > 0:
            prev_id = "-".join(parts[:-1]) + f"-{prev_num}"
            card_path = CARDS_DIR / f"{prev_id}.md"
            if card_path.exists():
                return card_path.read_text(encoding="utf-8")[:KG_MAX_CARD_CONTENT]

    return ""


def build_injection_context(card_id: str) -> str:
    """为卡片生成构建上下文注入文本

    包含：
    1. 前一张卡的核心论点摘要
    2. 同系列已建立的知识锚点（避免重复）
    """
    parts = []

    # 前一张卡
    series = card_id.split("-")[0] if "-" in card_id else card_id
    prev_text = get_prev_card_text(card_id)
    if prev_text:
        anchors = extract_anchors(prev_text, max_anchors=2)
        summary = " ".join(anchors) if anchors else prev_text[:200]
        parts.append(f"前一张卡的核心内容: {summary}")
        parts.append("注意: 不要重复讲述前一张卡已覆盖的内容，保持逻辑递进。")

    # 同系列锚点
    series_anchors = get_series_anchors(series, card_id)
    if series_anchors:
        parts.append(f"\n本系列已建立的知识基础:")
        for a in series_anchors[-10:]:
            parts.append(f"  - {a}")
        parts.append("请贡献新的知识，不要重复以上内容。")

    return "\n".join(parts)
