"""质量评分标准与门禁阈值

集中管理所有评分维度的权重和硬性/软性门禁规则。
修改此文件即可调整整个质控体系的行为。
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class DimensionSpec:
    name: str
    weight: float
    hard_gate: Optional[float] = None   # 低于此分直接 FAIL，None 表示无硬性门禁
    soft_gate: Optional[float] = None   # 低于此分触发 WARN
    description: str = ""


# ══════════════════════════════════════════════════════════════
# 七维评分标准
# ══════════════════════════════════════════════════════════════

DIMENSIONS = [
    DimensionSpec(
        name="length",
        weight=0.15,
        hard_gate=5.0,
        soft_gate=None,
        description="字数是否在 [min_chars, max_chars] 区间",
    ),
    DimensionSpec(
        name="format",
        weight=0.10,
        hard_gate=3.0,
        soft_gate=None,
        description="无代码块包裹、无 content=、无禁词元描述",
    ),
    DimensionSpec(
        name="source_alignment",
        weight=0.20,
        hard_gate=4.0,
        soft_gate=None,
        description="关键实体/年份/数据是否与信源匹配",
    ),
    DimensionSpec(
        name="fact_accuracy",
        weight=0.25,
        hard_gate=5.0,
        soft_gate=None,
        description="事实断言是否可在信源中验证（调 douhua 评估）",
    ),
    DimensionSpec(
        name="style",
        weight=0.10,
        hard_gate=None,
        soft_gate=3.0,
        description="文本特征是否匹配期望风格（学术/叙事/趣味等）",
    ),
    DimensionSpec(
        name="coherence",
        weight=0.10,
        hard_gate=None,
        soft_gate=None,
        description="与前一张卡片的逻辑递进关系",
    ),
    DimensionSpec(
        name="novelty",
        weight=0.10,
        hard_gate=None,
        soft_gate=3.0,
        description="与同系列已有卡片的内容重复度（10=全新）",
    ),
]

# ══════════════════════════════════════════════════════════════
# 综合门禁阈值
# ══════════════════════════════════════════════════════════════

PASS_THRESHOLD = 7.0    # 总分 >= 此值 → PASS
WARN_THRESHOLD = 5.0    # 总分 >= 此值但 < PASS → WARN
                         # 总分 < 此值 → FAIL

# ══════════════════════════════════════════════════════════════
# 各阶段质控映射
# ══════════════════════════════════════════════════════════════

# 每个阶段跑哪些维度的检查
STAGE_CHECKS = {
    "outline":    [],                                          # S2 仅结构校验
    "draft":      ["length", "format"],                        # S3 快速检查
    "review":     ["length", "format", "style", "coherence"],  # S4 完整自审
    "revise":     ["length", "format"],                        # S5 修订验证
    "polish":     ["style"],                                   # S6 风格检查
    "factcheck":  ["source_alignment", "fact_accuracy"],       # S7 事实核查
    "final":      ["length", "format", "source_alignment",
                   "fact_accuracy", "style", "coherence",
                   "novelty"],                                 # 最终全维度
}

# ══════════════════════════════════════════════════════════════
# 重试与回退策略
# ══════════════════════════════════════════════════════════════

MAX_STAGE_RETRIES = 2       # 同一阶段最大重试次数
MAX_CARD_RETRIES = 3        # 整张卡片从 S1 重新开始的最大次数
STAGE_RETRY_DELAY = 10      # 阶段内重试等待秒数

# ══════════════════════════════════════════════════════════════
# 字数评分映射
# ══════════════════════════════════════════════════════════════

def score_length(actual: int, min_chars: int, max_chars: int) -> float:
    """将实际字数映射到 0-10 分"""
    if actual < min_chars:
        ratio = actual / max(min_chars, 1)
        return round(max(0, ratio * 8), 1)
    if actual > max_chars:
        ratio = max_chars / max(actual, 1)
        return round(max(0, ratio * 8), 1)
    # 在范围内，越接近中心越好
    center = (min_chars + max_chars) / 2
    deviation = abs(actual - center) / max((max_chars - min_chars) / 2, 1)
    return round(10 - deviation * 2, 1)
