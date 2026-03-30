"""模型工厂：用于实例化 LLM"""

from __future__ import annotations

import os
import yaml
from typing import Any, Callable, Dict, Optional
from langchain_openai import ChatOpenAI
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover
    ChatGoogleGenerativeAI = None

from utils.env_loader import get_env_config
from utils.path import get_config_path

# 按 provider 使用的默认环境变量名
_DEFAULT_API_KEY_ENV_BY_PROVIDER: Dict[str, str] = {
    "openai": "OPENAI_APIKEY",
    "openai_compatible": "APIKEY",
    "gemini": "GEMINI_APIKEY",
    "qwen": "QWEN_APIKEY",
    "dashscope": "DASHSCOPE_APIKEY",
    "deepseek": "DEEPSEEK_APIKEY",
    "kimi": "KIMI_APIKEY",
}

_PROVIDER_ALIASES: Dict[str, str] = {
    "openai-compatible": "openai_compatible",
    "openai_compat": "openai_compatible",
    "openai_compatible": "openai_compatible",
    "compatible": "openai_compatible",
}


def _normalize_provider(provider: str) -> str:
    val = provider.strip().lower()
    return _PROVIDER_ALIASES.get(val, val)

# 加载模型配置
def _load_model_config() -> Dict[str, Any]:
    """从 config/model.yaml 加载配置"""
    config_path = get_config_path("model.yaml")
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

# 获取对应profile的模型
def _get_profile_config(profile: str) -> Dict[str, Any]:
    """按 profile 取对应模型配置块"""
    full = _load_model_config()
    block = full.get(profile) if isinstance(full.get(profile), dict) else None
    # 兼容旧版：无 main 但有顶层 provider 时，整份当作 main
    if block is None and profile == "main" and full.get("provider"):
        return full
    if block is None:
        raise ValueError(
            f"config/model.yaml 中缺少 profile '{profile}' 的配置（需为 main / text_generation / element_extraction / code_generation 等）"
        )
    return block

# 从配置与覆盖参数解析 provider、model、api_key_env，并取回 api_key
def _resolve_provider_model_api_key(
    config: Dict[str, Any],
    env: Any,
    provider_override: Optional[str],
    model_override: Optional[str],
) -> tuple[str, str, str]:
    """从配置与覆盖参数解析 provider、model、api_key_env，并取回 api_key"""
    provider_raw = provider_override or config.get("provider")
    model_raw = model_override or config.get("model")
    if not provider_raw or not str(provider_raw).strip():
        raise ValueError("请在 config/model.yaml 中配置 provider")
    if not model_raw or not str(model_raw).strip():
        raise ValueError("请在 config/model.yaml 中配置 model")

    provider_val = _normalize_provider(str(provider_raw))
    model_val = str(model_raw).strip()

    api_key_env = (config.get("api_key_env") or "").strip()
    if not api_key_env:
        api_key_env = _DEFAULT_API_KEY_ENV_BY_PROVIDER.get(
            provider_val,
            f"{provider_val.upper()}_APIKEY",
        )
    api_key = env.get_api_key(api_key_env)
    if not api_key:
        # 提供更详细的错误信息，帮助用户排查问题
        available_keys = []
        for key in [
            "OPENAI_APIKEY",
            "OPENAI_API_KEY",
            "GEMINI_APIKEY",
            "GEMINI_API_KEY",
            "QWEN_APIKEY",
            "QWEN_API_KEY",
            "DASHSCOPE_APIKEY",
            "DASHSCOPE_API_KEY",
            "DEEPSEEK_APIKEY",
            "DEEPSEEK_API_KEY",
            "KIMI_APIKEY",
            "KIMI_API_KEY",
        ]:
            if env.get_api_key(key):
                available_keys.append(key)
        error_msg = f"缺少 {api_key_env}，请在 .env 中配置"
        if available_keys:
            error_msg += f"\n提示：检测到已配置的环境变量: {', '.join(available_keys)}"
        raise ValueError(error_msg)

    return provider_val, model_val, api_key

