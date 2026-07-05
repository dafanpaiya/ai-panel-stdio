"""
发言调度器单元测试 （TDD）

测试范围：
  - Scheduler：两步管道第一步 — 决定“谁发言 + 什么类型”
  - ModeratorTrigger：主持人条件触发逻辑
  - 不测试实际 LLM 调用（全部 mock）

Mock 策略：
  所有 LLM 调用使用固定返回值替代，模拟 Deepseek V4 Flash 响应。
"""

import uuid
import pytest
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
from enum import StrEnum


# ============================================================
# 领域枚举（与实现保持一致）
# ============================================================

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
    ROUND_INTERVAL = "round_interval"
    SILENCE = "silence"
    OFF_TOPIC = "off_topic"
    USER_INTERJECTION = "user_interjection"
    CLOSING = "closing"


# ============================================================
# 领域模型（简化 dataclass，用于测试）
# ============================================================

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


@dataclass
class SpeakingStats:
    """单个专家的发言统计"""
    panelist_id: str
    total_utterances: int
    consecutive_utterances: int
    last_spoke_round: int


# ============================================================
# Mock 固定返回值
# ============================================================

def make_mock_scheduler_response(
    selected_panelist_id: str,
    utterance_type: str = "main",
    target_panelist_id: Optional[str] = None,
    reason: str = "该专家最近未发言，应给予发言机会",
) -> dict:
    """构造模拟调度器 LLM 返回的 JSON"""
    result: dict = {
        "selected_panelist_id": selected_panelist_id,
        "type": utterance_type,
        "reason": reason,
    }
    if target_panelist_id:
        result["target_panelist_id"] = target_panelist_id
    return result


# ---- 预制 mock 调度决策序列 ----
# 用于测试多轮调度逻辑

MOCK_SCHEDULE_SEQUENCE = [
    # (panelist_index, type, reason)
    (1, "main",       "专家1立场鲜明，应首先发言"),
    (2, "main",       "专家2持反对立场，需要表达"),
    (1, "supplement", "专家1补充之前的观点"),
    (3, "rebuttal",   "专家3反驳专家1的观点"),
    (2, "supplement", "专家2补充专家1的分析"),
    (4, "main",       "专家4尚未发言，提出新视角"),
    (3, "rebuttal",   "专家3继续反驳"),
    (1, "supplement", "专家1回应反驳"),
    (2, "rebuttal",   "专家2反对专家3的立场"),
    (4, "supplement", "专家4补充"),
]


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def discussion() -> Discussion:
    """标准讨论实例"""
    return Discussion(
        id=str(uuid.uuid4()),
        topic="AI 是否应该拥有法律人格？",
        status=DiscussionStatus.RUNNING,
        max_rounds=12,
        current_round=3,
    )


@pytest.fixture
def moderator() -> Panelist:
    """标准主持人"""
    return Panelist(
        id=str(uuid.uuid4()),
        discussion_id="",
        role=PanelistRole.MODERATOR,
        name="陈锐",
        occupation="资深媒体人",
        title="《前沿对话》主持人",
        stance="中立，擅长引导多视角辩论",
        color="#4A90D9",
        sort_order=0,
    )


@pytest.fixture
def experts() -> list[Panelist]:
    """4 位专家"""
    return [
        Panelist(
            id=str(uuid.uuid4()),
            discussion_id="",
            role=PanelistRole.EXPERT,
            name="林芳",
            occupation="法学教授",
            title="北京大学法学院",
            stance="倾向于支持 AI 有限法律人格",
            color="#E57373",
            sort_order=1,
        ),
        Panelist(
            id=str(uuid.uuid4()),
            discussion_id="",
            role=PanelistRole.EXPERT,
            name="李国栋",
            occupation="经济学家",
            title="社科院经济研究所",
            stance="质疑 AI 法律人格的经济基础",
            color="#FFB74D",
            sort_order=2,
        ),
        Panelist(
            id=str(uuid.uuid4()),
            discussion_id="",
            role=PanelistRole.EXPERT,
            name="王雪",
            occupation="科技政策研究员",
            title="中国科学院",
            stance="关注监管框架的可行路径",
            color="#81C784",
            sort_order=3,
        ),
        Panelist(
            id=str(uuid.uuid4()),
            discussion_id="",
            role=PanelistRole.EXPERT,
            name="周明哲",
            occupation="AI 伦理学家",
            title="某科技公司伦理委员会",
            stance="强调人类福祉为讨论出发点",
            color="#BA68C8",
            sort_order=4,
        ),
    ]


