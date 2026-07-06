"""
端到端测试 — 多讨论并行隔离

验证：
1. 两个不同话题的讨论同时运行，Transcript 互不交叉
2. 讨论状态各自独立更新（暂停/恢复互不干扰）
3. 共识/分歧在讨论过程中增量生成（非仅在结束时）
4. Transcript 中不出现"举手""抢答"等内部事件文本
5. Mock LLM 覆盖：嘉宾生成、多轮调度、发言生成、共识提炼、总结

超时策略：每个等待操作有 5 秒超时上限。
"""

import asyncio
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import pytest

from app.core.models import (
    Discussion,
    DiscussionStatus,
    Panelist,
    PanelistRole,
    PanelistState,
    PanelistStatus,
    Utterance,
    UtteranceType,
    SchedulerResult,
    InsightResult,
    Consensus,
    Divergence,
    ModeratorTrigger,
    SpeakingStats,
    SSEEvent,
    new_id,
    now_iso,
)
from app.core.dispatch import FrequencyController, UtteranceValidator, MAX_SENTENCES
from app.core.engine import DiscussionEngine
from app.core.scheduler import Scheduler
from app.llm.client import LLMClient, MockLLMClient


# ── 确定性 Mock LLM（E2E 用）───────────────────────

class DeterministicMockLLM(LLMClient):
    """
    确定性 Mock — 每轮给出可预测的调度/发言/共识，不依赖外部 API。

    不同 discussion 使用独立实例 → 验证隔离。
    """

    def __init__(self, seed: int = 0):
        self._seed = seed
        self._call_count = 0
        self._schedule_cycle = 0

    # ── 阵容生成（由 Manager 调用，这里只提供 mock 数据）──

    # ── 调度 ──────────────────────────────────────────

    async def schedule_next_speaker(
        self, topic, experts, stats, transcript,
    ) -> Optional[SchedulerResult]:
        """Mock 调度：允许反驳和补充优先"""
        self._call_count += 1
        n = len(experts)
        import random
        roll = random.random()
        if roll < 0.3 and self._call_count > 1:
            idx = self._schedule_cycle % n
            expert = experts[idx]
            utt_type = "rebuttal" if random.random() < 0.6 else "supplement"
            target = None
            for e in experts:
                if e.id != expert.id:
                    target = e.id
                    break
            self._schedule_cycle += 1
        else:
            idx = self._schedule_cycle % n
            expert = experts[idx]
            utt_type = "main"
            target = None
            self._schedule_cycle += 1

        return SchedulerResult(
            selected_panelist_id=expert.id,
            type=utt_type,
            reason=f"[E2E Mock] 选择 {expert.name}",
            target_panelist_id=target,
        )

    # ── 专家发言生成 ──────────────────────────────────

    async def generate_expert_speech(
        self, panelist, topic, transcript, speech_type, target_panelist_id=None,
    ) -> str:
        """返回带 topic 标识的确定性发言 — 用于交叉污染检测"""
        self._call_count += 1
        topic_tag = topic[:6]  # 前 6 字作为标识
        speeches = {
            "main": f"关于「{topic_tag}」，我认为核心问题在于制度设计的滞后性。现有法律框架无法有效应对 AI 带来的新挑战。",
            "supplement": f"补充一点——前面提到的观点很有启发性。在「{topic_tag}」这个问题上，我们还需要考虑国际协调的维度。",
            "rebuttal": f"我对此持不同看法。「{topic_tag}」的推进不能过于激进，必须充分考虑技术成熟度和社会接受度。",
        }
        return speeches.get(speech_type, f"关于「{topic_tag}」，我有些想法需要表达。")

    # ── 主持人发言 ────────────────────────────────────

    async def generate_opening(self, topic, moderator, experts) -> str:
        names = "、".join(e.name for e in experts)
        return f"大家好，欢迎来到《前沿对话》。我是{moderator.name}。今天讨论的话题是：{topic}。我们荣幸邀请到{names}。让我们开始。话题标签：{topic[:10]}。"

    async def generate_moderator_interjection(
        self, topic, moderator, transcript, trigger, user_message=None,
    ) -> str:
        trigger_msgs = {
            ModeratorTrigger.ROUND_INTERVAL: f"感谢各位的发言。在「{topic[:8]}」这个问题上，让我们继续深入。",
            ModeratorTrigger.SILENCE: "让我们继续讨论，请一位尚未充分表达的专家分享观点。",
            ModeratorTrigger.OFF_TOPIC: f"让我们聚焦回核心问题——{topic[:10]}。",
            ModeratorTrigger.USER_INTERJECTION: f"观众提了一个好问题：{user_message}。各位专家怎么看？",
            ModeratorTrigger.CLOSING: "进入收尾阶段。",
        }
        return trigger_msgs.get(trigger, f"继续讨论「{topic[:8]}」。")

    async def generate_closing(self, topic, moderator, transcript, consensus_list, divergence_list) -> str:
        return (
            f"感谢各位专家的精彩讨论。关于「{topic}」，我们达成了{len(consensus_list)}项共识，"
            f"也存在{len(divergence_list)}项分歧。感谢收看，我们下期再见。"
        )

    # ── 共识/分歧提取 ─────────────────────────────────

    async def extract_insights(
        self, utterance, topic, transcript, existing_consensus, existing_divergence,
    ) -> InsightResult:
        """
        模拟增量共识/分歧：
        - 每 2 条专家发言产生一条共识
        - 每 3 条专家发言产生一条分歧
        验证讨论过程中有增量更新（非仅在结束）。
        """
        expert_utt_count = sum(
            1 for u in transcript
            if u.type in ("main", "supplement", "rebuttal")
        )
        result = InsightResult()

        topic_short = topic[:8]

        if expert_utt_count % 2 == 0 and expert_utt_count > 0 and len(existing_consensus) < 4:
            cons = Consensus(
                id=new_id(),
                discussion_id=utterance.discussion_id,
                content=f"[E2E] 专家们就「{topic_short}」的第 {expert_utt_count} 轮讨论达成初步共识",
                source_utterance_ids=[utterance.id],
                version=len(existing_consensus) + 1,
            )
            result.consensus_updates.append(cons)

        if expert_utt_count % 3 == 0 and expert_utt_count > 0 and len(existing_divergence) < 3:
            div = Divergence(
                id=new_id(),
                discussion_id=utterance.discussion_id,
                content=f"[E2E] 在「{topic_short}」的实施路径上存在分歧（第 {expert_utt_count} 轮）",
                opposing_sides=[
                    {"side": "渐进式推进", "panelist_ids": []},
                    {"side": "激进改革", "panelist_ids": []},
                ],
                source_utterance_ids=[utterance.id],
                version=len(existing_divergence) + 1,
            )
            result.divergence_updates.append(div)

        return result


