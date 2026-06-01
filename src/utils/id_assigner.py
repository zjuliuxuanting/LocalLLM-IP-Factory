"""卡片编号分配器

基于 PROJECT_MAP.md 的编号规则和可扩展区域，自动分配新卡片 ID。
"""
import re
from pathlib import Path
from typing import Set, List, Dict, Optional

from config.settings import PROJECT_MAP_FILE


def parse_project_map() -> tuple:
    """解析 PROJECT_MAP.md，返回 (slots, used_ids)

    slots: { series: [{ch, sec, start, hint, exact?}] }
    used_ids: set of all IDs mentioned in the map
    """
    slots: Dict[str, List[dict]] = {}
    used_ids: Set[str] = set()

    map_file = Path(PROJECT_MAP_FILE)
    if not map_file.exists():
        return slots, used_ids

    text = map_file.read_text(encoding="utf-8")

    # 先移除所有范围引用如 "F2-1-1~F2-1-9"（范围起止都不是实际卡片 ID）
    text_clean = re.sub(r'[A-Z]\d+(?:-\d+)+\s*~\s*[A-Z]\d+(?:-\d+)+', '', text)

    # 收集所有已使用的 ID
    for mid in re.findall(r'[A-Z]\d+(?:-\d+)+(?:-\d+)?', text_clean):
        used_ids.add(mid)

    # 解析"可扩展区域"
    in_ext = False
    for line in text.split('\n'):
        if '可扩展区域' in line:
            in_ext = True
            continue
        if in_ext and line.startswith('|--'):
            continue
        if in_ext and line.startswith('|'):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if len(cells) < 3:
                continue
            series, range_str, hint = cells[0], cells[1], cells[2]

            # 范围格式: B3-1-1~
            m = re.match(r'([A-Z]+)(\d+)-(\d+)-(\d+)~', range_str)
            if m:
                slots.setdefault(m.group(1), []).append({
                    'ch': int(m.group(2)),
                    'sec': int(m.group(3)),
                    'start': int(m.group(4)),
                    'hint': hint,
                })

            # 具体 ID 引用（如 S2-1-4~ 中的 S2-1-4）
            for mid in re.findall(r'([A-Z]\d+-\d+-\d+)', range_str):
                m2 = re.match(r'([A-Z]+)(\d+)-(\d+)-(\d+)', mid)
                if m2:
                    slots.setdefault(m2.group(1), []).append({
                        'ch': int(m2.group(2)),
                        'sec': int(m2.group(3)),
                        'start': int(m2.group(4)),
                        'hint': hint,
                        'exact': True,
                    })

    # 可扩展区域的起始编号不算"已使用"（如 B2-3-1 只是起始标记）
    for series, series_slots in slots.items():
        for sl in series_slots:
            start_id = f"{series}{sl['ch']}-{sl['sec']}-{sl['start']}"
            used_ids.discard(start_id)

    return slots, used_ids


class IdAssigner:
    """卡片编号分配器"""

    def __init__(self, existing_ids: Set[str]):
        self.slots, self.map_ids = parse_project_map()
        self.used = set(self.map_ids) | existing_ids

    def _assign_from_slots(self, series: str) -> Optional[str]:
        """从 PROJECT_MAP 的可扩展区域分配编号"""
        if series not in self.slots:
            return None
        for sl in sorted(self.slots[series],
                         key=lambda s: (s['ch'], s['sec'], s['start'])):
            prefix = f"{series}{sl['ch']}-{sl['sec']}-"
            used_in_slot = sorted(
                i for i in self.used if i.startswith(prefix)
            )
            if used_in_slot:
                next_num = max(int(i.rsplit('-', 1)[1]) for i in used_in_slot) + 1
            else:
                next_num = sl['start']
            cid = f"{prefix}{next_num}"
            if cid not in self.used:
                self.used.add(cid)
                return cid
        return None

    def assign(self, series: str) -> str:
        """为指定系列分配一个新编号（永远输出 3 段格式，如 B2-3-2）"""
        # 优先从 PROJECT_MAP 可扩展区域分配
        result = self._assign_from_slots(series)
        if result:
            return result

        # 没有可扩展区域 → 找已有 3 段 ID 自动递增
        existing = sorted(
            i for i in self.used
            if i.startswith(series) and len(i.split('-')) == 3
        )
        if existing:
            best = max(existing, key=lambda x: tuple(
                int(p) if p.isdigit() else 0 for p in x.split('-')[1:]
            ))
            parts = best.split('-')
            series_code = parts[0][len(series):]
            cid = f"{series}{series_code}-{int(parts[1])}-{int(parts[2]) + 1}"
        else:
            # 全新的系列，从 1-1-1 开始
            cid = f"{series}1-1-1"

        self.used.add(cid)
        return cid