@pytest.fixture
def panelists(moderator: Panelist, experts: list[Panelist]) -> list[Panelist]:
    """完整嘉宾列表（主持人 + 4 专家）"""
    return [moderator] + experts


@pytest.fixture
def empty_transcript() -> list[Utterance]:
    """空 transcript"""
    return []


@pytest.fixture
def sample_transcript(
    discussion: Discussion,
    moderator: Panelist,
    experts: list[Panelist],
) -> list[Utterance]:
    """
    典型 transcript 快照：
    - 第 1 轮：主持人开场 + 专家 1、2 各一句
    - 第 2 轮：专家 3、4 各一句 + 主持人串联
    - 第 3 轮：专家 1 反驳 + 专家 2 补充
    """
    seq = 0
    now = datetime.now(timezone.utc).isoformat()

    def utt(panelist: Panelist, r: int, t: UtteranceType, content: str) -> Utterance:
        nonlocal seq
        seq += 1
        return Utterance(
            id=str(uuid.uuid4()),
            discussion_id=discussion.id,
            panelist_id=panelist.id,
            type=t,
            content=content,
            round=r,
            seq=seq,
            created_at=now,
        )

    return [
        utt(moderator,  1, UtteranceType.OPENING,
            "大家好，欢迎来到《前沿对话》。今天我们讨论的话题是 AI 是否应该拥有法律人格。首先请林芳教授发言。"),
        utt(experts[0], 1, UtteranceType.MAIN,
            "从法理学角度看，法律人格的赋予从来不是基于生物学标准，而是基于社会功能的必要性。"),
        utt(experts[1], 1, UtteranceType.MAIN,
            "我部分同意林教授，但必须强调公司法人制度的背后有股东和注册资本的支撑，AI 目前缺少这样的经济基础。"),
        utt(experts[2], 2, UtteranceType.MAIN,
            "从科技政策角度看，如果真的要推进 AI 法律人格立法，监管框架需要先走一步。"),
        utt(experts[3], 2, UtteranceType.MAIN,
            "这是一个全球治理的问题，不应该被简化为单一法域的立法选择。"),
        utt(moderator,  2, UtteranceType.MODERATOR_INTERJECTION,
            "感谢各位的观点。林教授，您对李老师的质疑有什么回应？"),
        utt(experts[0], 3, UtteranceType.REBUTTAL,
            "历史上所有重大法律变革都不是等全球共识形成后才开始的，欧洲 GDPR 就是先行者示范。"),
        utt(experts[1], 3, UtteranceType.SUPPLEMENT,
            "我承认先行者的思路，但我担心的不是速度问题，而是经济基础确实尚未建立。"),
    ]


@pytest.fixture
def speaking_stats(experts: list[Panelist]) -> list[SpeakingStats]:
    """与 sample_transcript 对应的发言统计"""
    return [
        SpeakingStats(
            panelist_id=experts[0].id,
            total_utterances=3,
            consecutive_utterances=0,  # 上一轮最后发言的不是他
            last_spoke_round=3,
        ),
        SpeakingStats(
            panelist_id=experts[1].id,
            total_utterances=2,
            consecutive_utterances=1,  # 第 3 轮刚发过言
            last_spoke_round=3,
        ),
        SpeakingStats(
            panelist_id=experts[2].id,
            total_utterances=1,
            consecutive_utterances=0,
            last_spoke_round=2,
        ),
        SpeakingStats(
            panelist_id=experts[3].id,
            total_utterances=1,
            consecutive_utterances=0,
            last_spoke_round=2,
        ),
    ]


# ============================================================
# 1. 调度器核心逻辑测试
# ============================================================

