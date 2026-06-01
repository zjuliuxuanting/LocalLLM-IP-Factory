"""卡片状态机

定义单卡从种子到完成的全部生命周期状态，以及上下文数据结构。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CardState(str, Enum):
    PENDING = "pending"
    RESEARCHING = "researching"
    RESEARCHED = "researched"
    OUTLINING = "outlining"
    OUTLINED = "outlined"
    DRAFTING = "drafting"
    DRAFTED = "drafted"
    REVIEWING = "reviewing"
    REVIEWED = "reviewed"
    REVISING = "revising"
    REVISED = "revised"
    POLISHING = "polishing"
    POLISHED = "polished"
    FACTCHECKING = "factchecking"
    FACTCHECKED = "factchecked"
    COMPLETE = "complete"
    FAILED = "failed"


# 状态流转图
TRANSITIONS: dict[CardState, CardState] = {
    CardState.PENDING: CardState.RESEARCHING,
    CardState.RESEARCHING: CardState.RESEARCHED,
    CardState.RESEARCHED: CardState.OUTLINING,
    CardState.OUTLINING: CardState.OUTLINED,
    CardState.OUTLINED: CardState.DRAFTING,
    CardState.DRAFTING: CardState.DRAFTED,
    CardState.DRAFTED: CardState.REVIEWING,
    CardState.REVIEWING: CardState.REVIEWED,
    CardState.REVIEWED: CardState.REVISING,
    CardState.REVISING: CardState.REVISED,
    CardState.REVISED: CardState.POLISHING,
    CardState.POLISHING: CardState.POLISHED,
    CardState.POLISHED: CardState.FACTCHECKING,
    CardState.FACTCHECKING: CardState.FACTCHECKED,
    CardState.FACTCHECKED: CardState.COMPLETE,
}

# 每个阶段是否需要 GPU
GPU_STAGES: set[CardState] = {
    CardState.OUTLINING, CardState.DRAFTING, CardState.REVIEWING,
    CardState.REVISING, CardState.POLISHING, CardState.FACTCHECKING,
}

# 阶段到可读名称
STAGE_NAMES: dict[CardState, str] = {
    CardState.PENDING: "待处理",
    CardState.RESEARCHING: "S1 研究",
    CardState.RESEARCHED: "研究完成",
    CardState.OUTLINING: "S2 大纲",
    CardState.OUTLINED: "大纲完成",
    CardState.DRAFTING: "S3 初稿",
    CardState.DRAFTED: "初稿完成",
    CardState.REVIEWING: "S4 自审",
    CardState.REVIEWED: "自审完成",
    CardState.REVISING: "S5 修订",
    CardState.REVISED: "修订完成",
    CardState.POLISHING: "S6 润色",
    CardState.POLISHED: "润色完成",
    CardState.FACTCHECKING: "S7 查证",
    CardState.FACTCHECKED: "查证完成",
    CardState.COMPLETE: "完成",
    CardState.FAILED: "失败",
}


@dataclass
class CardContext:
    """卡片在流水线中流转的完整上下文"""
    card: dict

    # S1
    source_files: list[str] = field(default_factory=list)
    source_text: str = ""

    # S2
    outline: Optional[dict] = None

    # S3
    draft: str = ""
    draft_retries: int = 0

    # S4
    review_result: Optional[dict] = None

    # S5
    revised: str = ""

    # S6
    polished: str = ""

    # S7
    factcheck_result: Optional[dict] = None

    # 前一张卡内容（连贯性用）
    prev_card_text: str = ""

    # 最终
    final: str = ""
    quality_score: float = 0.0

    # 状态追踪
    state: CardState = CardState.PENDING
    stage_retries: int = 0
    card_retries: int = 0
    error: str = ""

    @property
    def card_id(self) -> str:
        return self.card.get("id", "")

    @property
    def needs_gpu(self) -> bool:
        return self.state in GPU_STAGES

    def advance(self) -> CardState:
        next_state = TRANSITIONS.get(self.state)
        if next_state:
            self.state = next_state
            self.stage_retries = 0
        return self.state

    def advance_target(self) -> Optional[CardState]:
        """返回下一阶段目标（不实际推进状态）"""
        return TRANSITIONS.get(self.state)

    def mark_failed(self, reason: str = ""):
        self.state = CardState.FAILED
        self.error = reason
