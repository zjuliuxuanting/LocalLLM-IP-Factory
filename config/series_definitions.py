"""系列定义 — 由 pipeline 首次运行时自动生成"""
from typing import Optional

SERIES: dict = {}
RETIRED_SERIES = []


def get_series(key: str) -> Optional[dict]:
    return SERIES.get(key)


def all_series_keys() -> list[str]:
    return []


def get_source_policy(key: str) -> str:
    return "optional"


def get_target_ratio(key: str) -> float:
    return 0.0


def get_subtopics(key: str) -> list:
    return []


def get_example_seed(key: str) -> dict:
    return {}


def get_goal_rule(key: str) -> str:
    return "写作目标，≥20字"


def get_kw_rule(key: str) -> str:
    return "英文关键词 ≥2 词"