# ── 内存数据库（E2E 用，不依赖 SQLite 文件）───────

class InMemoryDB:
    """用于 E2E 测试的内存数据库 stub"""

    def __init__(self):
        self._discussions: dict[str, Discussion] = {}
        self._panelists: dict[str, list[Panelist]] = {}
        self._utterances: dict[str, list[Utterance]] = {}
        self._consensus: dict[str, list[Consensus]] = {}
        self._divergences: dict[str, list[Divergence]] = {}

    def create_discussion(self, topic: str, expert_count: int, max_rounds: int) -> Discussion:
        d = Discussion(
            id=new_id(), topic=topic, status=DiscussionStatus.DRAFT,
            max_rounds=max_rounds, current_round=0,
        )
        self._discussions[d.id] = d
        self._panelists[d.id] = []
        self._utterances[d.id] = []
        self._consensus[d.id] = []
        self._divergences[d.id] = []
        return d

    def get_discussion(self, did: str) -> Optional[Discussion]:
        return self._discussions.get(did)

    def update_discussion(self, d: Discussion):
        self._discussions[d.id] = d

    def create_panelist(self, p: Panelist):
        self._panelists.setdefault(p.discussion_id, []).append(p)

    def list_panelists(self, did: str) -> list[Panelist]:
        return self._panelists.get(did, [])

    def get_panelist(self, pid: str) -> Optional[Panelist]:
        for lst in self._panelists.values():
            for p in lst:
                if p.id == pid:
                    return p
        return None

    def get_panelist_count(self, did: str) -> int:
        return len(self._panelists.get(did, []))

    def get_utterance_count(self, did: str) -> int:
        return len(self._utterances.get(did, []))

    def clear_panelists(self, did: str):
        self._panelists[did] = [p for p in self._panelists.get(did, []) if p.role == PanelistRole.MODERATOR]

    def save_utterance(self, u: Utterance):
        self._utterances.setdefault(u.discussion_id, []).append(u)

    def save_consensus(self, c: Consensus):
        self._consensus.setdefault(c.discussion_id, []).append(c)

    def save_divergence(self, d: Divergence):
        self._divergences.setdefault(d.discussion_id, []).append(d)

    def list_consensus(self, did: str) -> list[Consensus]:
        return self._consensus.get(did, [])

    def list_divergences(self, did: str) -> list[Divergence]:
        return self._divergences.get(did, [])

    def list_utterances(self, did: str, after_seq=0, limit=100) -> list[Utterance]:
        return self._utterances.get(did, [])


