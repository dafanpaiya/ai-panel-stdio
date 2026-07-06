"""
API Key 配置管理 — 持久化到本地 JSON 文件（data/config.json），不上传 git。
"""

import json
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


CONFIG_PATH = Path("C:/Users/大反派/AppData/Roaming/TRAE SOLO CN/ModularData/ai-agent/work-mode-projects/6a4b27824bf5329b06acb20a/config.json")


@dataclass
class LLMProviderConfig:
    provider: str = "deepseek"                      # deepseek | openai | anthropic | custom
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    label: str = ""                                  # 用户自定义名称


@dataclass
class AppConfig:
    providers: list[LLMProviderConfig] = field(default_factory=list)
    active_provider: str = "deepseek"                # 当前使用的 provider name

    def get_active(self) -> Optional[LLMProviderConfig]:
        for p in self.providers:
            if p.provider == self.active_provider:
                return p
        return None

    def find(self, provider: str) -> Optional[LLMProviderConfig]:
        for p in self.providers:
            if p.provider == provider:
                return p
        return None


def _default_providers() -> list[LLMProviderConfig]:
    """默认 provider 列表 — 不含 key，key 由用户填写"""
    return [
        LLMProviderConfig(
            provider="deepseek",
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            label="DeepSeek V4 Flash",
        ),
        LLMProviderConfig(
            provider="openai",
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            label="OpenAI GPT-4o",
        ),
        LLMProviderConfig(
            provider="anthropic",
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            base_url="https://api.anthropic.com/v1",
            model="claude-fable-5",
            label="Anthropic Claude",
        ),
        LLMProviderConfig(
            provider="custom",
            api_key="",
            base_url="",
            model="",
            label="自定义",
        ),
    ]


def load_config() -> AppConfig:
    """加载配置，不存在则创建默认配置"""
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            providers = [LLMProviderConfig(**p) for p in data.get("providers", [])]
            # 确保默认 provider 都存在
            existing = {p.provider for p in providers}
            for dp in _default_providers():
                if dp.provider not in existing:
                    providers.append(dp)
            return AppConfig(
                providers=providers,
                active_provider=data.get("active_provider", "deepseek"),
            )
        except Exception:
            pass

    # 默认
    return AppConfig(
        providers=_default_providers(),
        active_provider="deepseek",
    )


def save_config(config: AppConfig) -> None:
    """保存配置到文件"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "providers": [
            {k: v for k, v in p.__dict__.items()}
            for p in config.providers
        ],
        "active_provider": config.active_provider,
    }
    CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_active_api_key() -> str:
    """
    获取当前激活的 API Key。
    优先级：环境变量 DEEPSEEK_API_KEY > config 文件。
    """
    # 环境变量优先（用于服务端部署）
    env_key = os.getenv("DEEPSEEK_API_KEY", "")
    if env_key:
        return env_key

    cfg = load_config()
    active = cfg.get_active()
    if active and active.api_key:
        return active.api_key
    return ""


def update_provider_key(provider: str, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None) -> LLMProviderConfig:
    """更新指定 provider 的 API Key"""
    cfg = load_config()
    p = cfg.find(provider)
    if p is None:
        p = LLMProviderConfig(provider=provider)
        cfg.providers.append(p)

    p.api_key = api_key
    if base_url is not None:
        p.base_url = base_url
    if model is not None:
        p.model = model

    save_config(cfg)
    return p


def set_active_provider(provider: str) -> AppConfig:
    """切换当前使用的 LLM provider"""
    cfg = load_config()
    cfg.active_provider = provider
    save_config(cfg)
    return cfg
