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

    # 收集所有已使用的 ID
    for mid in re.findall(r'[A-Z]\d+(?:-\d+)+(?:-\d+)?', text):
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

    return slots, used_ids


class IdAssigner:
    """卡片编号分配器"""

    def __init__(self, existing_ids: Set[str]):
        self.slots, self.map_ids = parse_project_map()
        self.used = set(self.map_ids) | existing_ids

    def assign(self, series: str) -> str:
        """为指定系列分配一个新编号"""
        if series in self.slots:
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

        # 可扩展区域用完了，自动递增
        existing = [i for i in self.used if i.startswith(series)]
        if existing:
            # 判断是三位还是两位编号
            has_three = any(len(i.split('-')) == 3 for i in existing)
            if has_three:
                best = max(existing, key=lambda x: tuple(
                    int(p) if p.isdigit() else 0 for p in x.split('-')[1:]
                ))
                parts = best.split('-')
                series_code = parts[0][len(series):]
                cid = f"{series}{series_code}-{int(parts[1])}-{int(parts[2]) + 1}"
            else:
                best = max(existing, key=lambda x: int(x.split('-')[1]))
                parts = best.split('-')
                cid = f"{series}{parts[0][len(series):]}-{int(parts[1]) + 1}"
        else:
            cid = f"{series}1-1"

        self.used.add(cid)
        return cid
