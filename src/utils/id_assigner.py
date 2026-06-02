"""卡片编号分配器

基于 PROJECT_MAP.md 的编号规则和可扩展区域，自动分配新卡片 ID。
支持章节升级时间冷却（同一系列的下一个章节必须等至少 1 天）。
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Set, List, Dict, Optional

from config.settings import PROJECT_MAP_FILE, DATA_DIR

CHAPTER_DATES_FILE = DATA_DIR / "chapter_dates.json"


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
        self.existing_ids = existing_ids  # 实际产出的卡片 ID

        # 加载章节首次产出日期
        self.chapter_dates: dict = {}
        if CHAPTER_DATES_FILE.exists():
            self.chapter_dates = json.loads(CHAPTER_DATES_FILE.read_text())

    def _record_chapter_date(self, series: str, chapter: int) -> None:
        """记录某个系列章节的首次产出日期"""
        key = f"{series}ch{chapter}"
        if key not in self.chapter_dates:
            self.chapter_dates[key] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            CHAPTER_DATES_FILE.write_text(json.dumps(self.chapter_dates, indent=2))

    def _chapter_is_cooled(self, series: str, chapter: int) -> bool:
        """检查上一章节是否已冷却足够时间（≥1天）
        
        对 ch>=2：必须所有前置章节都已冷却，才能启用。
        例如 ch=4 需要 ch=1,2,3 都已冷却。
        """
        if chapter <= 1:
            return True
        for c in range(1, chapter):
            prev_key = f"{series}ch{c}"
            prev_date = self.chapter_dates.get(prev_key)
            if not prev_date:
                return True  # 前置章节未开始 → 可以通过（会走 fallback 创建它）
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if not (prev_date < today):
                return False  # 前置章节今天才产出的 → 未冷却
        return True

    def _assign_from_slots(self, series: str) -> Optional[str]:
        """从 PROJECT_MAP 的可扩展区域分配编号"""
        if series not in self.slots:
            return None
        for sl in sorted(self.slots[series],
                         key=lambda s: (s['ch'], s['sec'], s['start'])):
            # 章节 >= 2 需要两个条件：
            # 1. chapter 1 已有实际产出卡片
            # 2. chapter 1 首次产出时间已过 1 天冷却期
            if sl['ch'] >= 2:
                prefix_1 = f"{series}1-"
                chapter_1_exists = any(i.startswith(prefix_1) for i in self.existing_ids)
                if not chapter_1_exists or not self._chapter_is_cooled(series, sl['ch']):
                    continue
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
                self._record_chapter_date(series, sl['ch'])
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
            ch = int(parts[1])
            cid = f"{series}{series_code}-{ch}-{int(parts[2]) + 1}"
        else:
            # 全新的系列，从 1-1-1 开始
            cid = f"{series}1-1-1"
            ch = 1

        self.used.add(cid)
        self._record_chapter_date(series, ch)
        return cid
