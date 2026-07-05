"""
LLM 客户端 — DeepSeek V4 Flash 适配层。

支持：
- 真实 API 调用
- 测试模式的 mock 返回
- 统一的异常处理
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

from app.core.models import (
    Panelist,
    PanelistRole,
    Utterance,
    SchedulerResult,
    SpeakerResult,
    InsightResult,
    Consensus,
    Divergence,
    ModeratorTrigger,
    SpeakingStats,
    new_id,
    now_iso,
)

logger = logging.getLogger(__name__)

# ── 抽象接口 ────────────────────────────────────────

class LLMClient(ABC):
    """LLM 客户端抽象接口"""

    @abstractmethod
    async def schedule_next_speaker(
        self,
        topic: str,
        experts: list[Panelist],
        stats: list[SpeakingStats],
        transcript: list[Utterance],
    ) -> Optional[SchedulerResult]:
        """两步管道第一步：调度"""
        ...

    @abstractmethod
    async def generate_expert_speech(
        self,
        panelist: Panelist,
        topic: str,
        transcript: list[Utterance],
        speech_type: str,
        target_panelist_id: Optional[str] = None,
    ) -> str:
        """两步管道第二步：生成专家发言"""
        ...

    @abstractmethod
    async def generate_opening(
        self,
        topic: str,
        moderator: Panelist,
        experts: list[Panelist],
    ) -> str:
        """生成主持人开场白"""
        ...

    @abstractmethod
    async def generate_moderator_interjection(
        self,
        topic: str,
        moderator: Panelist,
        transcript: list[Utterance],
        trigger: ModeratorTrigger,
        user_message: Optional[str] = None,
    ) -> str:
        """生成主持人介入发言"""
        ...

    @abstractmethod
    async def generate_closing(
        self,
        topic: str,
        moderator: Panelist,
        transcript: list[Utterance],
        consensus_list: list,
        divergence_list: list,
    ) -> str:
        """生成主持人收尾总结"""
        ...

    @abstractmethod
    async def extract_insights(
        self,
        utterance: Utterance,
        topic: str,
        transcript: list[Utterance],
        existing_consensus: list,
        existing_divergence: list,
    ) -> InsightResult:
        """从最新发言中增量提取共识/分歧"""
        ...


# ── Mock 实现（测试用）────────────────────────────────

class MockLLMClient(LLMClient):
    """
    Mock LLM 客户端 — 返回固定值，用于测试。
    所有方法不依赖真实 API。
    """

    def __init__(self):
        self._schedule_index = 0

    async def schedule_next_speaker(
        self, topic, experts, stats, transcript,
    ) -> Optional[SchedulerResult]:
        """按固定顺序循环选择专家"""
        # 使用一个简单的轮转
        expert = experts[self._schedule_index % len(experts)]
        types = ["main", "supplement", "rebuttal"]
        utt_type = types[self._schedule_index % len(types)]
        self._schedule_index += 1

        target = None
        if utt_type in ("supplement", "rebuttal"):
            # 选一个不是自己的专家作为 target
            for e in experts:
                if e.id != expert.id:
                    target = e.id
                    break

        return SchedulerResult(
            selected_panelist_id=expert.id,
            type=utt_type,
            reason=f"Mock 调度：选择 {expert.name}",
            target_panelist_id=target,
        )

    async def generate_expert_speech(
        self, panelist, topic, transcript, speech_type, target_panelist_id=None,
    ) -> str:
        """返回模拟发言"""
        speeches = {
            "main": f"从我的角度看，" + topic + "这个问题确实值得深入探讨。我认为关键在于平衡创新与风险。",
            "supplement": "我想补充一点——前面的分析很有启发性，但我们还需要考虑实施路径的问题。",
            "rebuttal": "我对此有不同看法。过于激进的推进可能带来不可预知的后果，我们应该谨慎行事。",
        }
        return speeches.get(speech_type, f"关于{topic}，我有一些想法。")

    async def generate_opening(self, topic, moderator, experts) -> str:
        names = "、".join(e.name for e in experts)
        return f"大家好，欢迎来到《前沿对话》。我是主持人{moderator.name}。今天我们讨论的话题是：{topic}。今天我们荣幸地邀请到了{names}四位专家。让我们先请各位嘉宾亮明自己的核心立场。"

    async def generate_moderator_interjection(
        self, topic, moderator, transcript, trigger, user_message=None,
    ) -> str:
        if trigger == ModeratorTrigger.ROUND_INTERVAL:
            return f"感谢各位的精彩发言。刚才的讨论触及了一些非常核心的问题，我想请下一位专家继续展开。"
        elif trigger == ModeratorTrigger.USER_INTERJECTION and user_message:
            return f"感谢观众的提问。问题是关于：{user_message}。各位专家，让我们从这个角度继续讨论。"
        elif trigger == ModeratorTrigger.SILENCE:
            return "看来大家都在深入思考。我想请一位尚未充分发言的专家分享您的看法。"
        elif trigger == ModeratorTrigger.OFF_TOPIC:
            return "让我们把讨论拉回正题——我们今天的核心问题是" + topic + "。"
        return "让我们继续讨论。"

    async def generate_closing(
        self, topic, moderator, transcript, consensus_list, divergence_list,
    ) -> str:
        return (
            f"感谢各位专家的精彩讨论。今天关于{topic}，我们达成了以下共识："
            + "；".join(c.content for c in consensus_list[:2])
            + "。同时也在以下方面存在分歧："
            + "；".join(d.content for d in divergence_list[:2])
            + "。感谢各位观众，我们下期再见。"
        )

    async def extract_insights(
        self, utterance, topic, transcript, existing_consensus, existing_divergence,
    ) -> InsightResult:
        """Mock：每隔一条发言生成一条共识或分歧"""
        total_utts = len([u for u in transcript if u.type not in ("opening", "closing")])
        result = InsightResult()

        if total_utts % 3 == 0 and len(existing_consensus) < 5:
            result.consensus_updates.append(Consensus(
                id=new_id(),
                discussion_id=utterance.discussion_id,
                content=f"专家们就{topic}的某个方面达成初步共识",
                source_utterance_ids=[utterance.id],
            ))
        if total_utts % 4 == 0 and len(existing_divergence) < 5:
            result.divergence_updates.append(Divergence(
                id=new_id(),
                discussion_id=utterance.discussion_id,
                content=f"在{topic}的实施路径上仍有不同观点",
                opposing_sides=[
                    {"side": "渐进式推进", "panelist_ids": []},
                    {"side": "激进改革", "panelist_ids": []},
                ],
                source_utterance_ids=[utterance.id],
            ))

        return result


# ── DeepSeek 实现 ────────────────────────────────────

class DeepSeekClient(LLMClient):
    """
    DeepSeek V4 Flash 客户端（OpenAI 兼容协议）。
    API Key 从环境变量 DEEPSEEK_API_KEY 读取。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
        model: str = "deepseek-chat",
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def _chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> str:
        """底层 HTTP 调用"""
        import httpx

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict:
        """调用 LLM 并解析 JSON 返回"""
        import re
        raw = await self._chat(system_prompt, user_prompt, temperature)

        # 尝试提取 JSON 块
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        raise ValueError(f"LLM 返回无法解析为 JSON: {raw[:200]}")

    # ── 调度 ──────────────────────────────────────────

    async def schedule_next_speaker(
        self, topic, experts, stats, transcript,
    ) -> Optional[SchedulerResult]:
        """调用 LLM 决定下一位发言专家"""
        # 构造 prompt
        expert_lines = []
        for e, s in zip(experts, stats):
            if len(stats) == len(experts):
                stat = [x for x in stats if x.panelist_id == e.id][0] if any(
                    x.panelist_id == e.id for x in stats
                ) else SpeakingStats(panelist_id=e.id)
            else:
                stat = next((x for x in stats if x.panelist_id == e.id), SpeakingStats(panelist_id=e.id))

            expert_lines.append(
                f"- {e.name}（{e.stance}）| 已发言 {stat.total_utterances} 次 | "
                f"连续 {stat.consecutive_utterances} 次 | 最近第 {stat.last_spoke_round} 轮"
            )

        recent = transcript[-6:] if len(transcript) > 6 else transcript
        recent_lines = [
            f"[R{u.round}] {self._speaker_name(u, experts)}: {u.content[:80]}…"
            for u in recent
        ]

        system_prompt = (
            "你是一个圆桌讨论的调度员。根据当前讨论进展和专家发言统计，"
            "决定下一位发言专家及发言类型。\n\n"
            "约束规则：\n"
            "1. 同一专家连续发言不超过 2 次\n"
            "2. 优先选择最近未发言的专家\n"
            "3. 禁止机械式轮流发言\n"
            "4. 发言类型：main（新观点）、supplement（补充）、rebuttal（反驳）\n"
            "5. rebuttal/supplement 必须指定 target_panelist_id\n\n"
            '返回 JSON: {"selected_panelist_id": "...", "type": "main|supplement|rebuttal", '
            '"target_panelist_id": "..." | null, "reason": "选择理由"}'
        )

        user_prompt = (
            f"话题：{topic}\n\n"
            f"专家统计：\n" + "\n".join(expert_lines) + "\n\n"
            f"最近发言：\n" + "\n".join(recent_lines)
        )

        try:
            result = await self._chat_json(system_prompt, user_prompt)
            return SchedulerResult(
                selected_panelist_id=result["selected_panelist_id"],
                type=result.get("type", "main"),
                reason=result.get("reason", ""),
                target_panelist_id=result.get("target_panelist_id"),
            )
        except Exception as e:
            logger.warning(f"调度 LLM 调用失败，fallback 到候选排序: {e}")
            return None  # 调用方会 fallback 到 Scheduler.pick_next

    # ── 专家发言生成 ──────────────────────────────────

    async def generate_expert_speech(
        self, panelist, topic, transcript, speech_type, target_panelist_id=None,
    ) -> str:
        recent = transcript[-8:] if len(transcript) > 8 else transcript
        recent_lines = "\n".join(
            f"[R{u.round}] {u.type}: {u.content}" for u in recent
        )

        system_prompt = (
            f"你是 {panelist.name}，{panelist.occupation}，{panelist.title}。\n"
            f"你的立场：{panelist.stance}\n\n"
            f"你正在参加一场关于「{topic}」的圆桌讨论。\n"
            f"本轮你的发言类型是：{speech_type}。\n"
            f"请用自然语言发表 1-2 句话，表达你的观点。\n"
            f"要求：简洁有力，口语化，像真实讨论中的发言。"
        )

        user_prompt = f"最近讨论记录：\n{recent_lines}\n\n请发表你的观点："

        return await self._chat(system_prompt, user_prompt, temperature=0.8)

    # ── 主持人发言 ────────────────────────────────────

    async def generate_opening(self, topic, moderator, experts) -> str:
        expert_intros = "\n".join(
            f"- {e.name}，{e.occupation}，{e.title}，立场：{e.stance}"
            for e in experts
        )
        system_prompt = (
            f"你是 {moderator.name}，{moderator.occupation}，{moderator.title}。\n"
            f"主持风格：{moderator.stance}\n"
            f"请为一场关于「{topic}」的圆桌讨论做开场白。介绍话题背景、引入嘉宾、宣布讨论开始。"
        )
        user_prompt = f"嘉宾名单：\n{expert_intros}"
        return await self._chat(system_prompt, user_prompt, temperature=0.8)

    async def generate_moderator_interjection(
        self, topic, moderator, transcript, trigger, user_message=None,
    ) -> str:
        trigger_descriptions = {
            ModeratorTrigger.ROUND_INTERVAL: "已进行多轮讨论，需要串联总结并引出下一个话题方向",
            ModeratorTrigger.SILENCE: "讨论出现了冷场，需要追问引导",
            ModeratorTrigger.OFF_TOPIC: "讨论偏离了核心话题，需要纠正方向",
            ModeratorTrigger.USER_INTERJECTION: f"观众提出了一个问题：「{user_message}」，请转述并引导专家讨论",
            ModeratorTrigger.CLOSING: "进入收尾阶段",
        }

        system_prompt = (
            f"你是 {moderator.name}，{moderator.occupation}。\n"
            f"当前需要你介入讨论：{trigger_descriptions.get(trigger, '串联讨论')}\n"
            f"请用自然的主持语言发表 1-3 句话。"
        )
        recent = transcript[-4:] if len(transcript) > 4 else transcript
        recent_lines = "\n".join(f"[R{u.round}]: {u.content[:100]}" for u in recent)

        return await self._chat(system_prompt, f"最近发言：\n{recent_lines}", temperature=0.8)

    async def generate_closing(
        self, topic, moderator, transcript, consensus_list, divergence_list,
    ) -> str:
        cons_lines = "\n".join(f"- 共识：{c.content}" for c in consensus_list)
        div_lines = "\n".join(f"- 分歧：{d.content}" for d in divergence_list)

        system_prompt = (
            f"你是 {moderator.name}。讨论「{topic}」已接近尾声。\n"
            f"请做自然语言总结，涵盖：核心观点回顾、已达成共识、主要分歧、感谢嘉宾。\n"
            f"禁止输出 JSON，只输出自然语言段落。"
        )
        user_prompt = f"共识列表：\n{cons_lines}\n\n分歧列表：\n{div_lines}"

        return await self._chat(system_prompt, user_prompt, temperature=0.7)

    # ── 共识/分歧提取 ─────────────────────────────────

    async def extract_insights(
        self, utterance, topic, transcript, existing_consensus, existing_divergence,
    ) -> InsightResult:
        existing_cons_lines = "\n".join(f"- {c.content}" for c in existing_consensus)
        existing_div_lines = "\n".join(f"- {d.content}" for d in existing_divergence)

        system_prompt = (
            "你是一个讨论分析助手。根据最新一条发言，判断是否引入了新的共识或分歧。\n"
            "已有共识：\n" + existing_cons_lines + "\n\n"
            "已有分歧：\n" + existing_div_lines + "\n\n"
            "如果新发言不引入新共识/分歧，返回空数组。\n"
            '返回 JSON: {"new_consensus": [], "new_divergences": []}'
        )
        user_prompt = f"最新发言：{utterance.content}"

        try:
            result = await self._chat_json(system_prompt, user_prompt)
            insight_result = InsightResult()

            for c_data in result.get("new_consensus", []):
                insight_result.consensus_updates.append(Consensus(
                    id=new_id(),
                    discussion_id=utterance.discussion_id,
                    content=c_data["content"],
                    source_utterance_ids=[utterance.id],
                ))

            for d_data in result.get("new_divergences", []):
                insight_result.divergence_updates.append(Divergence(
                    id=new_id(),
                    discussion_id=utterance.discussion_id,
                    content=d_data["content"],
                    opposing_sides=d_data.get("opposing_sides", []),
                    source_utterance_ids=[utterance.id],
                ))

            return insight_result
        except Exception as e:
            logger.warning(f"共识/分歧提取失败: {e}")
            return InsightResult()

    # ── 工具 ──────────────────────────────────────────

    def _speaker_name(self, u: Utterance, experts: list[Panelist]) -> str:
        for e in experts:
            if e.id == u.panelist_id:
                return e.name
        return "主持人"


# ── 工厂 ────────────────────────────────────────────

def create_llm_client(mock: bool = False) -> LLMClient:
    """创建 LLM 客户端实例"""
    if mock:
        return MockLLMClient()

    from app.core.models import PanelistRole
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY 未设置，fallback 到 MockLLMClient")
        return MockLLMClient()

    return DeepSeekClient(api_key=api_key)
