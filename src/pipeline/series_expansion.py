"""系列自我进化引擎

让内容网络能够感知饱和、发现缺口、提出有架构约束的新系列。

设计原则：
  - 新系列不能凭空产生 — 必须与 ≥2 个现有系列有逻辑关联
  - 新系列必须有信源支撑 — 至少 1 个种子候选通过信源验证
  - 新系列不能与现有系列重叠 — 语义距离检查
  - 最终决定权在人 — 提案写入 staging 文件，等待审批

触发条件（全部满足才启动分析）：
  1. ≥2 个活跃系列达到"饱和线"（子话题覆盖 >75% 或近期种子新颖度 <0.4）
  2. 知识图谱存在"薄区"（节点数少但与核心区有边连接的中间地带）
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import PROJECT_ROOT, KG_DIR
from src.io.store import AtomicJsonStore, get_nodes_store, get_edges_store
from src.io.source_validator import validate_source
from src.models.gateway import call_douhua
from src.quality.seed_gate import inspect_seed
from src.pipeline.seed_diversity import (
    analyze_coverage, check_batch_diversity, semantic_novelty,
    detect_patterns,
)
from config.series_definitions import SERIES, get_series, all_series_keys, get_subtopics
from src.utils.logging import get_logger

logger = get_logger("series_expansion")

# 提案暂存目录
STAGING_DIR = PROJECT_ROOT / "data" / "series_proposals"
STAGING_DIR.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════
# 1. 饱和度检测
# ══════════════════════════════════════════════════════════════

@dataclass
class SeriesHealth:
    series: str
    seed_count: int
    coverage_rate: float       # 子话题覆盖比例
    recent_novelty: float      # 最近 20 个种子的平均 pairwise 新颖度
    pattern_alert: bool
    pattern_detail: str
    is_saturated: bool         # 是否达到饱和线
    saturation_reason: str = ""


def check_saturation(pool: dict, series: str,
                     coverage_threshold: float = 0.75,
                     novelty_threshold: float = 0.4) -> SeriesHealth:
    """检测单个系列是否趋于饱和

    饱和定义：
      - 子话题覆盖率 > 75%：大部分规划的话题已有种子
      - 或 近期种子内部新颖度 < 0.4：新种子开始雷同
    """
    data = pool.get(series, {})
    seeds = data.get("seeds", [])
    coverage = analyze_coverage(series, seeds)
    cov_rate = int(coverage.get("coverage_rate", "0%").rstrip("%")) / 100

    # 最近 20 个种子的内部新颖度
    recent = seeds[-20:] if len(seeds) >= 20 else seeds
    novelty = check_batch_diversity(recent) if len(recent) >= 5 else 1.0

    patterns = detect_patterns(seeds)
    pattern_alert = len(patterns) > 0

    saturated = False
    reasons = []
    if cov_rate >= coverage_threshold:
        saturated = True
        reasons.append(f"子话题覆盖 {cov_rate:.0%} ≥ {coverage_threshold:.0%}")
    if novelty <= novelty_threshold:
        saturated = True
        reasons.append(f"近期新颖度 {novelty:.2f} ≤ {novelty_threshold}")

    return SeriesHealth(
        series=series,
        seed_count=len(seeds),
        coverage_rate=cov_rate,
        recent_novelty=novelty,
        pattern_alert=pattern_alert,
        pattern_detail="; ".join(patterns) if patterns else "",
        is_saturated=saturated,
        saturation_reason="; ".join(reasons) if reasons else "",
    )


def should_trigger_expansion(pool: dict) -> tuple[bool, list[SeriesHealth]]:
    """判断是否应该启动系列扩展分析

    Returns:
        (是否触发, 各系列健康度列表)
    """
    healths = []
    for key in all_series_keys():
        if key in pool:
            h = check_saturation(pool, key)
            healths.append(h)

    saturated = [h for h in healths if h.is_saturated]
    trigger = len(saturated) >= 2

    return trigger, healths


# ══════════════════════════════════════════════════════════════
# 2. 知识图谱缺口分析
# ══════════════════════════════════════════════════════════════

def analyze_graph_gaps() -> dict:
    """分析知识图谱中的"薄区"

    薄区定义：
      - 两个现有系列之间有语义边连接，但边密度低
      - 或某些节点类型（如 concept/person）数量过少
    """
    nodes = get_nodes_store().read()
    edges = get_edges_store().read()

    # 按系列统计节点数
    series_nodes: dict[str, int] = {}
    for n in nodes:
        cid = n.get("id", "")
        if "-" in cid:
            s = cid.split("-")[0]
            series_nodes[s] = series_nodes.get(s, 0) + 1

    # 跨系列边统计
    cross_edges: dict[tuple, int] = {}
    for e in edges:
        f = e.get("from", "").split("-")[0] if "-" in e.get("from", "") else ""
        t = e.get("to", "").split("-")[0] if "-" in e.get("to", "") else ""
        if f and t and f != t:
            pair = tuple(sorted([f, t]))
            cross_edges[pair] = cross_edges.get(pair, 0) + 1

    # 找连接最稀疏的系列对（有少量连接，说明有话题桥梁但没充分开发）
    thin_bridges = []
    active = all_series_keys()
    for s1 in active:
        for s2 in active:
            if s1 >= s2:
                continue
            pair = tuple(sorted([s1, s2]))
            count = cross_edges.get(pair, 0)
            n1 = series_nodes.get(s1, 0)
            n2 = series_nodes.get(s2, 0)
            if n1 > 0 and n2 > 0 and count > 0 and count < 5:
                thin_bridges.append({
                    "series_a": s1,
                    "series_b": s2,
                    "cross_edges": count,
                    "potential": "high" if count <= 2 else "medium",
                })

    return {
        "series_node_counts": series_nodes,
        "cross_series_edges": {f"{k[0]}-{k[1]}": v for k, v in cross_edges.items()},
        "thin_bridges": sorted(thin_bridges, key=lambda x: x["cross_edges"]),
    }


# ══════════════════════════════════════════════════════════════
# 3. 新系列提案生成
# ══════════════════════════════════════════════════════════════

SERIES_PROPOSAL_PROMPT = """你是LocalLLM-IP-FactoryIP的首席内容架构师。当前内容网络出现饱和信号，需要你提出一个**有严格架构约束**的新系列。

