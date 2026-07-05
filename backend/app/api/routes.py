"""
FastAPI 路由 — REST API + SSE。
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.manager import DiscussionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ── 请求/响应模型 ───────────────────────────────────

class CreateDiscussionRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=200)
    expert_count: int = Field(default=4, ge=1, le=8)
    max_rounds: int = Field(default=12, ge=4, le=30)


class GeneratePanelRequest(BaseModel):
    expert_count: int = Field(default=4, ge=1, le=8)


class UpdatePanelistRequest(BaseModel):
    name: Optional[str] = None
    occupation: Optional[str] = None
    title: Optional[str] = None
    stance: Optional[str] = None
    color: Optional[str] = None


class AddExpertRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    occupation: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=100)
    stance: str = Field(..., min_length=1, max_length=200)
    color: str = Field(..., pattern=r"^#[0-9A-Fa-f]{6}$")


class InterjectRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)


# ── 依赖注入 ────────────────────────────────────────

_manager: Optional[DiscussionManager] = None


def get_manager() -> DiscussionManager:
    assert _manager is not None, "DiscussionManager 未初始化"
    return _manager


def set_manager(manager: DiscussionManager):
    global _manager
    _manager = manager


# ── 讨论管理 ────────────────────────────────────────

@router.get("/discussions")
async def list_discussions(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    mgr = get_manager()
    result = await mgr.list_discussions(status, limit, offset)
    return {"discussions": result, "total": len(result)}


@router.post("/discussions", status_code=201)
async def create_discussion(body: CreateDiscussionRequest):
    mgr = get_manager()
    d = await mgr.create_discussion(body.topic, body.expert_count, body.max_rounds)
    return {
        "id": d.id,
        "topic": d.topic,
        "status": d.status,
        "max_rounds": d.max_rounds,
        "expert_count": body.expert_count,
        "created_at": now_iso(),
    }


@router.get("/discussions/{discussion_id}")
async def get_discussion(discussion_id: str):
    mgr = get_manager()
    d = await mgr.get_discussion(discussion_id)
    if d is None:
        raise HTTPException(404, detail={"code": "DISCUSSION_NOT_FOUND", "message": "讨论不存在"})

    panel_count = mgr.db.get_panelist_count(discussion_id)
    utt_count = mgr.db.get_utterance_count(discussion_id)
    return {
        "id": d.id,
        "topic": d.topic,
        "status": d.status,
        "max_rounds": d.max_rounds,
        "current_round": d.current_round,
        "panelist_count": panel_count,
        "total_utterances": utt_count,
        "created_at": None,  # simplified
        "updated_at": None,
    }


@router.delete("/discussions/{discussion_id}")
async def delete_discussion(discussion_id: str):
    mgr = get_manager()
    d = await mgr.get_discussion(discussion_id)
    if d is None:
        raise HTTPException(404, detail={"code": "DISCUSSION_NOT_FOUND", "message": "讨论不存在"})
    if d.status != "ended":
        raise HTTPException(409, detail={"code": "INVALID_STATE", "message": "仅已结束的讨论可删除"})
    deleted = mgr.db.delete_discussion(discussion_id)
    return {"deleted": deleted}


# ── 嘉宾阵容 ────────────────────────────────────────

@router.post("/discussions/{discussion_id}/panel/generate", status_code=201)
async def generate_panel(discussion_id: str, body: GeneratePanelRequest):
    mgr = get_manager()
    d = await mgr.get_discussion(discussion_id)
    if d is None:
        raise HTTPException(404, detail={"code": "DISCUSSION_NOT_FOUND", "message": "讨论不存在"})

    panelists = await mgr.generate_panel(discussion_id, body.expert_count)
    return {
        "panel": [
            {
                "id": p.id, "role": p.role, "name": p.name,
                "occupation": p.occupation, "title": p.title,
                "stance": p.stance, "color": p.color, "sort_order": p.sort_order,
            }
            for p in panelists
        ]
    }


@router.get("/discussions/{discussion_id}/panel")
async def get_panel(discussion_id: str):
    mgr = get_manager()
    panelists = await mgr.list_panel(discussion_id)
    return {
        "panel": [
            {
                "id": p.id, "role": p.role, "name": p.name,
                "occupation": p.occupation, "title": p.title,
                "stance": p.stance, "color": p.color, "sort_order": p.sort_order,
            }
            for p in panelists
        ]
    }


@router.put("/discussions/{discussion_id}/panel/{panelist_id}")
async def update_panelist(discussion_id: str, panelist_id: str, body: UpdatePanelistRequest):
    mgr = get_manager()
    p = mgr.db.get_panelist(panelist_id)
    if p is None:
        raise HTTPException(404, detail={"code": "PANELIST_NOT_FOUND", "message": "嘉宾不存在"})

    updates = body.model_dump(exclude_none=True)
    await mgr.update_panelist(discussion_id, panelist_id, updates)

    # Re-fetch
    p = mgr.db.get_panelist(panelist_id)
    return {
        "id": p.id, "role": p.role, "name": p.name,
        "occupation": p.occupation, "title": p.title,
        "stance": p.stance, "color": p.color, "sort_order": p.sort_order,
    }


@router.delete("/discussions/{discussion_id}/panel/{panelist_id}")
async def delete_panelist(discussion_id: str, panelist_id: str):
    mgr = get_manager()
    p = mgr.db.get_panelist(panelist_id)
    if p is None:
        raise HTTPException(404, detail={"code": "PANELIST_NOT_FOUND", "message": "嘉宾不存在"})
    if p.role == "moderator":
        raise HTTPException(422, detail={"code": "CANNOT_DELETE_MODERATOR", "message": "不可删除主持人"})

    deleted = await mgr.delete_panelist(discussion_id, panelist_id)
    return {"deleted": deleted}


@router.post("/discussions/{discussion_id}/panel", status_code=201)
async def add_expert(discussion_id: str, body: AddExpertRequest):
    mgr = get_manager()
    p = await mgr.add_expert(discussion_id, body.model_dump())
    return {
        "id": p.id, "role": p.role, "name": p.name,
        "occupation": p.occupation, "title": p.title,
        "stance": p.stance, "color": p.color, "sort_order": p.sort_order,
    }


# ── 讨论控制 ────────────────────────────────────────

@router.post("/discussions/{discussion_id}/start", status_code=202)
async def start_discussion(discussion_id: str):
    mgr = get_manager()
    d = await mgr.get_discussion(discussion_id)
    if d is None:
        raise HTTPException(404, detail={"code": "DISCUSSION_NOT_FOUND", "message": "讨论不存在"})
    if d.status not in ("lineup_ready", "draft"):
        raise HTTPException(409, detail={"code": "INVALID_STATE", "message": "当前状态不允许开始讨论"})

    try:
        await mgr.start_discussion(discussion_id)
        return {"status": "running", "started_at": now_iso()}
    except ValueError as e:
        raise HTTPException(422, detail={"code": "PANEL_NOT_READY", "message": str(e)})


@router.post("/discussions/{discussion_id}/pause")
async def pause_discussion(discussion_id: str):
    mgr = get_manager()
    await mgr.pause_discussion(discussion_id)
    return {"status": "paused"}


@router.post("/discussions/{discussion_id}/resume")
async def resume_discussion(discussion_id: str):
    mgr = get_manager()
    await mgr.resume_discussion(discussion_id)
    return {"status": "running"}


@router.post("/discussions/{discussion_id}/interject", status_code=202)
async def interject(discussion_id: str, body: InterjectRequest):
    mgr = get_manager()
    await mgr.interject(discussion_id, body.message)
    return {"accepted": True, "message": "追问已提交，主持人将在下一轮中引导讨论"}


@router.post("/discussions/{discussion_id}/end", status_code=202)
async def end_discussion(discussion_id: str):
    mgr = get_manager()
    await mgr.stop_discussion(discussion_id)
    return {"status": "ending", "message": "主持人正在进行收尾总结…"}


# ── SSE ─────────────────────────────────────────────

@router.get("/discussions/{discussion_id}/stream")
async def stream_discussion(discussion_id: str, request: Request):
    mgr = get_manager()

    async def event_generator():
        try:
            async for sse_text in mgr.sse_stream(discussion_id):
                # 客户端断开连接时停止
                if await request.is_disconnected():
                    break
                yield sse_text
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 查询 ────────────────────────────────────────────

@router.get("/discussions/{discussion_id}/transcript")
async def get_transcript(
    discussion_id: str,
    limit: int = 100,
    offset: int = 0,
    after_seq: int = 0,
):
    mgr = get_manager()
    return await mgr.get_transcript(discussion_id, after_seq, limit)


@router.get("/discussions/{discussion_id}/insights")
async def get_insights(discussion_id: str):
    mgr = get_manager()
    return await mgr.get_insights(discussion_id)
