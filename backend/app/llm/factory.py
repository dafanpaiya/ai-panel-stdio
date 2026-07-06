"""
LLM 客户端工厂 — 从配置读取活跃 provider 并创建客户端。
"""

import logging
from app.core.config import load_config, get_active_api_key
from app.llm.client import LLMClient, MockLLMClient, DeepSeekClient

logger = logging.getLogger(__name__)


def create_llm_client_from_config(mock: bool = False) -> LLMClient:
    """根据 config.json 中的活跃 provider 创建 LLM 客户端"""

    if mock:
        return MockLLMClient()

    cfg = load_config()
    active = cfg.get_active()

    if active is None or not active.api_key:
        logger.warning("未配置 API Key，使用 Mock 模式运行")
        return MockLLMClient()

    # 对所有 provider 使用 OpenAI 兼容协议（DeepSeek / OpenAI / 自定义 endpoint 均兼容）
    from app.llm.client import DeepSeekClient
    return DeepSeekClient(
        api_key=active.api_key,
        base_url=active.base_url,
        model=active.model,
    )


def reload_llm_client(mock: bool = False) -> LLMClient:
    """强制重新加载配置并创建新的 LLM 客户端（用于 API Key 更新后）"""
    return create_llm_client_from_config(mock=mock)