## 现有系列
{existing_series}

## 饱和状态
{saturation_report}

## 知识图谱缺口
薄弱的跨系列桥梁（这些是话题中间地带，可以发展为新系列）:
{thin_bridges}

## 缺失的子话题
{missing_subtopics}

## 提案要求（严格）

1. **新系列必须连接 ≥2 个现有系列**，不能凭空产生。说明它与哪些系列有逻辑关联。
2. **新系列必须能通过信源验证**，给出 3 个种子候选，每个都有英文搜索词。
3. **新系列不能与现有系列重叠**。如果现有系列已经覆盖了该话题，不要重复。
4. **新系列必须有清晰的内容边界**——什么属于它，什么不属于它。

## 输出格式（只输出 JSON）

{{
  "proposal": {{
    "series_code": "单个大写字母，不与现有{{B,C,D,E,G,H,I,J,K,L,N,O,T,U,V,W,X,Y,Z}}冲突",
    "name": "系列中文名（4-8字）",
    "topic": "系列话题描述",
    "style": "内容风格（20-50字）",
    "rationale": "为什么需要这个系列（100-200字）：它填补了什么空白？与哪些现有系列相关联？",
    "connects_to": ["系列A", "系列B"],
    "connection_detail": "如何与每个关联系列衔接",
    "estimated_volume": "预计种子规模（如 30-50 个）",
    "subtopics": ["子话题1", "子话题2", "子话题3", "子话题4", "子话题5"],
    "source_policy": "required 或 optional",
    "engine_pref": "pubmed/web/arxiv",
    "seed_candidates": [
      {{"title": "示例标题", "goal": "写作目标", "engine": "web", "kw": "english search keywords"}}
    ]
  }}
}}

