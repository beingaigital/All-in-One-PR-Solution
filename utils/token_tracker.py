"""Token 使用追踪：记录每次调用的 token 消耗。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Mapping
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class TokenUsageTracker(BaseCallbackHandler):
    """Token 使用追踪器：记录每次 LLM 调用的 token 消耗"""
    
    def __init__(self):
        """初始化追踪器"""
        super().__init__()
        self.current_step: Optional[str] = None
        self.step_token_usage: Dict[str, Dict[str, int]] = {}
        self.total_usage: Dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    
    def set_step(self, step_name: str) -> None:
        """
        设置当前步骤名称
        
        Args:
            step_name: 步骤名称
        """
        self.current_step = step_name
        if step_name not in self.step_token_usage:
            self.step_token_usage[step_name] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
    
    def _apply_usage(self, usage: Mapping[str, Any]) -> None:
        """将 usage 字典应用到累计与 step 统计中"""
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", 0) or 0)

        if total_tokens <= 0 and (prompt_tokens or completion_tokens):
            total_tokens = prompt_tokens + completion_tokens

        if total_tokens <= 0:
            return

        # 更新总使用量
        self.total_usage["prompt_tokens"] += prompt_tokens
        self.total_usage["completion_tokens"] += completion_tokens
        self.total_usage["total_tokens"] += total_tokens

        # 更新当前步骤的使用量
        if self.current_step:
            self.step_token_usage[self.current_step]["prompt_tokens"] += prompt_tokens
            self.step_token_usage[self.current_step]["completion_tokens"] += completion_tokens
            self.step_token_usage[self.current_step]["total_tokens"] += total_tokens

    def _extract_usage_from_llm_output(self, llm_output: Any) -> Optional[Mapping[str, Any]]:
        """
        从 llm_output 中提取 token usage

        兼容常见结构：
        - {"token_usage": {...}}
        - {"usage": {...}}
        """
        if not isinstance(llm_output, dict):
            return None
        usage = llm_output.get("token_usage") or llm_output.get("usage")
        return usage if isinstance(usage, dict) else None

    def _extract_usage_from_chat_result(self, response: Any) -> Optional[Mapping[str, Any]]:
        """
        从 ChatModel 的 response 中提取 token usage

        常见来源：
        - response.llm_output["token_usage"]
        - AIMessage.response_metadata["token_usage"]
        - AIMessage.usage_metadata
        """
        usage = self._extract_usage_from_llm_output(getattr(response, "llm_output", None))
        if usage:
            return usage

        generations = getattr(response, "generations", None)
        if not generations:
            return None

        # generations: List[List[ChatGeneration]]
        try:
            gen0 = generations[0][0]
        except Exception:
            return None

        msg = getattr(gen0, "message", None)
        if msg is None:
            return None

        # 新版：usage_metadata
        usage_meta = getattr(msg, "usage_metadata", None)
        if isinstance(usage_meta, dict) and usage_meta:
            # 兼容字段名不同的情况
            normalized = {
                "prompt_tokens": usage_meta.get("input_tokens") or usage_meta.get("prompt_tokens") or 0,
                "completion_tokens": usage_meta.get("output_tokens") or usage_meta.get("completion_tokens") or 0,
                "total_tokens": usage_meta.get("total_tokens") or 0,
            }
            return normalized

        # 常见：response_metadata.token_usage
        resp_meta = getattr(msg, "response_metadata", None)
        if isinstance(resp_meta, dict):
            token_usage = resp_meta.get("token_usage")
            if isinstance(token_usage, dict) and token_usage:
                return token_usage

        return None

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """
        LLM 调用结束时记录 token 使用
        
        Args:
            response: LLM 响应
            **kwargs: 其他参数
        """
        usage = self._extract_usage_from_llm_output(getattr(response, "llm_output", None))
        if usage:
            self._apply_usage(usage)
            return

        # 兜底：有些实现不会在 llm_output 中给 usage，而是在 generations 的 message metadata 中给
        generations = getattr(response, "generations", None)
        if not generations:
            return
        try:
            gen0 = generations[0][0]
        except Exception:
            return
        msg = getattr(gen0, "message", None)
        if msg is None:
            return
        usage_meta = getattr(msg, "usage_metadata", None)
        if isinstance(usage_meta, dict) and usage_meta:
            normalized = {
                "prompt_tokens": usage_meta.get("input_tokens") or usage_meta.get("prompt_tokens") or 0,
                "completion_tokens": usage_meta.get("output_tokens") or usage_meta.get("completion_tokens") or 0,
                "total_tokens": usage_meta.get("total_tokens") or 0,
            }
            self._apply_usage(normalized)
            return
        resp_meta = getattr(msg, "response_metadata", None)
        if isinstance(resp_meta, dict):
            token_usage = resp_meta.get("token_usage")
            if isinstance(token_usage, dict) and token_usage:
                self._apply_usage(token_usage)
                return

    def on_chat_model_end(self, response: Any, **kwargs: Any) -> None:
        """ChatModel 调用结束时记录 token 使用（ChatOpenAI / OpenAI-compatible 等）"""
        usage = self._extract_usage_from_chat_result(response)
        if usage:
            self._apply_usage(usage)
    
    def get_step_usage(self, step_name: str) -> Dict[str, int]:
        """
        获取指定步骤的 token 使用量
        
        Args:
            step_name: 步骤名称
            
        Returns:
            Token 使用量字典
        """
        return self.step_token_usage.get(step_name, {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        })
    
    def get_total_usage(self) -> Dict[str, int]:
        """
        获取总 token 使用量
        
        Returns:
            总 token 使用量字典
        """
        return self.total_usage.copy()
    
    def reset(self) -> None:
        """重置追踪器。"""
        self.current_step = None
        self.step_token_usage = {}
        self.total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
