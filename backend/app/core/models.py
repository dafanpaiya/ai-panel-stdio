"""
AI Panel Studio — 领域模型
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ── 枚举 ────────────────────────────────────────────

class PanelistRole(StrEnum):
    MODERATOR = "moderator"
    EXPERT = "expert"


class UtteranceType(StrEnum):
    OPENING = "opening"
    MAIN = "main"
    SUPPLEMENT = "supplement"
    REBUTTAL = "rebuttal"
    MODERATOR_INTERJECTION = "moderator_interjection"
    CLOSING = "closing"


class PanelistStatus(StrEnum):
    IDLE = "idle"
    PREPARING = "preparing"
    SPEAKING = "speaking"


class DiscussionStatus(StrEnum):
    DRAFT = "draft"
    LINEUP_READY = "lineup_ready"
    RUNNING = "running"
    PAUSED = "paused"
    ENDED = "ended"


class ModeratorTrigger(StrEnum):
    OPENING = "opening"
    ROUND_INTERVAL = "round_interval"
    SILENCE = "silence"
    OFF_TOPIC = "off_topic"
    USER_INTERJECTION = "user_interjection"
    CLOSING = "closing"


# ── 领域模型 ─────────────────────────────────────────

@dataclass
class Panelist:
    id: str
    discussion_id: str
    role: PanelistRole
    name: str
    occupation: str
    title: str
    stance: str
    color: str
    sort_order: int

    @classmethod
    def from_dict(cls, d: dict) -> "Panelist":
        return cls(
            id=d["id"],
            discussion_id=d["discussion_id"],
            role=PanelistRole(d["role"]),
            name=d["name"],
            occupation=d["occupation"],
            title=d["title"],
            stance=d["stance"],
            color=d["color"],
            sort_order=d["sort_order"],
        )


@dataclass
class Utterance:
    id: str
    discussion_id: str
    panelist_id: str
    type: UtteranceType
    content: str
    round: int
    seq: int
    created_at: str


@dataclass
class Discussion:
    id: str
    topic: str
    status: DiscussionStatus
    max_rounds: int
    current_round: int

    def can_start(self) -> bool:
        return self.status == DiscussionStatus.LINEUP_READY

    def can_resume(self) -> bool:
        return self.status == DiscussionStatus.PAUSED

    def is_running(self) -> bool:
        return self.status == DiscussionStatus.RUNNING


@dataclass
class Consensus:
    id: str
    discussion_id: str
    content: str
    source_utterance_ids: list[str] = field(default_factory=list)
    version: int = 1


@dataclass
class Divergence:
    id: str
    discussion_id: str
    content: str
    opposing_sides: list[dict] = field(default_factory=list)
    source_utterance_ids: list[str] = field(default_factory=list)
    version: int = 1


@dataclass
class PanelistState:
    panelist_id: str
    discussion_id: str
    status: PanelistStatus = PanelistStatus.IDLE
    focus: Optional[str] = None

    def set_preparing(self, focus: str = "正在组织观点…"):
        self.status = PanelistStatus.PREPARING
        self.focus = focus

    def set_speaking(self, focus: Optional[str] = None):
        self.status = PanelistStatus.SPEAKING
        if focus:
            self.focus = focus

    def set_idle(self, focus: Optional[str] = None):
        self.status = PanelistStatus.IDLE
        if focus:
            self.focus = focus


@dataclass
class SpeakingStats:
    panelist_id: str
    total_utterances: int = 0
    consecutive_utterances: int = 0
    last_spoke_round: int = 0  # 0 = never spoke


# ── 调度结果 ─────────────────────────────────────────

@dataclass
class SchedulerResult:
    """两步管道第一步的输出"""
    selected_panelist_id: str
    type: UtteranceType
    reason: str
    target_panelist_id: Optional[str] = None


@dataclass
class SpeakerResult:
    """两步管道第二步的输出"""
    panelist_id: str
    content: str
    type: UtteranceType
    round: int
    seq: int


@dataclass
class InsightResult:
    """增量共识/分歧更新结果"""
    consensus_updates: list[Consensus] = field(default_factory=list)
    divergence_updates: list[Divergence] = field(default_factory=list)


# ── SSE 事件 ─────────────────────────────────────────

@dataclass
class SSEEvent:
    """SSE 事件基类"""
    event: str
    data: dict

    def to_sse(self) -> str:
        import json
        return f"event: {self.event}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"
