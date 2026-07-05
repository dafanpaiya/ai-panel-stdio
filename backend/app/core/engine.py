"""
讨论引擎 — 每个 Discussion 实例的核心编排器。

管理讨论生命周期：开场 → 主循环（调度→发言→共识/分歧）→ 收尾。
每个 DiscussionEngine 独立运行 — 独立 transcript、独立 seq、独立状态，
多讨论完全隔离。
"""

import asyncio
import logging
from typing import Optional

from app.core.models import (
    Discussion,
    DiscussionStatus,
    Panelist,
    PanelistRole,
    PanelistStatus,
    PanelistState,
    Utterance,
    UtteranceType,
    ModeratorTrigger,
    Consensus,
    Divergence,
    SSEEvent,
    now_iso,
    new_id,
)
from app.core.scheduler import Scheduler
from app.core.speaking_stats import SpeakingStatsCalculator
from app.core.moderator import ModeratorTriggerLogic
from app.core.dispatch import (
    extract_context_window,
    truncate_to_sentences,
    count_sentences,
    DEFAULT_WINDOW_SIZE,
    MAX_SENTENCES,
    FrequencyController,
)

logger = logging.getLogger(__name__)


# ── SSE 事件工厂 ─────────────────────────────────────

def _utterance_event(u: Utterance, panelist: Panelist) -> SSEEvent:
    return SSEEvent("utterance", {
        "id": u.id, "discussion_id": u.discussion_id, "type": u.type,
        "panelist": {
            "id": panelist.id, "name": panelist.name,
            "occupation": panelist.occupation, "title": panelist.title,
            "color": panelist.color, "role": panelist.role,
        },
        "content": u.content, "round": u.round, "seq": u.seq, "created_at": u.created_at,
    })


def _panelist_state_event(ps: PanelistState, panelist: Panelist) -> SSEEvent:
    return SSEEvent("panelist_status", {
        "panelist_id": ps.panelist_id, "panelist_name": panelist.name,
        "role": panelist.role, "color": panelist.color,
        "status": ps.status, "focus": ps.focus,
    })


def _moderating_event(trigger: ModeratorTrigger, message: str) -> SSEEvent:
    return SSEEvent("moderating", {"trigger": trigger.value, "message": message})


def _insight_update_event(insight_type: str, action: str, insight) -> SSEEvent:
    event_name = "consensus_update" if insight_type == "consensus" else "divergence_update"
    data = {
        "action": action,
        insight_type: {
            "id": insight.id, "content": insight.content,
            "version": insight.version,
            "source_utterance_ids": insight.source_utterance_ids,
        },
    }
    if insight_type == "divergence":
        data[insight_type]["opposing_sides"] = insight.opposing_sides
    return SSEEvent(event_name, data)


def _heartbeat_event(discussion_id: str) -> SSEEvent:
    return SSEEvent("heartbeat", {"timestamp": now_iso(), "discussion_id": discussion_id})


# ── 引擎 ────────────────────────────────────────────