# 创建 OpenAI 兼容接口的 ChatModel（DeepSeek、qwen以及kimi等）
def _create_openai_compatible(
    *,
    model: str,
    api_key: str,
    base_url: str,
    **kwargs: Any,
) -> Any:
    """
    创建 OpenAI 兼容接口的 ChatModel（DeepSeek、qwen以及kimi等）

    说明：
    - 使用 langchain_openai.ChatOpenAI
    - 通过 base_url 指向第三方 OpenAI-compatible endpoint
    """
    # 流式场景下默认请求返回 usage（通过 model_kwargs 注入，避免触发「非默认参数」warning）
    model_kwargs = kwargs.get("model_kwargs") if isinstance(kwargs.get("model_kwargs"), dict) else {}
    if "stream_options" not in model_kwargs and "stream_options" not in kwargs:
        model_kwargs["stream_options"] = {"include_usage": True}
    kwargs["model_kwargs"] = model_kwargs
    # OpenAI 接口要求 stream_options 与 stream 同时显式开启
    kwargs.setdefault("streaming", True)
    try:
        return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, **kwargs)
    except TypeError:
        # 兼容旧参数名
        if "model_kwargs" in kwargs and isinstance(kwargs["model_kwargs"], dict):
            kwargs["model_kwargs"].pop("stream_options", None)
        return ChatOpenAI(model=model, openai_api_key=api_key, base_url=base_url, **kwargs)

# 创建openai模型接口
def _create_openai(model: str, api_key: str, **kwargs: Any) -> Any:
    # 兼容 OpenAI-compatible 场景：若配置了 base_url，则按兼容接口初始化
    base_url = str(kwargs.pop("base_url", "") or "").strip()
    if base_url:
        return _create_openai_compatible(model=model, api_key=api_key, base_url=base_url, **kwargs)

    # 流式场景下默认请求返回 usage（通过 model_kwargs 注入，避免触发「非默认参数」warning）
    model_kwargs = kwargs.get("model_kwargs") if isinstance(kwargs.get("model_kwargs"), dict) else {}
    if "stream_options" not in model_kwargs and "stream_options" not in kwargs:
        model_kwargs["stream_options"] = {"include_usage": True}
    kwargs["model_kwargs"] = model_kwargs
    # OpenAI 接口要求 stream_options 与 stream 同时显式开启
    kwargs.setdefault("streaming", True)
    try:
        return ChatOpenAI(model=model, api_key=api_key, **kwargs)
    except TypeError:
        # 兼容旧参数名/旧版本：可能不支持 model_kwargs/stream_options
        if "model_kwargs" in kwargs and isinstance(kwargs["model_kwargs"], dict):
            kwargs["model_kwargs"].pop("stream_options", None)
        return ChatOpenAI(model=model, openai_api_key=api_key, **kwargs)

# 创建gemini模型接口
def _create_gemini(model: str, api_key: str, **kwargs: Any) -> Any:
    """
    Gemini: 使用 langchain-google-genai（ChatGoogleGenerativeAI）

    依赖：
    - langchain-google-genai
    """
    if ChatGoogleGenerativeAI is None:
        raise ImportError(
            "未安装 Gemini 依赖：请安装 `langchain-google-genai` 后再使用 provider=gemini"
        )
    # 常见参数名：google_api_key
    return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, **kwargs)

# 创建qwen模型接口
def _create_qwen(model: str, api_key: str, **kwargs: Any) -> Any:
    """
    Qwen：OpenAI compatible

    默认 base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    可在 config/model.yaml 的 profile 中用 base_url 覆盖。
    """
    base_url = str(kwargs.pop("base_url", "") or "https://dashscope.aliyuncs.com/compatible-mode/v1").strip()
    return _create_openai_compatible(model=model, api_key=api_key, base_url=base_url, **kwargs)