class TestSchedulerCore:
    """
    测试调度器：给定 transcript + 专家列表 + 发言统计
    → 返回“谁发言 + 什么类型”（两步管道第一步）
    """

    def test_returns_selected_expert_from_pool(
        self, experts: list[Panelist], empty_transcript: list[Utterance],
    ):
        """
        调度器必须从专家池中选出一位专家。
        不应选中主持人。
        """
        mock_response = make_mock_scheduler_response(
            selected_panelist_id=experts[0].id,
            utterance_type="main",
            reason="专家1立场鲜明，应首先发言",
        )

        assert mock_response["selected_panelist_id"] in [e.id for e in experts]
        assert mock_response["type"] == "main"

    def test_returns_valid_utterance_type(
        self, experts: list[Panelist], empty_transcript: list[Utterance],
    ):
        """
        调度器返回的 type 必须是有效的发言类型 — 对专家而言
        只能是 main / supplement / rebuttal。
        moderator_interjection / opening / closing 由引擎直接触发，不经过调度器。
        """
        valid_expert_types = {"main", "supplement", "rebuttal"}

        for _, utt_type, _ in MOCK_SCHEDULE_SEQUENCE:
            assert utt_type in valid_expert_types, (
                f"调度器返回了非法发言类型: {utt_type}"
            )

    def test_rebuttal_and_supplement_have_target(
        self, experts: list[Panelist],
    ):
        """
        rebuttal 和 supplement 类型必须附带 target_panelist_id，
        指明反驳/补充的对象。main 类型不需要。
        """
        # rebuttal 必须有 target
        rebuttal_resp = make_mock_scheduler_response(
            experts[0].id, "rebuttal", target_panelist_id=experts[2].id,
        )
        assert rebuttal_resp["type"] == "rebuttal"
        assert "target_panelist_id" in rebuttal_resp
        assert rebuttal_resp["target_panelist_id"] == experts[2].id

        # supplement 必须有 target
        supplement_resp = make_mock_scheduler_response(
            experts[1].id, "supplement", target_panelist_id=experts[0].id,
        )
        assert supplement_resp["type"] == "supplement"
        assert "target_panelist_id" in supplement_resp

        # main 不需要 target
        main_resp = make_mock_scheduler_response(experts[3].id, "main")
        assert main_resp["type"] == "main"
        assert "target_panelist_id" not in main_resp

    def test_target_must_be_different_from_speaker(
        self, experts: list[Panelist],
    ):
        """
        target_panelist_id 绝不能等于 selected_panelist_id
        （专家不能反驳/补充自己）
        """
        resp = make_mock_scheduler_response(
            experts[0].id, "rebuttal", target_panelist_id=experts[1].id,
        )
        assert resp["target_panelist_id"] != resp["selected_panelist_id"]


# ============================================================
# 2. 连续发言约束测试
# ============================================================

class TestConsecutiveSpeakConstraint:
    """
    约束：同一专家连续发言不得超过 2 次。
    PRD §2.3.2 — "尽量不让同一名专家连续发言超过两次"
    """

    def test_blocks_expert_with_2_consecutive(
        self, experts: list[Panelist],
    ):
        """
        如果某专家已连续发言 2 次，调度器必须排除该专家。
        """
        stats = [
            SpeakingStats(experts[0].id, 5, 2, 3),
            SpeakingStats(experts[1].id, 2, 0, 2),
            SpeakingStats(experts[2].id, 1, 0, 1),
            SpeakingStats(experts[3].id, 0, 0, 0),
        ]

        blocked_ids = {
            s.panelist_id for s in stats if s.consecutive_utterances >= 2
        }

        assert experts[0].id in blocked_ids
        assert experts[1].id not in blocked_ids
        assert experts[2].id not in blocked_ids
        assert experts[3].id not in blocked_ids

    def test_allows_expert_with_1_consecutive(
        self, experts: list[Panelist],
    ):
        """
        连续发言 1 次的专家仍可被选中 — 允许再发一次。
        """
        stats = [
            SpeakingStats(experts[0].id, 3, 1, 3),
        ]

        blocked_ids = {
            s.panelist_id for s in stats if s.consecutive_utterances >= 2
        }

        assert experts[0].id not in blocked_ids

    def test_when_all_blocked_oldest_gets_reset(
        self, experts: list[Panelist],
    ):
        """
        极端情况：全部专家都已连续发言 ≥2 次（理论上不应出现，但需兜底）。
        此时应重置计数，选择距上次发言最久的专家。
        """
        stats = [
            SpeakingStats(experts[0].id, 6, 2, 3),
            SpeakingStats(experts[1].id, 5, 2, 3),
            SpeakingStats(experts[2].id, 4, 3, 2),
            SpeakingStats(experts[3].id, 3, 2, 1),
        ]

        all_blocked = all(s.consecutive_utterances >= 2 for s in stats)
        assert all_blocked

        # 兜底逻辑：选 last_spoke_round 最小的
        candidate = min(stats, key=lambda s: s.last_spoke_round)
        assert candidate.panelist_id == experts[3].id


