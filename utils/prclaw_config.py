"""PRClaw 配置加载器。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from utils.path import get_config_path, get_project_root


@dataclass
class WebSearchSettings:
    provider: str = "auto"
    max_results: int = 5
    timeout_seconds: int = 15


@dataclass
class ExportSettings:
    save_markdown: bool = True


@dataclass
class PRClawConfig:
    use_embedded_unified_system: bool
    allow_external_unified_fallback: bool
    unified_config_path: str
    all_in_one_path: str
    default_output_types: List[str]
    default_use_graph_rag: bool
    default_use_web_search: bool
    web_search: WebSearchSettings
    export: ExportSettings
    config_path: Path


_CONFIG_CACHE: Optional[PRClawConfig] = None
_CONFIG_MTIME: Optional[float] = None


def _normalize_output_types(value: Any) -> List[str]:
    if value is None:
        return ["A", "B", "C"]
    if isinstance(value, str):
        raw_items = [x.strip() for x in value.replace("，", ",").split(",")]
    elif isinstance(value, list):
        raw_items = [str(x).strip() for x in value]
    else:
        raw_items = []

    allowed = {"A", "B", "C", "D", "E", "F"}
    output: List[str] = []
    for item in raw_items:
        up = item.upper()
        if up in allowed and up not in output:
            output.append(up)
    return output or ["A", "B", "C"]


def _infer_all_in_one_path() -> Path:
    project_root = get_project_root()
    parent = project_root.parent

    if (parent / "unified_pr_system.py").exists():
        return parent

    candidate = parent / "All-in-One-PR-Solution"
    if (candidate / "unified_pr_system.py").exists():
        return candidate

    return parent


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _build_default(path: Path) -> PRClawConfig:
    all_in_one_path = str(_infer_all_in_one_path())
    return PRClawConfig(
        use_embedded_unified_system=True,
        allow_external_unified_fallback=False,
        unified_config_path="config/unified_config.yaml",
        all_in_one_path=all_in_one_path,
        default_output_types=["A", "B", "C"],
        default_use_graph_rag=True,
        default_use_web_search=True,
        web_search=WebSearchSettings(),
        export=ExportSettings(),
        config_path=path,
    )


def get_prclaw_config(force_reload: bool = False) -> PRClawConfig:
    """读取 config/prclaw.yaml，并做缓存。"""
    global _CONFIG_CACHE, _CONFIG_MTIME

    config_path = get_config_path("prclaw.yaml")
    mtime = None
    if config_path.exists():
        try:
            mtime = config_path.stat().st_mtime
        except Exception:
            mtime = None

    if not force_reload and _CONFIG_CACHE is not None and _CONFIG_MTIME == mtime:
        return _CONFIG_CACHE

    default = _build_default(config_path)
    raw = _load_yaml(config_path)

    all_in_one_path = str(raw.get("all_in_one_path") or default.all_in_one_path).strip()
    if not all_in_one_path:
        all_in_one_path = default.all_in_one_path

    web_raw = raw.get("web_search") if isinstance(raw.get("web_search"), dict) else {}
    export_raw = raw.get("export") if isinstance(raw.get("export"), dict) else {}

    config = PRClawConfig(
        use_embedded_unified_system=bool(
            raw.get("use_embedded_unified_system", default.use_embedded_unified_system)
        ),
        allow_external_unified_fallback=bool(
            raw.get("allow_external_unified_fallback", default.allow_external_unified_fallback)
        ),
        unified_config_path=str(raw.get("unified_config_path") or default.unified_config_path).strip()
        or default.unified_config_path,
        all_in_one_path=all_in_one_path,
        default_output_types=_normalize_output_types(raw.get("default_output_types")),
        default_use_graph_rag=bool(raw.get("default_use_graph_rag", default.default_use_graph_rag)),
        default_use_web_search=bool(raw.get("default_use_web_search", default.default_use_web_search)),
        web_search=WebSearchSettings(
            provider=str(web_raw.get("provider", default.web_search.provider) or "auto").strip() or "auto",
            max_results=max(1, _safe_int(web_raw.get("max_results"), default.web_search.max_results)),
            timeout_seconds=max(3, _safe_int(web_raw.get("timeout_seconds"), default.web_search.timeout_seconds)),
        ),
        export=ExportSettings(
            save_markdown=bool(export_raw.get("save_markdown", default.export.save_markdown)),
        ),
        config_path=config_path,
    )

    _CONFIG_CACHE = config
    _CONFIG_MTIME = mtime
    return config


def get_all_in_one_root() -> Path:
    """返回 All-in-One-PR-Solution 根目录。"""
    cfg = get_prclaw_config()
    raw = Path(cfg.all_in_one_path).expanduser()
    if not raw.is_absolute():
        raw = (get_project_root() / raw).resolve()
    return raw.resolve()


def get_unified_config_path() -> Path:
    cfg = get_prclaw_config()
    raw = Path(cfg.unified_config_path).expanduser()
    if not raw.is_absolute():
        raw = (get_project_root() / raw).resolve()
    return raw.resolve()
