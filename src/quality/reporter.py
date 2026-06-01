"""质控报告生成"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import REPORTS_DIR
from src.quality.metrics import QualityResult, DimensionScore
from src.io.store import AtomicJsonStore


def generate_report(results: list[QualityResult]) -> dict:
    """基于一批质检结果生成统计报告"""
    total = len(results)
    passed = sum(1 for r in results if r.verdict == "pass")
    warned = sum(1 for r in results if r.verdict == "warn")
    failed = sum(1 for r in results if r.verdict == "fail")

    issue_types: dict[str, int] = {}
    dim_avgs: dict[str, list[float]] = {}
    for r in results:
        for ds in r.dimensions:
            dim_avgs.setdefault(ds.dimension, []).append(ds.score)
        for issue in r.block_issues:
            key = issue.split("] ")[0].lstrip("[") if "] " in issue else "other"
            issue_types[key] = issue_types.get(key, 0) + 1

    dim_summary = {
        dim: round(sum(scores) / len(scores), 1)
        for dim, scores in dim_avgs.items() if scores
    }

    return {
        "timestamp": datetime.now().isoformat(),
        "total": total,
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "pass_rate": f"{passed / max(total, 1) * 100:.1f}%",
        "dimension_averages": dim_summary,
        "issue_distribution": issue_types,
    }


def save_report(report: dict, name: Optional[str] = None) -> Path:
    """保存质控报告到 JSON 文件"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if name is None:
        name = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    path = REPORTS_DIR / f"{name}.json"
    store = AtomicJsonStore(path, {})
    store.write(report)
    return path


def format_card_result(result: QualityResult, show_details: bool = False) -> str:
    """格式化单卡质检结果为可读文本"""
    icons = {"pass": "✅", "warn": "⚠️", "fail": "❌"}
    icon = icons.get(result.verdict, "❓")
    lines = [
        f"{icon} {result.card_id} — {result.verdict.upper()} ({result.weighted_total}/10)",
    ]
    if show_details:
        for ds in result.dimensions:
            flag = "🔴" if ds.hard_gate_fail else "  "
            lines.append(f"  {flag} {ds.dimension}: {ds.score}/10 ({ds.details})")
    if result.block_issues:
        for iss in result.block_issues[:3]:
            lines.append(f"  ❌ {iss[:80]}")
    if result.soft_issues:
        for iss in result.soft_issues[:2]:
            lines.append(f"  ⚠️ {iss[:80]}")
    return "\n".join(lines)