# 创建deepseek模型接口
def _create_deepseek(model: str, api_key: str, **kwargs: Any) -> Any:
    """
    DeepSeek：OpenAI compatible

    默认 base_url: https://api.deepseek.com
    可在 config/model.yaml 的 profile 中用 base_url 覆盖。
    """
    base_url = str(kwargs.pop("base_url", "") or "https://api.deepseek.com").strip()
    return _create_openai_compatible(model=model, api_key=api_key, base_url=base_url, **kwargs)

# 创建kimi模型接口
def _create_kimi(model: str, api_key: str, **kwargs: Any) -> Any:
    """
    Kimi（Moonshot）：OpenAI compatible

    默认 base_url: https://api.moonshot.cn/v1
    可在 config/model.yaml 的 profile 中用 base_url 覆盖。
    """
    base_url = str(kwargs.pop("base_url", "") or "https://api.moonshot.cn/v1").strip()
    return _create_openai_compatible(model=model, api_key=api_key, base_url=base_url, **kwargs)


def _create_openai_compatible_generic(model: str, api_key: str, **kwargs: Any) -> Any:
    """
    通用 OpenAI-compatible provider。

    base_url 来源优先级：
    1. config/model.yaml 中 profile 顶层 base_url
    2. profile.kwargs.base_url
    3. 环境变量 OPENAI_BASE_URL / API_BASE_URL / BASE_URL
    """
    base_url = str(
        kwargs.pop("base_url", "")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("API_BASE_URL")
        or os.getenv("BASE_URL")
        or ""
    ).strip()
    if not base_url:
        raise ValueError(
            "provider=openai_compatible 时缺少 base_url。"
            "请在 config/model.yaml 对应 profile 配置 base_url，或设置环境变量 OPENAI_BASE_URL。"
        )
    return _create_openai_compatible(model=model, api_key=api_key, base_url=base_url, **kwargs)


# 注册表：便于扩展新厂商
_PROVIDER_CREATORS: Dict[str, Callable[..., Any]] = {
    "openai": _create_openai,
    "openai_compatible": _create_openai_compatible_generic,
    "gemini": _create_gemini,
    "qwen": _create_qwen,
    "deepseek": _create_deepseek,
    "kimi": _create_kimi,
}


# 模型工厂，用于实例化模型
class ModelFactory:
    """模型工厂：实例化LLM模型"""

    @staticmethod
    def create(
        *,
        profile: Optional[str] = "main",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ):
        profile = profile or "main"
        config = _get_profile_config(profile)
        env = get_env_config()
        provider_val, model_val, api_key = _resolve_provider_model_api_key(
            config, env, provider, model
        )

        creator = _PROVIDER_CREATORS.get(provider_val)
        if creator is None:
            supported = ", ".join(sorted(_PROVIDER_CREATORS.keys()))
            raise ValueError(
                f"不支持的 provider: {provider_val}。当前支持: {supported}"
            )

        # 支持在 model.yaml 中给每个 profile 传额外 kwargs（如 temperature/max_tokens/base_url 等）
        config_kwargs = config.get("kwargs") if isinstance(config.get("kwargs"), dict) else {}
        merged_kwargs: Dict[str, Any] = {**config_kwargs, **kwargs}
        # 允许把 base_url 放在 profile 顶层（便于 deepseek 配置）
        if "base_url" in config and "base_url" not in merged_kwargs:
            merged_kwargs["base_url"] = config.get("base_url")

        return creator(model_val, api_key, **merged_kwargs)

# 具体的模型业务
def get_react_model():
    """主流程模型：作为 ReAct Agent 底座（对应 model.yaml 中 main）"""
    return ModelFactory.create(profile="main")


def get_text_generation_model():
    """文本生成模型：用于文本生成任务（对应 model.yaml 中 text_generation）"""
    return ModelFactory.create(profile="text_generation")


def get_element_extraction_model():
    """元素提取模型：用于从文本中提取结构化信息（对应 model.yaml 中 element_extraction）"""
    return ModelFactory.create(profile="element_extraction")


def get_code_generation_model():
    """代码生成模型：用于代码生成任务（对应 model.yaml 中 code_generation）"""
    return ModelFactory.create(profile="code_generation")
