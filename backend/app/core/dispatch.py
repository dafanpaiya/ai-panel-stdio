"""
发言调度核心 — 上下文窗口、频率控制、发言校验、会话隔离

公共基类：提供所有 Discussion 实例共享的纯逻辑。
"""

import re
from typing import Optional

from app.core.models import (
    Panelist,
    PanelistRole,
    Utterance,
    UtteranceType,
    SpeakingStats,
    SchedulerResult,
)


# ── 发言长度 ────────────────────────────────────────────

SENTENCE_BOUNDARY = re.compile(r"[。！？.!?\n]")
MAX_SENTENCES = 2


def truncate_to_sentences(text: str, max_sentences: int = MAX_SENTENCES) -> str:
    """将文本截断为最多 max_sentences 句。超过则保留前 N 句。"""
    parts = SENTENCE_BOUNDARY.split(text)
    # 过滤纯空白
    meaningful = [p.strip() for p in parts if p.strip()]
    if len(meaningful) <= max_sentences:
        return text.strip()

    # 找到第 N 个句子边界在原字符串中的位置
    count = 0
    for match in SENTENCE_BOUNDARY.finditer(text):
        count += 1
        if count == max_sentences:
            return text[: match.end()].strip()

    # 兜底：找不到足够的句子边界，原样返回
    return text.strip()


def count_sentences(text: str) -> int:
    """估算句子数"""
    parts = [p.strip() for p in SENTENCE_BOUNDARY.split(text) if p.strip()]
    return len(parts)


# ── 上下文窗口 ────────────────────────────────────────────

DEFAULT_WINDOW_SIZE = 20  # 最近 N 条发言


def extract_context_window(
    transcript: list[Utterance],
    window_size: int = DEFAULT_WINDOW_SIZE,
) -> tuple[list[Utterance], int]:
    """
    返回 (窗口内的发言, 被截断的发言数量)。
    窗口只取最近 N 条专家发言 + 所有主持人发言（主持人发言不计入窗口配额，
    因为主持人发言是结构性的串联信息，丢了会影响上下文连贯性）。
    """
    if len(transcript) <= window_size:
        return list(transcript), 0

    # 分离主持人和专家发言
    moderator_utts = [u for u in transcript if u.type in (
        UtteranceType.OPENING, UtteranceType.MODERATOR_INTERJECTION, UtteranceType.CLOSING,
    )]
    expert_utts = [u for u in transcript if u.type not in (
        UtteranceType.OPENING, UtteranceType.MODERATOR_INTERJECTION, UtteranceType.CLOSING,
    )]

    # 保留最近的 window_size 条专家发言 + 所有主持人发言
    kept_expert = expert_utts[-window_size:] if len(expert_utts) > window_size else expert_utts
    trimmed = len(expert_utts) - len(kept_expert)

    # 合并并按 seq 排序
    combined = moderator_utts + kept_expert
    combined.sort(key=lambda u: u.seq)

    return combined, trimmed


# ── 发言频率控制 ────────────────────────────────────────────

class FrequencyController:
    """
    发言频率控制逻辑。

    规则（来自 PDR §2.3.2）：
    1. 同一专家连续发言不超过 2 次
    2. 优先选择最近未发言的专家
    3. 禁止机械式轮流发言
    4. 主持人每 3-4 轮专家发言后介入
    """

    MAX_CONSECUTIVE = 2
    MODERATOR_INTERVAL = 3  # 每 3 轮触发一次

    @staticmethod
    def build_candidate_order(
        experts: list[Panelist],
        stats: list[SpeakingStats],
    ) -> list[str]:
        """
        按优先级排序专家 ID 列表。

        规则：
        1. 排除连续发言 ≥ MAX_CONSECUTIVE 次的专家
        2. 从未发言的专家（last_spoke_round=0）最优先
        3. 按 last_spoke_round 升序（最久未发言的优先）
        4. 总发言数少的优先（平衡参与度）
        5. 全部阻塞时（极端情况），选最久未发言的
        """
        eligible = [s for s in stats if s.consecutive_utterances < FrequencyController.MAX_CONSECUTIVE]

        # 极端兜底：全部被排除时，解锁所有专家
        if not eligible:
            eligible = list(stats)

        def sort_key(s: SpeakingStats) -> tuple[int, int, int, int]:
            never_spoken = 0 if s.last_spoke_round == 0 else 1
            return (never_spoken, s.last_spoke_round, s.consecutive_utterances, s.total_utterances)

        eligible.sort(key=sort_key)
        return [s.panelist_id for s in eligible]

    @staticmethod
    def should_trigger_moderator(
        current_round: int,
        last_moderator_round: int,
    ) -> bool:
        """轮次间隔触发：距上次主持人介入 ≥ MODERATOR_INTERVAL 轮"""
        return (current_round - last_moderator_round) >= FrequencyController.MODERATOR_INTERVAL

    @staticmethod
    def is_blocked_by_consecutive(stat: SpeakingStats) -> bool:
        return stat.consecutive_utterances >= FrequencyController.MAX_CONSECUTIVE


# ── 发言校验 ────────────────────────────────────────────

class UtteranceValidator:
    """发言校验器：类型、目标、长度"""

    VALID_EXPERT_TYPES = {"main", "supplement", "rebuttal"}

    @staticmethod
    def validate_type(utt_type: str) -> bool:
        return utt_type in UtteranceValidator.VALID_EXPERT_TYPES

    @staticmethod
    def validate_target(
        target_panelist_id: Optional[str],
        speaker_id: str,
        experts: list[Panelist],
        utt_type: str,
    ) -> bool:
        """
        rebuttal/supplement 必须有 target；
        target 不能是自己；
        target 必须在专家池中。
        """
        if utt_type in ("supplement", "rebuttal"):
            if target_panelist_id is None:
                return False
            if target_panelist_id == speaker_id:
                return False
            return target_panelist_id in {e.id for e in experts}
        # main 不需要 target
        return True

    @staticmethod
    def validate_content_length(content: str, max_sentences: int = MAX_SENTENCES) -> str:
        """
        校验并截断发言内容。超过 2 句则截断到前 2 句。
        返回（可能截断后的）文本。
        """
        if count_sentences(content) > max_sentences:
            return truncate_to_sentences(content, max_sentences)
        return content


# ── 调度结果工厂 ────────────────────────────────────────────

def make_scheduler_result(
    selected_panelist_id: str,
    utt_type: str = "main",
    target_panelist_id: Optional[str] = None,
    reason: str = "",
) -> SchedulerResult:
    """构造 SchedulerResult，统一入口做校验"""
    return SchedulerResult(
        selected_panelist_id=selected_panelist_id,
        type=UtteranceType(utt_type),
        reason=reason,
        target_panelist_id=target_panelist_id,
    )