class DiscussionEngine:
    """
    单个讨论的编排引擎 — 每个 instance 持有完全隔离的状态。

    会话隔离保证：
      - self._transcript：仅本讨论的发言列表
      - self._seq：独立的序号计数器
      - self._last_moderator_round：独立的主持人介入追踪
      - self._expert_states：独立的专家状态机
    """

    def __init__(
        self,
        discussion: Discussion,
        panelists: list[Panelist],
        llm_client,
        db,
        window_size: int = DEFAULT_WINDOW_SIZE,
    ):
        self.discussion = discussion
        self.panelists = panelists
        self.llm = llm_client
        self.db = db
        self._window_size = window_size

        # ── 实例级隔离状态 ──
        self._queue: asyncio.Queue[SSEEvent] = asyncio.Queue()
        self._transcript: list[Utterance] = []
        self._seq = 0
        self._last_moderator_round = 0
        self._expert_states: dict[str, PanelistState] = {}
        self._consensus_list: list[Consensus] = []
        self._divergence_list: list[Divergence] = []
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._stop_event = asyncio.Event()

        self._moderator_trigger = ModeratorTriggerLogic()

        for p in self.experts:
            state = PanelistState(panelist_id=p.id, discussion_id=discussion.id)
            self._expert_states[p.id] = state

    # ── 属性 ──────────────────────────────────────────

    @property
    def moderator(self) -> Panelist:
        for p in self.panelists:
            if p.role == PanelistRole.MODERATOR:
                return p
        raise ValueError("No moderator found in panelists")

    @property
    def experts(self) -> list[Panelist]:
        return [p for p in self.panelists if p.role == PanelistRole.EXPERT]

    @property
    def sse_queue(self) -> asyncio.Queue[SSEEvent]:
        return self._queue

    # ── 控制方法 ──────────────────────────────────────

    async def pause(self):
        self._pause_event.clear()
        self.discussion.status = DiscussionStatus.PAUSED

    async def resume(self):
        self._pause_event.set()
        self.discussion.status = DiscussionStatus.RUNNING

    async def stop(self):
        self._stop_event.set()

    async def interject(self, message: str):
        self._moderator_trigger.enqueue_interjection(message)

    # ── 主循环 ────────────────────────────────────────

    async def run(self) -> str:
        self.discussion.status = DiscussionStatus.RUNNING

        try:
            await self._phase_opening()

            while self.discussion.current_round < self.discussion.max_rounds:
                await self._pause_event.wait()
                if self._stop_event.is_set():
                    break

                trigger = self._moderator_trigger.evaluate(
                    self.discussion, self._transcript,
                    last_moderator_round=self._last_moderator_round,
                )

                if trigger:
                    await self._handle_moderator_trigger(trigger)
                else:
                    await self._round_expert_speak()

                await self._queue.put(_heartbeat_event(self.discussion.id))

            summary = await self._phase_closing()
            return summary

        except Exception as e:
            logger.exception(f"讨论引擎异常: {e}")
            raise
        finally:
            self.discussion.status = DiscussionStatus.ENDED

    # ── Phase 1: 开场 ─────────────────────────────────

    async def _phase_opening(self):
        await self._broadcast_moderating(ModeratorTrigger.OPENING, "主持人进行开场介绍…")

        opening_content = await self.llm.generate_opening(
            topic=self.discussion.topic,
            moderator=self.moderator,
            experts=self.experts,
        )

        utterance = self._commit_utterance(
            panelist_id=self.moderator.id,
            utt_type=UtteranceType.OPENING,
            content=opening_content,
        )

        self._last_moderator_round = 1
        await self._queue.put(_utterance_event(utterance, self.moderator))

    # ── Phase 2a: 主持人介入 ──────────────────────────

    async def _handle_moderator_trigger(self, trigger: ModeratorTrigger):
        msg = self._trigger_message(trigger)
        await self._broadcast_moderating(trigger, msg)

        user_msg = None
        if trigger == ModeratorTrigger.USER_INTERJECTION:
            user_msg = self._moderator_trigger.get_pending_interjection()

        interjection = await self.llm.generate_moderator_interjection(
            topic=self.discussion.topic,
            moderator=self.moderator,
            transcript=self._transcript,
            trigger=trigger,
            user_message=user_msg,
        )

        utterance = self._commit_utterance(
            panelist_id=self.moderator.id,
            utt_type=UtteranceType.MODERATOR_INTERJECTION,
            content=interjection,
        )

        self._last_moderator_round = self.discussion.current_round
        await self._queue.put(_utterance_event(utterance, self.moderator))

    def _trigger_message(self, trigger: ModeratorTrigger) -> str:
        messages = {
            ModeratorTrigger.ROUND_INTERVAL: f"主持人串联第 {self.discussion.current_round} 轮讨论…",
            ModeratorTrigger.SILENCE: "检测到冷场，主持人追问引导…",
            ModeratorTrigger.OFF_TOPIC: "检测到讨论偏题，主持人纠正方向…",
            ModeratorTrigger.USER_INTERJECTION: "用户插入追问，主持人转述并引导…",
            ModeratorTrigger.CLOSING: "主持人进行收尾总结…",
            ModeratorTrigger.OPENING: "主持人进行开场介绍…",
        }
        return messages.get(trigger, "主持人介入…")

    # ── Phase 2b: 专家发言 ────────────────────────────

    async def _round_expert_speak(self):
        """
        一轮专家发言：调度 → 发言生成 → 长度校验 → 共识/分歧。
        每次发言控制在 1-2 句自然语言（MAX_SENTENCES 约束）。
        """
        self.discussion.current_round += 1

        # Step 1: 调度
        stats = SpeakingStatsCalculator.calculate(self.experts, self._transcript)

        # 使用上下文窗口缩减传给 LLM 的数据量
        context_transcript, trimmed = extract_context_window(
            self._transcript, self._window_size,
        )
        if trimmed > 0:
            logger.debug(f"讨论 {self.discussion.id} 上下文窗口：截断 {trimmed} 条早期发言")

        scheduler_result = await self.llm.schedule_next_speaker(
            topic=self.discussion.topic,
            experts=self.experts,
            stats=stats,
            transcript=context_transcript,
        )
        result = Scheduler.pick_next(self.experts, stats, scheduler_result)

        speaker = self._get_panelist(result.selected_panelist_id)

        # idled → preparing
        state = self._expert_states[speaker.id]
        state.set_preparing(f"正在思考关于 {self.discussion.topic} 的观点…")
        await self._queue.put(_panelist_state_event(state, speaker))

        # Step 2: 发言生成
        raw_content = await self.llm.generate_expert_speech(
            panelist=speaker,
            topic=self.discussion.topic,
            transcript=context_transcript,
            speech_type=result.type,
            target_panelist_id=result.target_panelist_id,
        )

        # ── 发言长度校验：超过 2 句则截断 ──
        content = truncate_to_sentences(raw_content, MAX_SENTENCES)

        # preparing → speaking
        preview = content[:60] + "…" if len(content) > 60 else content
        state.set_speaking(preview)
        await self._queue.put(_panelist_state_event(state, speaker))

        # 提交发言
        utterance = self._commit_utterance(
            panelist_id=speaker.id,
            utt_type=UtteranceType(result.type),
            content=content,
        )
        await self._queue.put(_utterance_event(utterance, speaker))

        # speaking → idle
        state.set_idle(f"刚发表了关于 {self.discussion.topic} 的观点")
        await self._queue.put(_panelist_state_event(state, speaker))

        # Step 3: 增量共识/分歧
        await self._update_insights(utterance)

    # ── Phase 3: 收尾 ─────────────────────────────────

    async def _phase_closing(self) -> str:
        await self._broadcast_moderating(ModeratorTrigger.CLOSING, "主持人进行收尾总结…")

        summary = await self.llm.generate_closing(
            topic=self.discussion.topic,
            moderator=self.moderator,
            transcript=self._transcript,
            consensus_list=self._consensus_list,
            divergence_list=self._divergence_list,
        )

        utterance = self._commit_utterance(
            panelist_id=self.moderator.id,
            utt_type=UtteranceType.CLOSING,
            content=summary,
        )
        await self._queue.put(_utterance_event(utterance, self.moderator))

        await self._queue.put(SSEEvent("discussion_ended", {
            "discussion_id": self.discussion.id,
            "summary": summary,
            "total_rounds": self.discussion.current_round,
            "total_utterances": self._seq,
            "consensus_count": len(self._consensus_list),
            "divergence_count": len(self._divergence_list),
            "ended_at": now_iso(),
        }))

        return summary

    # ── 共识/分歧增量更新 ─────────────────────────────

    async def _update_insights(self, utterance: Utterance):
        result = await self.llm.extract_insights(
            utterance=utterance,
            topic=self.discussion.topic,
            transcript=self._transcript,
            existing_consensus=self._consensus_list,
            existing_divergence=self._divergence_list,
        )

        for c in result.consensus_updates:
            self._consensus_list.append(c)
            await self._queue.put(_insight_update_event("consensus", "new", c))
            await self.db.save_consensus(c)

        for d in result.divergence_updates:
            self._divergence_list.append(d)
            await self._queue.put(_insight_update_event("divergence", "new", d))
            await self.db.save_divergence(d)

    # ── 工具方法 ──────────────────────────────────────

    def _get_panelist(self, panelist_id: str) -> Panelist:
        for p in self.panelists:
            if p.id == panelist_id:
                return p
        raise ValueError(f"Panelist not found: {panelist_id}")

    def _commit_utterance(
        self, panelist_id: str, utt_type: UtteranceType, content: str,
    ) -> Utterance:
        self._seq += 1
        u = Utterance(
            id=new_id(),
            discussion_id=self.discussion.id,
            panelist_id=panelist_id,
            type=utt_type,
            content=content,
            round=self.discussion.current_round,
            seq=self._seq,
            created_at=now_iso(),
        )
        self._transcript.append(u)
        return u

    async def _broadcast_moderating(self, trigger: ModeratorTrigger, message: str):
        await self._queue.put(_moderating_event(trigger, message))
