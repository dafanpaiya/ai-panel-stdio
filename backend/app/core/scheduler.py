"""
发言调度器 — 两步管道第一步（Scheduler 门面）

委派给 dispatch 模块的纯逻辑处理。
每个 Discussion 实例独立持有自己的候选排序上下文。
"""

from typing import Optional

from app.core.models import Panelist, SpeakingStats, SchedulerResult, UtteranceType
from app.core.dispatch import (
    FrequencyController,
    UtteranceValidator,
    make_scheduler_result,
)


class Scheduler:
    """
    专家发言调度器门面。

    纯逻辑由 dispatch.FrequencyController / UtteranceValidator 处理。
    Scheduler 自身只做 LLM 决策的融合。
    """

    @staticmethod
    def build_candidate_order(
        experts: list[Panelist],
        stats: list[SpeakingStats],
    ) -> list[str]:
        """委派给 FrequencyController"""
        return FrequencyController.build_candidate_order(experts, stats)

    @staticmethod
    def pick_next(
        experts: list[Panelist],
        stats: list[SpeakingStats],
        llm_decision: Optional[SchedulerResult] = None,
    ) -> SchedulerResult:
        """综合候选排序 + LLM 决策，选出下一位发言者"""
        candidates = Scheduler.build_candidate_order(experts, stats)

        if llm_decision and llm_decision.selected_panelist_id in candidates:
            return llm_decision

        reason = (
            "LLM 选中的专家不在候选列表中，fallback"
            if llm_decision else "候选排序第一位（优先级最高）"
        )
        return make_scheduler_result(
            selected_panelist_id=candidates[0],
            utt_type="main",
            reason=reason,
        )

    @staticmethod
    def is_valid_target(
        target_panelist_id: Optional[str],
        speaker_id: str,
        experts: list[Panelist],
    ) -> bool:
        """校验 target_panelist_id"""
        # 对 main 类型不需要 target
        return UtteranceValidator.validate_target(
            target_panelist_id, speaker_id, experts, "main"
        ) or target_panelist_id is None

    @staticmethod
    def validate_utterance_type(utt_type: str) -> bool:
        return UtteranceValidator.validate_type(utt_type)
