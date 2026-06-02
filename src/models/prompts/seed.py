"""种子生成 prompt

系列约束从 docs/SERIES_TOPICS.md 读取，修改后立即生效。
"""
import json, re
from typing import Optional, List
from pathlib import Path

TOPICS_FILE = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "SERIES_TOPICS.md"


def _parse_series() -> dict:
    """解析 SERIES_TOPICS.md 返回 { 'B': {name, style, engine, ...}, ... }"""
    if not TOPICS_FILE.exists():
        return _fallback_series()
    text = TOPICS_FILE.read_text(encoding="utf-8")
    blocks = re.split(r'\n## ', text)
    series = {}
    for block in blocks:
        header = block.split('\n')[0].strip()
        m = re.match(r'([A-Z])[：:]\s*(.+)', header)
        if not m:
            continue
        key = m.group(1)
        name = m.group(2).strip()
        body = '\n'.join(block.split('\n')[1:])

        def gf(label):
            p = re.search(rf'- {re.escape(label)}[：:]\s*(.+)', body)
            return p.group(1).strip() if p else ""

        def gl(label):
            p = re.search(rf'- {re.escape(label)}[：:]\s*(.+)', body)
            return [x.strip() for x in p.group(1).split('、')] if p else []

        style = gf("风格")
        engine = gf("引擎")
        goal_rule = gf("目标规则")
        kw_rule = gf("关键词规则")
        subtopics = gl("子话题")
        notes = gf("备注")
        engine_pref = engine.split("（")[0].split(",")[0].strip()

        example = {}
        ex = re.search(r'- 示例种子[：:]\s*\n(\s+- title: .+?\n\s+- goal: .+?\n\s+- engine: .+?\n\s+- kw: .+?)\n', body)
        if ex:
            t = re.search(r'title[：:]\s*(.+)', ex.group(1))
            g = re.search(r'goal[：:]\s*(.+)', ex.group(1))
            e = re.search(r'engine[：:]\s*(.+)', ex.group(1))
            k = re.search(r'kw[：:]\s*(.+)', ex.group(1))
            if t and g and e and k:
                example = {"title": t.group(1).strip(), "goal": g.group(1).strip(),
                           "engine": e.group(1).strip(), "kw": k.group(1).strip()}

        series[key] = {
            "name": name, "style": style, "engine_pref": engine_pref,
            "goal_rule": goal_rule, "kw_rule": kw_rule,
            "subtopics": subtopics, "example_seed": example, "notes": notes,
        }
    return series


def _fallback_series() -> dict:
    """没有 SERIES_TOPICS.md 时的降级"""
    from config.series_definitions import SERIES
    return {k: {"name": v.get("name",""), "style": v.get("style",""),
                "engine_pref": v.get("engine_pref","web"),
                "goal_rule": v.get("goal_rule",""),
                "kw_rule": v.get("kw_rule",""),
                "subtopics": v.get("subtopics",[]),
                "example_seed": v.get("example_seed",{}),
                "notes": v.get("notes","")}
            for k, v in SERIES.items()}