只输出 JSON。"""


def generate_proposal(pool: dict, max_retries: int = 2) -> Optional[dict]:
    """生成一个新系列的完整提案"""
    trigger, healths = should_trigger_expansion(pool)
    if not trigger:
        return None

    # 收集饱和度报告
    sat_lines = []
    for h in healths:
        status = "🔴 饱和" if h.is_saturated else "🟢 正常"
        sat_lines.append(
            f"- {h.series}: {h.seed_count}种子, "
            f"覆盖率{h.coverage_rate:.0%}, "
            f"新颖度{h.recent_novelty:.2f}, "
            f"{status}"
            + (f" ({h.saturation_reason})" if h.is_saturated else "")
        )

    # 知识图谱缺口
    gaps = analyze_graph_gaps()
    bridge_lines = []
    for b in gaps["thin_bridges"][:5]:
        s1_name = get_series(b["series_a"]) or {}
        s2_name = get_series(b["series_b"]) or {}
        bridge_lines.append(
            f"- {b['series_a']}({s1_name.get('name','')}) ↔ "
            f"{b['series_b']}({s2_name.get('name','')}): "
            f"{b['cross_edges']}条边, 潜力={b['potential']}"
        )

    # 缺失子话题
    missing_lines = []
    for key in all_series_keys():
        if key in pool:
            cov = analyze_coverage(key, pool[key].get("seeds", []))
            missing = cov.get("missing", [])
            if missing:
                missing_lines.append(f"  {key}: {missing[:3]}")

    existing_desc = "\n".join(
        f"- {k}: {v.get('name','')} ({v.get('topic','')})"
        for k, v in SERIES.items()
    )

    prompt = SERIES_PROPOSAL_PROMPT.format(
        existing_series=existing_desc,
        saturation_report="\n".join(sat_lines),
        thin_bridges="\n".join(bridge_lines) if bridge_lines else "(暂无薄区数据，基于语义逻辑推断)",
        missing_subtopics="\n".join(missing_lines) if missing_lines else "(暂无)",
    )

    for attempt in range(max_retries + 1):
        raw = call_douhua(prompt, max_tokens=4096, temperature=0.6)
        if not raw:
            continue

        m = re.search(r'\{[\s\S]*\}', raw)
        if not m:
            continue

        try:
            result = json.loads(m.group())
            proposal = result.get("proposal", result)
            if _validate_proposal_structure(proposal):
                return proposal
        except json.JSONDecodeError:
            continue

    return None


# ══════════════════════════════════════════════════════════════
# 4. 架构验证
# ══════════════════════════════════════════════════════════════

def _validate_proposal_structure(proposal: dict) -> bool:
    """检查提案是否包含所有必需字段"""
    required = ["series_code", "name", "topic", "style", "rationale",
                "connects_to", "subtopics", "seed_candidates"]
    return all(k in proposal for k in required)


def validate_proposal(proposal: dict, pool: dict) -> dict:
    """对提案执行完整的架构验证

    Returns:
        {"passed": bool, "issues": [...], "warnings": [...], "score": float}
    """
    issues = []
    warnings = []

    code = proposal.get("series_code", "")
    name = proposal.get("name", "")
    connects = proposal.get("connects_to", [])
    candidates = proposal.get("seed_candidates", [])

    # 1. 系列代码不能冲突
    if code in SERIES:
        issues.append(f"系列代码 '{code}' 已存在")
    if len(code) != 1 or not code.isalpha() or not code.isupper():
        issues.append(f"系列代码必须是单个大写字母，得到: '{code}'")

    # 2. 必须连接 ≥2 个现有系列
    valid_connects = [c for c in connects if c in SERIES]
    if len(valid_connects) < 2:
        issues.append(f"只连接到 {len(valid_connects)} 个现有系列，需要 ≥2")

    # 3. seed_candidates 至少 1 个通过质量门禁
    valid_candidates = 0
    for seed in candidates:
        gr = inspect_seed(seed, code, [], check_source=False)
        if gr.passed:
            valid_candidates += 1
    if valid_candidates == 0:
        issues.append(f"种子候选全部未通过质量门禁")
    elif valid_candidates < 2:
        warnings.append(f"仅 {valid_candidates} 个种子候选通过质量门禁，建议 ≥2")

    # 4. 信源验证（至少1个候选的信源可用）
    if proposal.get("source_policy") == "required":
        source_ok = 0
        for seed in candidates:
            result = validate_source(seed.get("kw", ""), seed.get("engine", "web"))
            if result.available:
                source_ok += 1
        if source_ok == 0:
            issues.append("信源策略为 required 但所有候选信源不可用")

    # 5. 语义重叠检查：新系列与现有系列的主题重叠度
    overlap_alerts = []
    new_text = f"{name} {proposal.get('topic','')} {proposal.get('rationale','')}"
    for key, s in SERIES.items():
        old_text = f"{s.get('name','')} {s.get('topic','')}"
        nov = semantic_novelty(new_text, name, [{"title": old_text, "goal": ""}])
        if nov < 0.4:
            overlap_alerts.append(f"与 {key}({s.get('name','')}) 语义重叠度偏高 ({nov:.2f})")
    if overlap_alerts:
        warnings.extend(overlap_alerts)

    # 综合评分
    score = 10.0
    score -= len(issues) * 3
    score -= len(warnings) * 1
    score = max(0, min(10, score))

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "score": round(score, 1),
    }


# ══════════════════════════════════════════════════════════════
# 5. 人类审批门
# ══════════════════════════════════════════════════════════════

def stage_proposal(proposal: dict, validation: dict) -> Path:
    """将提案写入暂存文件，等待人类审批"""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    code = proposal.get("series_code", "X")
    filename = f"proposal_{code}_{timestamp}.json"
    filepath = STAGING_DIR / filename

    record = {
        "proposal": proposal,
        "validation": validation,
        "status": "pending_review",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "approved_at": None,
        "approved_by": None,
    }
    store = AtomicJsonStore(filepath, {})
    store.write(record)
    return filepath


def list_proposals() -> list[dict]:
    """列出所有待审批的提案"""
    proposals = []
    for fp in sorted(STAGING_DIR.glob("proposal_*.json")):
        store = AtomicJsonStore(fp, {})
        data = store.read()
        proposals.append({
            "file": fp.name,
            "status": data.get("status", "unknown"),
            "code": data.get("proposal", {}).get("series_code", "?"),
            "name": data.get("proposal", {}).get("name", "?"),
            "validation_score": data.get("validation", {}).get("score", 0),
            "generated_at": data.get("generated_at", ""),
        })
    return proposals


def approve_proposal(filename: str, approved_by: str = "human") -> dict:
    """审批通过：将新系列写入 series_definitions.py 和 seed_pool.json"""
    fp = STAGING_DIR / filename
    if not fp.exists():
        return {"ok": False, "error": f"提案文件不存在: {filename}"}

    store = AtomicJsonStore(fp, {})
    record = store.read()
    record["status"] = "approved"
    record["approved_at"] = datetime.now(timezone.utc).isoformat()
    record["approved_by"] = approved_by
    store.write(record)

    proposal = record["proposal"]
    code = proposal["series_code"]

    # 写入 series_definitions.py（作为新的 SERIES 条目）
    # 注意：这是 Python 文件，需要小心处理
    _add_series_to_definitions(code, proposal)

    # 写入 seed_pool.json
    _add_series_to_seed_pool(code, proposal)

    return {"ok": True, "series_code": code, "name": proposal.get("name", "")}


def _add_series_to_seed_pool(code: str, proposal: dict):
    """将新系列添加到 seed_pool.json"""
    from src.io.store import AtomicJsonStore
    from config.settings import SEED_POOL_FILE

    store = AtomicJsonStore(SEED_POOL_FILE, {})
    pool = store.read()

    pool[code] = {
        "topic": proposal.get("topic", ""),
        "style": proposal.get("style", ""),
        "forbidden": ["在本文中", "值得注意的是", "综上所述"],
        "avg_chars": 400,
        "seeds": proposal.get("seed_candidates", []),
    }
    store.write(pool)


def _add_series_to_definitions(code: str, proposal: dict):
    """将新系列写入 series_definitions.py（追加到 SERIES 字典）

    这是对 Python 源文件的操作，需要安全处理。
    写入后需人工检查语法。
    """
    defs_file = PROJECT_ROOT / "config" / "series_definitions.py"
    content = defs_file.read_text(encoding="utf-8")

    # 找到最后一个 "P": { 条目的结束位置
    # 在 RETIRED_SERIES 之前插入新条目
    insertion_marker = "RETIRED_SERIES"
    new_entry = f'''
    "{code}": {{
        "name": "{proposal.get('name', '')}",
        "topic": "{proposal.get('topic', '')}",
        "style": "{proposal.get('style', '')}",
        "forbidden": ["在本文中", "值得注意的是", "综上所述"],
        "source_policy": "{proposal.get('source_policy', 'optional')}",
        "target_ratio": 0.08,
        "engine_pref": "{proposal.get('engine_pref', 'web')}",
        "avg_chars": 400,
        "subtopics": {json.dumps(proposal.get('subtopics', []), ensure_ascii=False)},
        "goal_rule": "写作目标，≥20字",
        "kw_rule": "英文关键词 ≥2 词",
        "example_seed": {json.dumps(proposal.get('seed_candidates', [{}])[0] if proposal.get('seed_candidates') else {{}}, ensure_ascii=False)},
        "notes": "AI提案生成，待人工确认。关联: {', '.join(proposal.get('connects_to', []))}",
    }},
    # ==== 下一系列在此之上插入 ====
    '''
    content = content.replace(
        f"# {insertion_marker}",
        f"{new_entry}# {insertion_marker}",
    )
    defs_file.write_text(content, encoding="utf-8")

    logger.warning(
        f"已修改 series_definitions.py，添加系列 {code}。"
        f"请检查文件语法后再运行。"
    )


# ══════════════════════════════════════════════════════════════
# 便捷入口
# ══════════════════════════════════════════════════════════════

def run_expansion_check(pool: dict, auto_generate: bool = False) -> dict:
    """运行完整的扩展分析

    Returns:
        {
            "triggered": bool,
            "health": [...],
            "graph_gaps": {...},
            "proposal": {...} 或 None (如果 auto_generate=False 或未触发),
            "proposal_file": str 或 None,
        }
    """
    triggered, healths = should_trigger_expansion(pool)
    gaps = analyze_graph_gaps()

    result = {
        "triggered": triggered,
        "health": [{
            "series": h.series,
            "seed_count": h.seed_count,
            "coverage_rate": f"{h.coverage_rate:.0%}",
            "recent_novelty": h.recent_novelty,
            "is_saturated": h.is_saturated,
            "saturation_reason": h.saturation_reason,
            "pattern_alert": h.pattern_alert,
        } for h in healths],
        "graph_gaps": {
            "series_nodes": gaps["series_node_counts"],
            "thin_bridges": gaps["thin_bridges"],
        },
        "proposal": None,
        "proposal_file": None,
    }

    if triggered and auto_generate:
        proposal = generate_proposal(pool)
        if proposal:
            validation = validate_proposal(proposal, pool)
            filepath = stage_proposal(proposal, validation)
            result["proposal"] = {
                "code": proposal.get("series_code"),
                "name": proposal.get("name"),
                "rationale": proposal.get("rationale", "")[:200],
                "connects_to": proposal.get("connects_to", []),
                "validation": validation,
            }
            result["proposal_file"] = str(filepath)

    return result