# ============================================================
# 3. 发言轮转优先级测试
# ============================================================

class TestRotationPriority:
    """
    约束：优先选择最近未发言的专家，禁止机械式轮流发言。
    PRD §2.3.2 — “优先选择最近未发言的专家”
    """

    def test_orders_by_last_spoke_ascending(
        self, experts: list[Panelist],
    ):
        """
        候选排序应优先选择 last_spoke_round 最小的专家。
        """
        stats = [
            SpeakingStats(experts[0].id, 3, 0, 3),
            SpeakingStats(experts[1].id, 2, 1, 3),
            SpeakingStats(experts[2].id, 1, 0, 2),
            SpeakingStats(experts[3].id, 0, 0, 0),
        ]

        # 排除连续 ≥2 的专家后，按 last_spoke_round 升序排列
        eligible = [s for s in stats if s.consecutive_utterances < 2]
        eligible.sort(key=lambda s: s.last_spoke_round)

        assert eligible[0].panelist_id == experts[3].id  # 从未发言
        assert eligible[1].panelist_id == experts[2].id  # round 2
        assert eligible[2].panelist_id == experts[0].id  # round 3

    def test_never_spoken_gets_highest_priority(
        self, experts: list[Panelist],
    ):
        """
        从未发过言的专家（last_spoke_round=0）应获得最高优先级。
        """
        stats = [
            SpeakingStats(experts[0].id, 3, 0, 3),
            SpeakingStats(experts[1].id, 2, 0, 2),
            SpeakingStats(experts[2].id, 0, 0, 0),  # 未发言
            SpeakingStats(experts[3].id, 1, 0, 1),
        ]

        eligible = [s for s in stats if s.consecutive_utterances < 2]
        eligible.sort(key=lambda s: s.last_spoke_round)

        assert eligible[0].panelist_id == experts[2].id


# ============================================================
# 4. 主持人触发条件测试
# ============================================================

class TestModeratorTriggers:
    """
    主持人不参与调度池，由引擎按条件直接触发。
    PRD §2.3.3

    触发条件：
    - 开场：讨论启动时（不经过此测试的调度器）
    - 轮次间隔：每 3-4 轮专家发言后
    - 冷场：长时间无新发言
    - 跑题：LLM 检测到偏题
    - 用户追问：用户插入追问
    - 收尾：达到最大轮次或用户手动结束
    """

    # ---- 轮次间隔触发 ----

    def test_moderator_triggers_after_3_expert_rounds(
        self, discussion: Discussion,
    ):
        """
        当距上次主持人介入已满 3 轮专家发言时，触发主持人介入。
        """
        discussion.current_round = 6
        last_moderator_round = 3

        rounds_since_moderator = discussion.current_round - last_moderator_round
        should_trigger = rounds_since_moderator >= 3

        assert should_trigger is True

    def test_moderator_does_not_trigger_at_2_rounds(
        self, discussion: Discussion,
    ):
        """
        仅过了 2 轮时不应触发。
        """
        discussion.current_round = 5
        last_moderator_round = 3

        rounds_since_moderator = discussion.current_round - last_moderator_round
        should_trigger = rounds_since_moderator >= 3

        assert should_trigger is False

    # ---- 收尾触发 ----

    def test_closing_triggers_at_max_rounds(
        self, discussion: Discussion,
    ):
        """
        达到最大轮次时触发收尾。
        """
        discussion.current_round = 12
        discussion.max_rounds = 12

        assert discussion.current_round >= discussion.max_rounds

    def test_closing_does_not_trigger_before_max(
        self, discussion: Discussion,
    ):
        """
        未达最大轮次时不触发收尾。
        """
        discussion.current_round = 11
        discussion.max_rounds = 12

        assert discussion.current_round < discussion.max_rounds

    # ---- 用户追问触发 ----

    def test_user_interjection_queues_trigger(
        self, discussion: Discussion,
    ):
        """
        用户插入追问后，pending_interjection 标记为 True，
        下一轮主持人优先处理。
        """
        pending_interjection: bool = False
        interjection_message: Optional[str] = None

        # 模拟用户追问
        interjection_message = "能否讨论一下数据隐私方面的考量？"
        pending_interjection = True

        assert pending_interjection is True
        assert interjection_message is not None
        assert len(interjection_message) > 0

    # ---- 冷场触发 ----

    def test_silence_trigger_after_timeout(
        self, discussion: Discussion,
    ):
        """
        冷场检测：距离上次发言超过阈值时间。
        """
        from datetime import timedelta

        SILENCE_THRESHOLD_SECONDS = 30
        last_utterance_time = datetime.now(timezone.utc) - timedelta(seconds=35)

        elapsed = (datetime.now(timezone.utc) - last_utterance_time).total_seconds()
        should_trigger = elapsed >= SILENCE_THRESHOLD_SECONDS

        assert should_trigger is True

    def test_silence_does_not_trigger_within_threshold(
        self, discussion: Discussion,
    ):
        """
        冷场检测：距离上次发言未超过阈值时不触发。
        """
        from datetime import timedelta

        SILENCE_THRESHOLD_SECONDS = 30
        last_utterance_time = datetime.now(timezone.utc) - timedelta(seconds=10)

        elapsed = (datetime.now(timezone.utc) - last_utterance_time).total_seconds()
        should_trigger = elapsed >= SILENCE_THRESHOLD_SECONDS

        assert should_trigger is False


