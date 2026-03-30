"""
LLM provider with safe fallback to avoid dependency/runtime crashes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class _EchoResponse:
    content: str


class EchoLLM:
    """Fallback LLM that echoes prompt for offline/demo usage."""

    def __init__(self, *_, **__):
        pass

    def invoke(self, prompt: Any) -> _EchoResponse:
        text = prompt if isinstance(prompt, str) else getattr(prompt, "to_string", lambda: str(prompt))()
        return _EchoResponse(content=f"[offline echo]\n{text}")


_PROVIDER_CONFIG: Dict[str, Dict[str, Any]] = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "base_url": "https://api.openai.com/v1",
        "models": {"flash": "gpt-4o-mini", "thinking": "gpt-4o"},
    },
    "openai_compatible": {
        "api_key_env": "APIKEY",
        "base_url_env": "OPENAI_BASE_URL",
        "base_url": "https://api.openai.com/v1",
        "models": {"flash": "gpt-4o-mini", "thinking": "gpt-4o"},
    },
    "kimi": {
        "api_key_env": "KIMI_API_KEY",
        "base_url_env": "KIMI_BASE_URL",
        "base_url": "https://api.moonshot.cn/v1",
        "models": {"flash": "moonshot-v1-auto", "thinking": "moonshot-v1-128k"},
    },
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "base_url": "https://api.deepseek.com",
        "models": {"flash": "deepseek-chat", "thinking": "deepseek-reasoner"},
    },
    "qwen": {
        "api_key_env": "QWEN_API_KEY",
        "base_url_env": "QWEN_BASE_URL",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": {"flash": "qwen-turbo", "thinking": "qwen-plus"},
    },
    "google": {
        "api_key_env": "GOOGLE_API_KEY",
        "base_url_env": "GOOGLE_BASE_URL",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": {"flash": "gemini-1.5-flash", "thinking": "gemini-1.5-pro"},
    },
}


_PROVIDER_ALIASES: Dict[str, str] = {
    "openai_compatible": "openai_compatible",
    "openai-compatible": "openai_compatible",
    "compatible": "openai_compatible",
}


def _resolve_provider(provider: str | None) -> str:
    env_provider = os.getenv("LLM_PROVIDER")
    raw = (provider or env_provider or "openai").strip().lower()
    resolved = _PROVIDER_ALIASES.get(raw, raw)
    if resolved not in _PROVIDER_CONFIG:
        return "openai"
    return resolved


def _resolve_model(provider: str, tier: str, override_model: str | None) -> str:
    # 强制覆盖（用于 OpenAI-compatible 网关场景，把代码里写死的 gpt-* 统一映射到可用模型）
    force_model = os.getenv("LLM_FORCE_MODEL")
    if force_model:
        return force_model
    # 分档覆盖：优先于调用方显式 model，便于统一接管老代码中的硬编码模型
    tier_key = "LLM_THINKING_MODEL" if (tier or "").lower() == "thinking" else "LLM_FLASH_MODEL"
    tier_model = os.getenv(tier_key)
    if tier_model:
        return tier_model
    # env override
    env_model = os.getenv("LLM_MODEL")
    if override_model:
        return override_model
    if env_model:
        return env_model
    conf = _PROVIDER_CONFIG.get(provider, _PROVIDER_CONFIG["openai"])
    return conf["models"].get(tier, conf["models"]["flash"])


def _resolve_base_url(provider: str, default: str) -> str:
    env = _PROVIDER_CONFIG.get(provider, {}).get("base_url_env")
    if env and os.getenv(env):
        return os.getenv(env)
    return (
        os.getenv("LLM_BASE_URL")
        or os.getenv("API_BASE_URL")
        or os.getenv("BASE_URL")
        or default
    )


def _resolve_api_key(provider: str, default_env: str) -> str:
    env_key = os.getenv(default_env, "")
    if env_key:
        return env_key
    return (
        os.getenv("LLM_API_KEY", "")
        or os.getenv("APIKEY", "")
        or ""
    )


def get_chat_llm(
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 2000,
    provider: str | None = None,
    tier: str = "flash",
):
    """
    获取统一的 Chat LLM，支持 openai/kimi/deepseek/qwen/google，并按 tier（flash/thinking）选择模型。
    """
    provider_resolved = _resolve_provider(provider)
    conf = _PROVIDER_CONFIG.get(provider_resolved, _PROVIDER_CONFIG["openai"])
    chosen_model = _resolve_model(provider_resolved, tier, model)
    base_url = _resolve_base_url(provider_resolved, conf["base_url"])
    api_key = _resolve_api_key(provider_resolved, conf["api_key_env"])

    try:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=chosen_model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key or None,
            base_url=base_url,
        )
    except Exception as exc:  # pragma: no cover - fallback path
        print(f"⚠️ ChatOpenAI 初始化失败，使用离线回显模型: {exc}")
        return EchoLLM()


__all__ = ["get_chat_llm", "EchoLLM"]
