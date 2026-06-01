"""信源缓存管理

管理 source_cache/ 目录，提供缓存读写、过期清理和统计。
"""
import shutil
import time
from pathlib import Path
from typing import Optional

from config.settings import CACHE_DIR


class SourceCache:
    """信源缓存管理器"""

    def __init__(self, base_dir: Optional[Path] = None):
        self._base = Path(base_dir) if base_dir else CACHE_DIR

    def get_dir(self, card_id: str) -> Path:
        """获取指定卡片的缓存目录"""
        d = self._base / card_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def has(self, card_id: str) -> bool:
        """检查卡片是否有已缓存的信源"""
        d = self._base / card_id
        if not d.exists():
            return False
        files = [p for p in d.iterdir() if p.is_file() and p.stat().st_size > 50]
        return len(files) > 0

    def list_files(self, card_id: str) -> list[Path]:
        """列出卡片的所有缓存文件路径"""
        d = self._base / card_id
        if not d.exists():
            return []
        return sorted(
            [p for p in d.iterdir() if p.is_file() and p.stat().st_size > 50],
            key=lambda p: p.stat().st_mtime,
        )

    def write(self, card_id: str, filename: str, content: str) -> Path:
        """写入缓存文件"""
        d = self.get_dir(card_id)
        fp = d / filename
        fp.write_text(content, encoding="utf-8")
        return fp

    def read_all(self, card_id: str, max_chars_per_file: int = 4000) -> str:
        """读取卡片的所有缓存信源，拼接为字符串"""
        parts = []
        for fp in self.list_files(card_id)[:5]:
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")
                parts.append(f"\n[信源:{fp.name}]\n{content[:max_chars_per_file]}")
            except OSError:
                pass
        return "\n".join(parts)

    def clear_card(self, card_id: str) -> None:
        """清除指定卡片的缓存"""
        d = self._base / card_id
        if d.exists():
            shutil.rmtree(d)

    def clear_old(self, max_age_days: int = 30) -> int:
        """清理超过 max_age_days 天的缓存，返回清理数量"""
        now = time.time()
        cutoff = now - max_age_days * 86400
        removed = 0
        for card_dir in self._base.iterdir():
            if not card_dir.is_dir():
                continue
            try:
                mtime = card_dir.stat().st_mtime
                if mtime < cutoff:
                    shutil.rmtree(card_dir)
                    removed += 1
            except OSError:
                pass
        return removed

    def stats(self) -> dict:
        """缓存统计"""
        total_files = 0
        total_size = 0
        card_count = 0
        for card_dir in self._base.iterdir():
            if not card_dir.is_dir():
                continue
            card_count += 1
            for fp in card_dir.iterdir():
                if fp.is_file():
                    total_files += 1
                    total_size += fp.stat().st_size
        return {
            "cards_cached": card_count,
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 1),
        }