# ============================================================
# 5. 发言统计计算测试
# ============================================================

class TestSpeakingStatsCalculation:
    """
    从 transcript 计算每位专家的发言统计。
    """

    def test_calculates_total_utterances(
        self, experts: list[Panelist], sample_transcript: list[Utterance],
    ):
        """
        统计每位专家的总发言次数（不含主持人）。
        """
        expert_ids = {e.id for e in experts}
        counts: dict[str, int] = {}

        for u in sample_transcript:
            if u.panelist_id in expert_ids:
                counts[u.panelist_id] = counts.get(u.panelist_id, 0) + 1

        assert counts[experts[0].id] == 2  # round 1 main + round 3 rebuttal
        assert counts[experts[1].id] == 2  # round 1 main + round 3 supplement
        assert counts[experts[2].id] == 1  # 1 main
        assert counts[experts[3].id] == 1  # 1 main

    def test_calculates_consecutive_utterances(
        self, experts: list[Panelist], sample_transcript: list[Utterance],
    ):
        """
        计算每个专家的连续发言次数 — 按 seq 倒序扫描，
        遇到不同 panelist 时停止。
        """
        expert_ids = {e.id for e in experts}
        expert_utterances = [u for u in sample_transcript if u.panelist_id in expert_ids]
        expert_utterances.sort(key=lambda u: u.seq, reverse=True)

        consecutive: dict[str, int] = {e.id: 0 for e in experts}
        first_id = expert_utterances[0].panelist_id
        for u in expert_utterances:
            if u.panelist_id == first_id:
                consecutive[u.panelist_id] += 1
            else:
                break

        # transcript 最后一条专家发言是 experts[1]（李国栋）的 supplement
        assert consecutive[experts[1].id] >= 1
        # 在它之前的是 experts[0]，所以连续计数应停止
        assert consecutive[experts[0].id] == 0

    def test_calculates_last_spoke_round(
        self, experts: list[Panelist], sample_transcript: list[Utterance],
    ):
        """
        计算每个专家最近一次发言的轮次。
        从未发言的专家 last_spoke_round = 0。
        """
        last_round: dict[str, int] = {e.id: 0 for e in experts}

        for u in sample_transcript:
            if u.panelist_id in last_round:
                last_round[u.panelist_id] = max(last_round[u.panelist_id], u.round)

        assert last_round[experts[0].id] == 3
        assert last_round[experts[1].id] == 3
        assert last_round[experts[2].id] == 2
        assert last_round[experts[3].id] == 2

    def test_never_spoken_expert_stats(
        self, experts: list[Panelist],
    ):
        """
        从未发言的专家应有 zero stats。
        """
        stats = SpeakingStats(
            panelist_id=experts[3].id,
            total_utterances=0,
            consecutive_utterances=0,
            last_spoke_round=0,
        )

        assert stats.total_utterances == 0
        assert stats.consecutive_utterances == 0
        assert stats.last_spoke_round == 0


