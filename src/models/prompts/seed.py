"""种子生成 prompt（调 douhua）

v3: 系列约束统一从 config/series_definitions.py 读取。
"""
import json
from config.series_definitions import get_series


def build_seed_generation_prompt(
    series: str,
    topic: str,
    style: str,
    existing_titles: list[str],
    needed: int = 10,
) -> str:
    """构建种子生成 prompt"""
    s = get_series(series)
    if s is None:
        s = get_series("F")  # fallback

    existing_block = "\n".join(f"- {t}" for t in existing_titles[-30:]) if existing_titles else "(暂无已有种子)"

    example = s.get("example_seed", {})
    example_json = json.dumps(example, ensure_ascii=False)

    return f"""你是喵言汪语IP的资深内容策划。为"{topic}"系列生成{needed}个新话题种子。

## 系列特性
- 名称: {s['name']}
- 风格: {style}
- Goal 要求: {s['goal_rule']}
- 搜索词要求: {s['kw_rule']}
- 推荐引擎: {s['engine_pref']}

## 核心 IP 定位
动物按钮沟通、宠物对话、人宠互动、行为学、动物认知

## 已有种子 (不要重复标题或变体)
{existing_block}

## 正确示例
{example_json}

## 要求
1. title: 有吸引力的标题，15-50字，应含标点或问句增强吸引力
2. goal: 可执行的写作目标，≥20字，必须包含：
   - 具体内容/知识点/场景
   - 写作角度或叙事手法
   - 至少1个动作词（介绍/分析/讲述/展示/说明等）
   - ❌ 禁止单字标签型 goal（如"幽默""娱乐""猎奇"）
3. engine: 信源引擎 ({s['engine_pref']} 优先)
4. kw: ⚠️ **必填：纯英文搜索关键词，≥3 个英文词。严禁中文，严禁拼音。** kw 将直接用于 DuckDuckGo 搜索引擎检索，中文关键词搜不到有效结果。

## 自检清单（输出前逐条确认）
- [ ] goal ≥ 20 字
- [ ] goal 包含了具体内容和写作角度
- [ ] kw **全部由英文单词组成，不含任何中文**
- [ ] kw ≥ 3 个英文词
- [ ] title 不与已有种子重复
- [ ] title 含有标点或问句增强吸引力

只输出 JSON 数组，不要其他文字。"""