def build_seed_generation_prompt(
    series: str,
    topic: str,
    style: str,
    existing_titles: list[str],
    needed: int = 10,
    subtopics: Optional[List[str]] = None,
    covered_topics: Optional[List[str]] = None,
    chapter_info: str = "",
    engine_status: Optional[dict] = None,
) -> str:
    """构建种子生成 prompt

    Args:
        subtopics: 系列定义的子话题列表
        covered_topics: 已被现有种子覆盖的子话题
        chapter_info: 章节上下文（如 "第2卷 · B2"）
    """
    all_series = _parse_series()
    s = all_series.get(series, {})

    existing_block = "\n".join(f"- {t}" for t in existing_titles[-30:]) if existing_titles else "(暂无已有种子)"

    example = s.get("example_seed", {})
    example_json = json.dumps(example, ensure_ascii=False)
    engine_pref = s.get("engine_pref", "web")
    goal_rule = s.get("goal_rule", "写作目标，≥20字")
    kw_rule = s.get("kw_rule", "英文关键词 ≥2 词")

    # 覆盖度指导
    coverage_guide = ""
    if subtopics:
        covered = set(covered_topics or [])
        missing = [t for t in subtopics if t not in covered]
        if missing:
            coverage_guide = f"""
## ⚠️ 子话题覆盖指引
本系列定义了 {len(subtopics)} 个子话题。当前已覆盖: {', '.join(sorted(covered)) if covered else '(暂无)'}。
**尚未覆盖的子话题: {', '.join(missing)}**
👉 请优先从缺失子话题中生成种子，每个子话题至少产出 1-2 个种子。避免在已覆盖子话题上生成变体。
"""
        elif covered:
            coverage_guide = f"""
## 子话题覆盖
所有 {len(subtopics)} 个子话题均已覆盖: {', '.join(sorted(covered))}。
若仍需补种，请深入挖掘已有子话题的细分角度，或从跨话题交叉地带寻找新切入点。
"""

    chapter_note = ""
    if chapter_info:
        chapter_note = f"""
## 📖 章节上下文
当前正在为 **{chapter_info}** 生成种子。这是该系列的新章节/新卷，请区别于前卷的内容方向。可以:
- 从前卷未深挖的子话题切入
- 或从全新角度重新组织已有话题（更深入、更交叉、更当代）
"""

    engine_guide = ""
    if engine_status:
        available = [k for k, v in engine_status.items() if v]
        unavailable = [k for k, v in engine_status.items() if not v]
        parts = []
        if available:
            parts.append(f"**可用引擎: {', '.join(available)}**")
        if unavailable:
            parts.append(f"**不可用引擎: {', '.join(unavailable)}** —— 请勿生成使用这些引擎的种子，用可用引擎替代")
        if unavailable:
            parts.append(f"若某引擎不可用但其对应的信源类型仍是该系列的首选，请将 engine 字段设为可用引擎中最接近的替代（如 pubmed 不可用时可用 web，反之亦然）")
        engine_guide = "\n## ⚠️ 引擎可用性\n" + "\n".join(parts) + "\n"

    return f"""你是LocalLLM-IP-FactoryIP的资深内容策划。为"{topic}"系列生成{needed}个新话题种子。

## 系列特性
- 名称: {s.get('name', topic)}
- 风格: {style}
- Goal 要求: {goal_rule}
- 搜索词要求: {kw_rule}
- 推荐引擎: {engine_pref}
{chapter_note}{engine_guide}{coverage_guide}
## 核心 IP 定位
动物按钮沟通、宠物对话、人宠互动、行为学、动物认知

## 已有种子 (不要重复标题或变体)
{existing_block}

## 正确示例
{example_json}

## 可用引擎
- `pubmed`: NIH 论文数据库，适合科普/科研类种子
- `arxiv`: 预印本论文，适合技术/前沿类种子
- `patent`: Google Patents 专利检索，适合调研/产品/技术类种子
- `web`: 通用搜索引擎（百度/Wikipedia），适合新闻/故事/问答类种子

根据系列特性和引擎可用性选择最合适的引擎。{engine_pref} 是本系列推荐引擎。

## 要求
1. title: 有吸引力的标题，15-50字，应含标点或问句增强吸引力
2. goal: 可执行的写作目标，≥20字，必须包含：
   - 具体内容/知识点/场景
   - 写作角度或叙事手法
   - 至少1个动作词（介绍/分析/讲述/展示/说明等）
   - ❌ 禁止单字标签型 goal（如"幽默""娱乐""猎奇"）
3. engine: 信源引擎，从上述可用引擎中选择
4. kw: ⚠️ **必填：纯英文搜索关键词，≥3 个英文词。严禁中文，严禁拼音。** kw 将直接用于搜索引擎检索，中文关键词搜不到有效结果。

## 自检清单（输出前逐条确认）
- [ ] goal ≥ 20 字
- [ ] goal 包含了具体内容和写作角度
- [ ] kw **全部由英文单词组成，不含任何中文**
- [ ] kw ≥ 3 个英文词
- [ ] title 不与已有种子重复
- [ ] title 含有标点或问句增强吸引力

只输出 JSON 数组，不要其他文字。"""
