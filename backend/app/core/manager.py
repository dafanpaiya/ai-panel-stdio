"""
讨论管理器 — 管理多个并行 DiscussionEngine 实例。
多讨论完全隔离：独立的 engine、task、SSE 队列。
"""

import asyncio
import logging
from typing import Optional, AsyncIterator

from app.core.models import (
    Discussion, DiscussionStatus,
    Panelist, PanelistRole,
    SchedulerResult,
    SSEEvent,
    new_id, now_iso,
)
from app.core.engine import DiscussionEngine
from app.llm.client import LLMClient, create_llm_client
from app.db.database import Database

logger = logging.getLogger(__name__)


class DiscussionManager:
    """多讨论并行管理器"""

    def __init__(self, db: Database):
        self.db = db
        self.llm: LLMClient = create_llm_client()
        self._engines: dict[str, DiscussionEngine] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._summaries: dict[str, str] = {}

    # ── 创建讨论 ──────────────────────────────────────

    async def create_discussion(self, topic: str, expert_count: int, max_rounds: int) -> Discussion:
        return self.db.create_discussion(topic, expert_count, max_rounds)

    async def get_discussion(self, discussion_id: str) -> Optional[Discussion]:
        return self.db.get_discussion(discussion_id)

    async def list_discussions(self, status: Optional[str] = None, limit: int = 20, offset: int = 0):
        discussions = self.db.list_discussions(status, limit, offset)
        result = []
        for d in discussions:
            panelist_count = self.db.get_panelist_count(d.id)
            utterance_count = self.db.get_utterance_count(d.id)
            result.append({
                "id": d.id,
                "topic": d.topic,
                "status": d.status,
                "max_rounds": d.max_rounds,
                "current_round": d.current_round,
                "panelist_count": panelist_count,
                "utterance_count": utterance_count,
            })
        return result

    # ── 嘉宾阵容 ──────────────────────────────────────

    async def generate_panel(
        self, discussion_id: str, expert_count: int, llm_client: Optional[LLMClient] = None,
    ) -> list[Panelist]:
        """调用 LLM 生成主持人和专家阵容"""
        llm = llm_client or self.llm
        discussion = self.db.get_discussion(discussion_id)
        if not discussion:
            raise ValueError("讨论不存在")

        # 清除已有专家（保留主持人）
        self.db.clear_panelists(discussion_id)

        # 使用 mock 或真实 LLM 生成
        panel_data = await self._llm_generate_panel(llm, discussion.topic, expert_count)

        # 写入数据库
        panelists = []
        for i, data in enumerate(panel_data):
            p = Panelist(
                id=new_id(),
                discussion_id=discussion_id,
                role=PanelistRole(data.get("role", "expert")),
                name=data["name"],
                occupation=data["occupation"],
                title=data["title"],
                stance=data["stance"],
                color=data["color"],
                sort_order=i,
            )
            self.db.create_panelist(p)
            panelists.append(p)

        return panelists

    async def _llm_generate_panel(self, llm: LLMClient, topic: str, count: int) -> list[dict]:
        """LLM 生成阵容（DeepSeek）或 mock 返回"""
        from app.llm.client import MockLLMClient

        if isinstance(llm, MockLLMClient):
            return self._mock_panel_data(count)

        system_prompt = (
            f"为话题「{topic}」生成圆桌讨论阵容。返回 JSON 数组。\n"
            f"第一位是主持人（role: moderator），后续 {count} 位是专家（role: expert）。\n"
            f"每位包含：name, occupation, title, stance, color（hex 颜色）。\n"
            f"专家应覆盖不同立场，形成辩论张力。"
        )
        # 简化：使用 mock 返回
        return self._mock_panel_data(count)

    def _mock_panel_data(self, count: int) -> list[dict]:
        """固定 mock 嘉宾数据"""
        colors = ["#E57373", "#81C784", "#FFB74D", "#BA68C8", "#4FC3F7", "#FF8A65", "#AED581", "#7986CB"]
        mock_experts = [
            {"name": "林芳", "occupation": "法学教授", "title": "北京大学法学院", "stance": "倾向于支持 AI 有限法律人格", "color": colors[0]},
            {"name": "李国栋", "occupation": "经济学家", "title": "社科院经济研究所", "stance": "质疑 AI 法律人格的经济基础", "color": colors[2]},
            {"name": "王雪", "occupation": "科技政策研究员", "title": "中国科学院", "stance": "关注监管框架的可行路径", "color": colors[1]},
            {"name": "周明哲", "occupation": "AI 伦理学家", "title": "某科技公司伦理委员会", "stance": "强调人类福祉为讨论出发点", "color": colors[3]},
            {"name": "赵远", "occupation": "技术创业者", "title": "某 AI 初创公司 CEO", "stance": "支持技术创新，反对过度监管", "color": colors[4]},
            {"name": "孙丽", "occupation": "社会学家", "title": "复旦大学社会发展中心", "stance": "关注 AI 对社会结构的长期影响", "color": colors[5]},
            {"name": "钱浩", "occupation": "知识产权律师", "title": "某知名律所合伙人", "stance": "关注 AI 创作物的版权归属", "color": colors[6]},
            {"name": "吴敏", "occupation": "数据隐私专家", "title": "前 GDPR 合规顾问", "stance": "优先保障数据隐私与个人权利", "color": colors[7]},
        ]
        result = [{
            "role": "moderator",
            "name": "陈锐",
            "occupation": "资深媒体人",
            "title": "《前沿对话》主持人",
            "stance": "中立，擅长引导多视角辩论",
            "color": "#4A90D9",
        }]
        result.extend(mock_experts[:count])
        return result

    async def list_panel(self, discussion_id: str) -> list[Panelist]:
        return self.db.list_panelists(discussion_id)

    async def update_panelist(self, discussion_id: str, panelist_id: str, updates: dict):
        self.db.update_panelist(panelist_id, updates)

    async def delete_panelist(self, discussion_id: str, panelist_id: str) -> bool:
        return self.db.delete_panelist(panelist_id)

    async def add_expert(self, discussion_id: str, data: dict) -> Panelist:
        existing = self.db.list_panelists(discussion_id)
        max_order = max((p.sort_order for p in existing), default=0)

        p = Panelist(
            id=new_id(),
            discussion_id=discussion_id,
            role=PanelistRole.EXPERT,
            name=data["name"],
            occupation=data["occupation"],
            title=data["title"],
            stance=data["stance"],
            color=data["color"],
            sort_order=max_order + 1,
        )
        self.db.create_panelist(p)
        return p

    # ── 讨论控制 ──────────────────────────────────────

    async def start_discussion(self, discussion_id: str):
        """启动讨论引擎"""
        discussion = self.db.get_discussion(discussion_id)
        if not discussion or not discussion.can_start():
            raise ValueError("讨论无法启动：状态不正确或阵容未就绪")

        panelists = self.db.list_panelists(discussion_id)
        if len(panelists) < 2:
            raise ValueError("至少需要 1 名主持人和 1 名专家")

        engine = DiscussionEngine(discussion, panelists, self.llm, self.db)
        self._engines[discussion_id] = engine

        # 后台异步运行
        task = asyncio.create_task(self._run_engine(discussion_id, engine))
        self._tasks[discussion_id] = task

        return engine

    async def _run_engine(self, discussion_id: str, engine: DiscussionEngine):
        try:
            summary = await engine.run()
            self._summaries[discussion_id] = summary
        except Exception as e:
            logger.exception(f"讨论 {discussion_id} 运行异常: {e}")
        finally:
            self.db.update_discussion(engine.discussion)

    async def pause_discussion(self, discussion_id: str):
        engine = self._engines.get(discussion_id)
        if engine:
            await engine.pause()
            self.db.update_discussion(engine.discussion)

    async def resume_discussion(self, discussion_id: str):
        engine = self._engines.get(discussion_id)
        if engine:
            await engine.resume()
            self.db.update_discussion(engine.discussion)

    async def interject(self, discussion_id: str, message: str):
        engine = self._engines.get(discussion_id)
        if engine:
            await engine.interject(message)

    async def stop_discussion(self, discussion_id: str):
        engine = self._engines.get(discussion_id)
        if engine:
            await engine.stop()

    # ── SSE ───────────────────────────────────────────

    async def sse_stream(self, discussion_id: str) -> AsyncIterator[str]:
        """SSE 事件流生成器"""
        engine = self._engines.get(discussion_id)
        if engine is None:
            # 讨论不在运行中 — 发送一个心跳后返回
            yield SSEEvent("heartbeat", {"message": "讨论未在运行"}).to_sse()
            return

        queue = engine.sse_queue
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    yield SSEEvent("heartbeat", {"timestamp": now_iso()}).to_sse()
                    # 检查讨论是否已结束
                    if engine.discussion.status == DiscussionStatus.ENDED:
                        break
        except asyncio.CancelledError:
            pass

    # ── 查询 ──────────────────────────────────────────

    async def get_transcript(self, discussion_id: str, after_seq: int = 0, limit: int = 100):
        utterances = self.db.list_utterances(discussion_id, after_seq, limit)
        total = self.db.get_utterance_count(discussion_id)
        result = []
        for u in utterances:
            panelist = self.db.get_panelist(u.panelist_id)
            result.append({
                "id": u.id, "seq": u.seq, "round": u.round,
                "panelist": {
                    "id": panelist.id, "name": panelist.name,
                    "occupation": panelist.occupation, "title": panelist.title,
                    "color": panelist.color, "role": panelist.role,
                } if panelist else {"id": u.panelist_id},
                "type": u.type, "content": u.content, "created_at": u.created_at,
            })
        return {"items": result, "total": total}

    async def get_insights(self, discussion_id: str):
        consensus_list = self.db.list_consensus(discussion_id)
        divergence_list = self.db.list_divergences(discussion_id)
        return {
            "consensus": [{"id": c.id, "content": c.content, "version": c.version,
                           "source_utterance_ids": c.source_utterance_ids} for c in consensus_list],
            "divergence": [{"id": d.id, "content": d.content, "version": d.version,
                            "opposing_sides": d.opposing_sides,
                            "source_utterance_ids": d.source_utterance_ids} for d in divergence_list],
        }