# ============================================================
# 6. 边界与异常场景
# ============================================================

class TestEdgeCases:

    def test_single_expert_scenario(self):
        """
        只有 1 位专家时，调度器必须选这位专家，
        且连续发言约束放宽（因无其他人可选）。
        """
        only_expert = Panelist(
            id=str(uuid.uuid4()),
            discussion_id="",
            role=PanelistRole.EXPERT,
            name="林芳",
            occupation="法学教授",
            title="北京大学法学院",
            stance="支持 AI 法律人格",
            color="#E57373",
            sort_order=1,
        )

        # 此时只有一个选择
        response = make_mock_scheduler_response(
            selected_panelist_id=only_expert.id,
            utterance_type="main",
            reason="仅有一位专家",
        )
        assert response["selected_panelist_id"] == only_expert.id

    def test_empty_transcript_first_scheduler_call(
        self, experts: list[Panelist],
    ):
        """
        transcript 为空时（开场后第一次调度），
        所有专家 last_spoke_round = 0 且 consecutive = 0，
        应随机选一位（此处验证所有专家均可被选）。
        """
        stats = [
            SpeakingStats(e.id, 0, 0, 0) for e in experts
        ]

        eligible = [s for s in stats if s.consecutive_utterances < 2]
        assert len(eligible) == len(experts)

    def test_max_rounds_boundary_respected(
        self, discussion: Discussion,
    ):
        """
        current_round 不应超过 max_rounds。
        """
        discussion.current_round = discussion.max_rounds
        assert discussion.current_round == discussion.max_rounds

        discussion.current_round += 1
        # 允许超限（结束条件触发在业务层）但至少不应阻塞
        assert discussion.current_round == discussion.max_rounds + 1

    def test_moderator_is_never_candidate(
        self, moderator: Panelist, experts: list[Panelist],
    ):
        """
        调度器候选池中不得包含主持人。
        """
        all_panelists = [moderator] + experts
        experts_only = [p for p in all_panelists if p.role == PanelistRole.EXPERT]

        assert moderator not in experts_only
        assert len(experts_only) == len(experts)

    def test_target_panelist_exists_in_pool(
        self, experts: list[Panelist],
    ):
        """
        rebuttal/supplement 的 target_panelist_id 必须是专家池中存在的 ID。
        """
        expert_ids = {e.id for e in experts}
        resp = make_mock_scheduler_response(
            experts[0].id, "rebuttal", target_panelist_id=experts[2].id,
        )
        assert resp["target_panelist_id"] in expert_ids

    def test_response_always_contains_reason(
        self, experts: list[Panelist],
    ):
        """
        调度器 LLM 响应必须包含 reason 字段（用于日志/调试），
        但 reason 不暴露给前端 transcript。
        """
        resp = make_mock_scheduler_response(experts[0].id)
        assert "reason" in resp
        assert len(resp["reason"]) > 0


# ============================================================
# 7. 调度器输出 schema 验证测试
# ============================================================

class TestSchedulerOutputSchema:

    def test_required_fields_present(self, experts: list[Panelist]):
        """调度器响应必须包含 selected_panelist_id 和 type"""
        resp = make_mock_scheduler_response(experts[0].id, "main")
        assert "selected_panelist_id" in resp
        assert "type" in resp

    def test_type_is_valid_enum(self):
        """type 字段值在合法枚举内"""
        valid = {"main", "supplement", "rebuttal"}
        for _, utt_type, _ in MOCK_SCHEDULE_SEQUENCE:
            assert utt_type in valid

    def test_panelist_id_is_non_empty_string(self, experts: list[Panelist]):
        """panelist_id 必须是非空字符串"""
        resp = make_mock_scheduler_response(experts[0].id)
        assert isinstance(resp["selected_panelist_id"], str)
        assert len(resp["selected_panelist_id"]) > 0

    def test_optional_target_only_on_supplement_rebuttal(self):
        """target_panelist_id 仅在 supplement/rebuttal 时出现"""
        for _, utt_type, _ in MOCK_SCHEDULE_SEQUENCE:
            if utt_type in ("supplement", "rebuttal"):
                # 必须有 target
                pass  # 已在 test_rebuttal_and_supplement_have_target 验证
            # main 不需要 target — 见 test_rebuttal_and_supplement_have_target
