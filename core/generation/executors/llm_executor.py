"""
通用 LLM 执行器。
"""

from __future__ import annotations

from typing import Optional

from core.common.llm_provider import get_chat_llm


class LLMExecutor:
    """封装 ChatOpenAI 调用，便于统一配置与替换。"""

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-3.5-turbo",
        max_tokens: int = 2048,
        temperature: float = 0.6,
    ) -> None:
        self.provider = provider
        self.model = model or "gpt-3.5-turbo"
        self.max_tokens = max_tokens
        self.temperature = temperature

    def complete(self, prompt: str) -> str:
        """执行一次补全。"""
        try:
            llm = get_chat_llm(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                provider=self.provider,
                tier="flash",
            )
            response = llm.invoke(prompt)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:  # pragma: no cover - 依赖外部服务
            return f"生成失败: {exc}"


def llm_complete(
    provider: str,
    model: str,
    prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.6,
) -> str:
    """保持对旧接口的兼容。"""
    executor = LLMExecutor(
        provider=provider,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return executor.complete(prompt)
