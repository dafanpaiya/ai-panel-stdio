"""
主持人触发逻辑。

根据 PDR §2.3.3，主持人不参与调度池，由引擎按条件直接触发。
使用 dispatch.FrequencyController 的 MODERATOR_INTERVAL。
"""

from datetime import datetime, timezone
from typing import Optional

from app.core.models import Discussion, Utterance, ModeratorTrigger
from app.core.dispatch import FrequencyController


class ModeratorTriggerLogic:
    """
    判断主持人是否应在当前状态介入。

    触发条件优先级（高到低）：
    1. 开场（opening）— 讨论刚启动
    2. 收尾（closing）— 达到最大轮次或用户主动结束
    3. 用户追问（user_interjection）— 用户发送了追问
    4. 跑题（off_topic）— LLM 检测到偏题
    5. 冷场（silence）— 超时无新发言
    6. 轮次间隔（round_interval）— 每 N 轮专家发言后
    """

    ROUND_INTERVAL_THRESHOLD = FrequencyController.MODERATOR_INTERVAL
    SILENCE_THRESHOLD_SECONDS = 30

    def __init__(self):
        self._pending_interjection: Optional[str] = None

    # ── 公开 API ──────────────────────────────────────

    def evaluate(
        self,
        discussion: Discussion,
        transcript: list[Utterance],
        last_moderator_round: int = 0,
        off_topic_detected: bool = False,
        force_close: bool = False,
    ) -> Optional[ModeratorTrigger]:
        """按优先级评估所有触发条件，返回第一个命中的 trigger。"""

        # 1. 用户追问（最高优先级）
        if self._pending_interjection is not None:
            return ModeratorTrigger.USER_INTERJECTION

        # 2. 收尾
        if force_close or discussion.current_round >= discussion.max_rounds:
            return ModeratorTrigger.CLOSING

        # 3. 跑题
        if off_topic_detected:
            return ModeratorTrigger.OFF_TOPIC

        # 4. 冷场
        if self._detect_silence(transcript):
            return ModeratorTrigger.SILENCE

        # 5. 轮次间隔 — 使用 FrequencyController 的共享常量
        if FrequencyController.should_trigger_moderator(
            discussion.current_round, last_moderator_round,
        ):
            return ModeratorTrigger.ROUND_INTERVAL

        return None

    def get_pending_interjection(self) -> Optional[str]:
        msg = self._pending_interjection
        self._pending_interjection = None
        return msg

    def enqueue_interjection(self, message: str) -> None:
        self._pending_interjection = message

    def has_pending_interjection(self) -> bool:
        return self._pending_interjection is not None

    # ── 私有方法 ──────────────────────────────────────

    def _detect_silence(self, transcript: list[Utterance]) -> bool:
        if not transcript:
            return False
        last_utt = max(transcript, key=lambda u: u.created_at)
        try:
            last_time = datetime.fromisoformat(last_utt.created_at)
            elapsed = (datetime.now(timezone.utc) - last_time).total_seconds()
            return elapsed >= self.SILENCE_THRESHOLD_SECONDS
        except (ValueError, TypeError):
            return False
