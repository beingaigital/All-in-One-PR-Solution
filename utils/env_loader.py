"""从 .env 加载环境变量，供 model/factory 等使用。"""

from __future__ import annotations

import os
from typing import Optional
from dotenv import load_dotenv

from utils.path import get_project_root


def _load_dotenv() -> None:
    try:
        root = get_project_root()
        candidates = [
            root / ".env",
            root.parent / ".env",
        ]
        loaded = False
        for env_file in candidates:
            if env_file.exists():
                load_dotenv(env_file, override=False)
                loaded = True
        if not loaded:
            load_dotenv(override=False)
    except ImportError:
        pass


_env_config: Optional["EnvConfig"] = None


class EnvConfig:
    """从 .env 读取的环境配置"""

    def __init__(self) -> None:
        _load_dotenv()
        # 兼容 _APIKEY 与 _API_KEY 两种命名
        self.OPENAI_APIKEY: Optional[str] = (
            os.environ.get("OPENAI_APIKEY")
            or os.environ.get("OPENAI_API_KEY")
            or None
        )
        self.GEMINI_APIKEY: Optional[str] = (
            os.environ.get("GEMINI_APIKEY")
            or os.environ.get("GEMINI_API_KEY")
            or None
        )
        self.QWEN_APIKEY: Optional[str] = (
            os.environ.get("QWEN_APIKEY")
            or os.environ.get("QWEN_API_KEY")
            or None
        )
        self.DASHSCOPE_APIKEY: Optional[str] = (
            os.environ.get("DASHSCOPE_APIKEY")
            or os.environ.get("DASHSCOPE_API_KEY")
            or None
        )
        self.DEEPSEEK_APIKEY: Optional[str] = (
            os.environ.get("DEEPSEEK_APIKEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or None
        )
        self.KIMI_APIKEY: Optional[str] = (
            os.environ.get("KIMI_APIKEY")
            or os.environ.get("KIMI_API_KEY")
            or None
        )

    def get_api_key(self, env_var_name: str) -> Optional[str]:
        """根据配置中的 api_key_env 取对应 API Key。"""
        direct = os.environ.get(env_var_name)
        if direct:
            return direct

        attr = getattr(self, env_var_name, None)
        if attr:
            return attr

        if env_var_name.endswith("_APIKEY"):
            alt = env_var_name.replace("_APIKEY", "_API_KEY")
            return os.environ.get(alt)
        if env_var_name.endswith("_API_KEY"):
            alt = env_var_name.replace("_API_KEY", "_APIKEY")
            return os.environ.get(alt)

        return None


def get_env_config() -> EnvConfig:
    """获取单例 EnvConfig，首次调用时加载 .env。"""
    global _env_config
    if _env_config is None:
        _env_config = EnvConfig()
    return _env_config