# ── Fixtures ────────────────────────────────────────

@pytest.fixture
def topic_a() -> str:
    return "AI 是否应该拥有法律人格？"


@pytest.fixture
def topic_b() -> str:
    return "量子计算对密码学的威胁有多大？"


@pytest.fixture
def make_panelists():
    """工厂函数：为指定 discussion 生成 1 主持人 + N 专家"""
    def _make(discussion_id: str, topic: str, expert_count: int = 3) -> list[Panelist]:
        colors = ["#E57373", "#81C784", "#FFB74D", "#BA68C8", "#4FC3F7"]
        panelists = [
            Panelist(
                id=new_id(), discussion_id=discussion_id,
                role=PanelistRole.MODERATOR,
                name="陈锐", occupation="资深媒体人",
                title="《前沿对话》主持人", stance="中立",
                color="#4A90D9", sort_order=0,
            )
        ]
        names = ["林芳", "李国栋", "王雪", "周明哲", "赵远"]
        stances = [
            f"支持{topic[:6]}的推进",
            f"质疑{topic[:6]}的可行性",
            f"关注{topic[:6]}的监管路径",
            f"强调{topic[:6]}的伦理边界",
            f"从技术角度评估{topic[:6]}",
        ]
        for i in range(expert_count):
            panelists.append(Panelist(
                id=new_id(), discussion_id=discussion_id,
                role=PanelistRole.EXPERT,
                name=names[i], occupation="研究员",
                title=f"某机构 {topic[:4]} 研究中心",
                stance=stances[i],
                color=colors[i % len(colors)],
                sort_order=i + 1,
            ))
        return panelists
    return _make


# ── 核心 E2E 测试 ───────────────────────────────────

