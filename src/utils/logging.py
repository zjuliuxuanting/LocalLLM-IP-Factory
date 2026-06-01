"""结构化日志系统

统一日志格式，支持 JSON 行输出（用于后续可观测性）。
取代当前散落在各处的 print() 调用。
"""
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── 日志格式器 ──

class JsonFormatter(logging.Formatter):
    """输出单行 JSON 日志，便于机器解析"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "card_id"):
            payload["card_id"] = record.card_id
        if hasattr(record, "stage"):
            payload["stage"] = record.stage
        if hasattr(record, "duration_s"):
            payload["duration_s"] = record.duration_s
        if hasattr(record, "extra"):
            payload.update(record.extra)
        return json.dumps(payload, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """人类可读的控制台格式，带时间戳和模块名"""

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    reset = "\x1b[0m"

    FORMATS = {
        logging.DEBUG: grey + "%(asctime)s %(name)-24s %(message)s" + reset,
        logging.INFO: "%(asctime)s %(name)-24s %(message)s",
        logging.WARNING: yellow + "%(asctime)s %(name)-24s %(message)s" + reset,
        logging.ERROR: red + "%(asctime)s %(name)-24s %(message)s" + reset,
    }

    def format(self, record: logging.LogRecord) -> str:
        fmt = self.FORMATS.get(record.levelno, self.FORMATS[logging.DEBUG])
        formatter = logging.Formatter(fmt, datefmt="%H:%M:%S")
        return formatter.format(record)


# ── Logger 工厂 ──

_loggers: dict[str, logging.Logger] = {}
_initialized = False


def setup(
    level: int = logging.INFO,
    log_dir: Optional[Path] = None,
    json_file: bool = True,
) -> None:
    """初始化全局日志系统，只需调用一次"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger("miao")
    root.setLevel(level)
    root.handlers.clear()

    # 控制台输出
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(ConsoleFormatter())
    root.addHandler(console)

    # 文件输出
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        if json_file:
            fh = logging.FileHandler(log_dir / "pipeline.jsonl", encoding="utf-8")
            fh.setLevel(level)
            fh.setFormatter(JsonFormatter())
            root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    """获取或创建子模块 logger"""
    if name not in _loggers:
        _loggers[name] = logging.getLogger(f"miao.{name}")
    return _loggers[name]


# ── 结构化事件辅助 ──

def log_stage_start(card_id: str, stage: str) -> None:
    logger = get_logger("pipeline")
    logger.info(f"▶ {card_id} {stage}", extra={
        "card_id": card_id, "stage": stage, "event": "stage_start",
    })


def log_stage_done(card_id: str, stage: str, duration_s: float,
                   ok: bool = True, detail: str = "") -> None:
    logger = get_logger("pipeline")
    icon = "✓" if ok else "✗"
    msg = f"{icon} {card_id} {stage} ({duration_s:.1f}s)"
    if detail:
        msg += f" — {detail}"
    logger.info(msg, extra={
        "card_id": card_id, "stage": stage, "event": "stage_done",
        "duration_s": round(duration_s, 1), "ok": ok,
    })
