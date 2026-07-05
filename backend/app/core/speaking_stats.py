"""
发言统计计算器 — 从 transcript 中计算每位专家的发言统计。
使用 dispatch 中的 FrequencyController 共享常量。
"""

from app.core.models import SpeakingStats, Utterance, Panelist
from app.core.dispatch import FrequencyController


class SpeakingStatsCalculator:
    """根据 transcript 历史计算各专家的 SpeakingStats"""

    MAX_CONSECUTIVE = FrequencyController.MAX_CONSECUTIVE

    @staticmethod
    def calculate(
        experts: list[Panelist],
        transcript: list[Utterance],
    ) -> list[SpeakingStats]:
        """计算所有专家的发言统计"""
        result: list[SpeakingStats] = []

        for expert in experts:
            total = sum(1 for u in transcript if u.panelist_id == expert.id)

            # 最后一次发言的轮次
            last_round = 0
            for u in transcript:
                if u.panelist_id == expert.id:
                    last_round = max(last_round, u.round)

            consecutive = SpeakingStatsCalculator._count_consecutive(
                expert.id, transcript
            )

            result.append(SpeakingStats(
                panelist_id=expert.id,
                total_utterances=total,
                consecutive_utterances=consecutive,
                last_spoke_round=last_round,
            ))

        return result

    @staticmethod
    def _count_consecutive(panelist_id: str, transcript: list[Utterance]) -> int:
        """从 transcript 末尾倒序，连续由同一专家发言的条数"""
        expert_utts = [
            u for u in transcript
            if u.type not in ("opening", "moderator_interjection", "closing")
        ]
        expert_utts.sort(key=lambda u: u.seq, reverse=True)

        count = 0
        for u in expert_utts:
            if u.panelist_id == panelist_id:
                count += 1
            else:
                break
        return count