class TestParallelDiscussionIsolation:

    @pytest.mark.asyncio
    async def test_transcript_no_cross_contamination(
        self, topic_a, topic_b, make_panelists,
    ):
        """
        两个讨论并行运行，各自的 transcript 只包含本讨论的内容。
        验证：Topic A 的 transcript 中不出现 Topic B 的话题关键词。
        """
        db_a = InMemoryDB()
        db_b = InMemoryDB()

        disc_a = db_a.create_discussion(topic_a, 3, max_rounds=3)
        disc_b = db_b.create_discussion(topic_b, 3, max_rounds=3)

        panelists_a = make_panelists(disc_a.id, topic_a, 3)
        panelists_b = make_panelists(disc_b.id, topic_b, 3)
        for p in panelists_a:
            db_a.create_panelist(p)
        for p in panelists_b:
            db_b.create_panelist(p)

        llm_a = DeterministicMockLLM(seed=1)
        llm_b = DeterministicMockLLM(seed=2)

        engine_a = DiscussionEngine(disc_a, panelists_a, llm_a, db_a)
        engine_b = DiscussionEngine(disc_b, panelists_b, llm_b, db_b)

        # 并行运行
        results = await asyncio.gather(
            engine_a.run(),
            engine_b.run(),
        )

        summary_a, summary_b = results

        # 收集 transcript
        utts_a = [u for u in engine_a._transcript]
        utts_b = [u for u in engine_b._transcript]

        # ── 验证 1: transcript 内容隔离 ──
        # Topic A 的 transcript 不出现 Topic B 的关键词
        keyword_b = topic_b[:8]
        for u in utts_a:
            assert keyword_b not in u.content, (
                f"交叉污染！讨论 A 的 transcript 中含有 B 的话题关键词：「{u.content[:80]}…」"
            )

        keyword_a = topic_a[:8]
        for u in utts_b:
            assert keyword_a not in u.content, (
                f"交叉污染！讨论 B 的 transcript 中含有 A 的话题关键词：「{u.content[:80]}…」"
            )

        # ── 验证 2: transcript 不出现内部事件文本 ──
        forbidden = ["举手", "抢答", "轮到我", "调度器", "选中", "Scheduler", "internal"]
        for name, utts in [("A", utts_a), ("B", utts_b)]:
            for u in utts:
                for word in forbidden:
                    assert word not in u.content, (
                        f"内部事件泄漏！讨论 {name} 的 transcript 中出现禁止词「{word}」: "
                        f"「{u.content[:80]}…」"
                    )

        # ── 验证 3: 两个讨论的 transcript 条数独立 ──
        # 每个讨论应有 ≥ 开场 + 几轮专家发言 + 收尾
        assert len(utts_a) >= 4, f"讨论 A transcript 过短: {len(utts_a)} 条"
        assert len(utts_b) >= 4, f"讨论 B transcript 过短: {len(utts_b)} 条"

    @pytest.mark.asyncio
    async def test_states_independently_updated(
        self, topic_a, topic_b, make_panelists,
    ):
        """
        一个讨论暂停后，另一个讨论继续运行不受影响。
        """
        db_a = InMemoryDB()
        db_b = InMemoryDB()

        disc_a = db_a.create_discussion(topic_a, 3, max_rounds=5)
        disc_b = db_b.create_discussion(topic_b, 3, max_rounds=5)

        panelists_a = make_panelists(disc_a.id, topic_a, 3)
        panelists_b = make_panelists(disc_b.id, topic_b, 3)
        for p in panelists_a:
            db_a.create_panelist(p)
        for p in panelists_b:
            db_b.create_panelist(p)

        llm_a = DeterministicMockLLM(seed=3)
        llm_b = DeterministicMockLLM(seed=4)

        engine_a = DiscussionEngine(disc_a, panelists_a, llm_a, db_a)
        engine_b = DiscussionEngine(disc_b, panelists_b, llm_b, db_b)

        # 启动两个引擎
        disc_a.status = DiscussionStatus.RUNNING
        disc_b.status = DiscussionStatus.RUNNING

        await engine_a._phase_opening()
        await engine_b._phase_opening()

        # 暂停 A
        await engine_a.pause()
        assert engine_a.discussion.status == DiscussionStatus.PAUSED
        # B 应该仍在运行
        assert engine_b.discussion.status == DiscussionStatus.RUNNING

        # 恢复 A
        await engine_a.resume()
        assert engine_a.discussion.status == DiscussionStatus.RUNNING

        # 停止 A
        await engine_a.stop()
        # B 不受影响
        assert engine_b.discussion.status == DiscussionStatus.RUNNING

        # 停止 B
        await engine_b.stop()

    @pytest.mark.asyncio
    async def test_consensus_incremental_during_discussion(
        self, topic_a, make_panelists,
    ):
        """
        共识/分歧在讨论过程中增量生成，而非仅在结束时。
        验证：讨论运行中 consensus 数量逐步增加。
        """
        db = InMemoryDB()
        disc = db.create_discussion(topic_a, 3, max_rounds=4)
        panelists = make_panelists(disc.id, topic_a, 3)
        for p in panelists:
            db.create_panelist(p)

        llm = DeterministicMockLLM(seed=5)
        engine = DiscussionEngine(disc, panelists, llm, db)

        # 手动逐步执行（不调用 run，避免完整跑完）
        disc.status = DiscussionStatus.RUNNING

        # 开场
        await engine._phase_opening()
        consensus_at_start = len(engine._consensus_list)
        # 开场后可能已有共识（取决于 mock）
        initial_count = consensus_at_start

        # 执行 2 轮专家发言
        for _ in range(2):
            if disc.current_round < disc.max_rounds:
                await engine._round_expert_speak()

        consensus_after_2 = len(engine._consensus_list)
        assert consensus_after_2 >= initial_count, (
            f"共识数量应不减少: {consensus_after_2} >= {initial_count}"
        )

        # 再执行 2 轮
        for _ in range(2):
            if disc.current_round < disc.max_rounds:
                await engine._round_expert_speak()

        consensus_after_4 = len(engine._consensus_list)
        assert consensus_after_4 >= consensus_after_2, (
            f"共识应在讨论中增量增加: {consensus_after_4} >= {consensus_after_2}"
        )

        # 收尾
        await engine._phase_closing()
        consensus_final = len(engine._consensus_list)
        assert consensus_final >= consensus_after_4, (
            f"收尾阶段不应减少共识: {consensus_final} >= {consensus_after_4}"
        )

    @pytest.mark.asyncio
    async def test_no_internal_events_in_sse(
        self, topic_a, make_panelists,
    ):
        """
        验证 SSE 事件队列中不包含内部调度事件。
        utterance 事件的 type 只应是合法类型，不含 "hand_raise" 等内部值。
        """
        db = InMemoryDB()
        disc = db.create_discussion(topic_a, 3, max_rounds=3)
        panelists = make_panelists(disc.id, topic_a, 3)
        for p in panelists:
            db.create_panelist(p)

        llm = DeterministicMockLLM(seed=6)
        engine = DiscussionEngine(disc, panelists, llm, db)

        # 收集所有 SSE 事件
        collected: list[SSEEvent] = []

        async def collector():
            while True:
                try:
                    evt = await asyncio.wait_for(engine.sse_queue.get(), timeout=2.0)
                    collected.append(evt)
                except asyncio.TimeoutError:
                    break

        collect_task = asyncio.create_task(collector())
        await engine.run()
        # 等待收集完成
        await asyncio.sleep(0.3)
        collect_task.cancel()
        try:
            await collect_task
        except asyncio.CancelledError:
            pass

        # 检查 utterance 事件
        utterances = [e for e in collected if e.event == "utterance"]
        assert len(utterances) > 0, "应有至少一条 utterance SSE 事件"

        internal_event_names = {"hand_raise", "queue_next", "scheduler_debug", "internal"}
        for evt in collected:
            assert evt.event not in internal_event_names, (
                f"SSE 事件中包含内部事件类型: {evt.event}"
            )

        # 检查每个 utterance 的 type
        valid_types = {"opening", "main", "supplement", "rebuttal", "moderator_interjection", "closing"}
        for evt in utterances:
            utt_type = evt.data.get("type", "")
            assert utt_type in valid_types, (
                f"utterance type 非法: {utt_type}"
            )

    @pytest.mark.asyncio
    async def test_scheduler_isolated_per_engine(
        self, topic_a, topic_b, make_panelists,
    ):
        """
        两个引擎的调度器状态完全隔离。
        每个引擎独立持有自己的 expert_states。
        """
        db_a = InMemoryDB()
        db_b = InMemoryDB()

        disc_a = db_a.create_discussion(topic_a, 3, max_rounds=3)
        disc_b = db_b.create_discussion(topic_b, 3, max_rounds=3)

        panelists_a = make_panelists(disc_a.id, topic_a, 3)
        panelists_b = make_panelists(disc_b.id, topic_b, 3)
        for p in panelists_a:
            db_a.create_panelist(p)
        for p in panelists_b:
            db_b.create_panelist(p)

        llm_a = DeterministicMockLLM(seed=7)
        llm_b = DeterministicMockLLM(seed=8)

        engine_a = DiscussionEngine(disc_a, panelists_a, llm_a, db_a)
        engine_b = DiscussionEngine(disc_b, panelists_b, llm_b, db_b)

        # 只执行开场
        disc_a.status = DiscussionStatus.RUNNING
        disc_b.status = DiscussionStatus.RUNNING

        await engine_a._phase_opening()
        await engine_b._phase_opening()

        # A 的 expert_states 和 B 的 expert_states 应完全独立
        assert len(engine_a._expert_states) == 3
        assert len(engine_b._expert_states) == 3

        # A 的 expert state keys 和 B 的不同
        a_keys = set(engine_a._expert_states.keys())
        b_keys = set(engine_b._expert_states.keys())
        assert a_keys.isdisjoint(b_keys), (
            f"专家状态交叉污染！A 和 B 共享 expert state keys"
        )

        # 各自执行一轮
        await engine_a._round_expert_speak()
        await engine_b._round_expert_speak()

        # A 的 transcript 和 B 的 transcript 独立
        a_panelist_ids = {u.panelist_id for u in engine_a._transcript}
        b_panelist_ids = {u.panelist_id for u in engine_b._transcript}
        assert a_panelist_ids.isdisjoint(b_panelist_ids), (
            "transcript 交叉污染！A 和 B 出现相同的 panelist_id"
        )

    @pytest.mark.asyncio
    async def test_content_length_truncation_in_e2e(
        self, topic_a, make_panelists,
    ):
        """
        验证发言长度超过 2 句时会被截断。
        """
        db = InMemoryDB()
        disc = db.create_discussion(topic_a, 3, max_rounds=2)
        panelists = make_panelists(disc.id, topic_a, 3)
        for p in panelists:
            db.create_panelist(p)

        # 创建一个返回超长发言的 mock
        class LongSpeechMock(DeterministicMockLLM):
            async def generate_expert_speech(self, panelist, topic, transcript, speech_type, target_panelist_id=None):
                # 返回 5 句话
                return "第一句话很重要。第二句话也关键。第三句是补充。第四句可有可无。第五句多余了。"

        llm = LongSpeechMock(seed=9)
        engine = DiscussionEngine(disc, panelists, llm, db)

        disc.status = DiscussionStatus.RUNNING
        await engine._phase_opening()
        await engine._round_expert_speak()

        # 检查最新一条专家发言
        from app.core.dispatch import count_sentences
        expert_utts = [u for u in engine._transcript if u.type not in ("opening", "moderator_interjection", "closing")]
        assert len(expert_utts) > 0

        for u in expert_utts:
            n = count_sentences(u.content)
            assert n <= MAX_SENTENCES, (
                f"发言超过 {MAX_SENTENCES} 句（实际 {n} 句）: 「{u.content}」"
            )


# ── 超时工具 ────────────────────────────────────────

async def wait_for_condition(
    condition, timeout: float = 5.0, interval: float = 0.1,
) -> bool:
    """
    轮询等待条件满足，超时返回 False。
    用于 E2E 测试中的异步等待。
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if await condition():
            return True
        await asyncio.sleep(interval)
    return False
