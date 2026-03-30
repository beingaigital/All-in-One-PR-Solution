"""工具注册中心：支持自动发现 + 配置启停。"""

from __future__ import annotations

import importlib
import pkgutil
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from utils.path import get_config_path

try:
    from langchain_core.tools import BaseTool
except Exception:  # pragma: no cover
    BaseTool = None


@dataclass
class ToolRegistryConfig:
    """工具注册中心配置。"""

    auto_discover: bool = True
    search_packages: List[str] = field(default_factory=lambda: ["tools"])
    include_modules: List[str] = field(default_factory=list)
    exclude_modules: List[str] = field(default_factory=lambda: ["tools.__init__"])
    enabled_tools: List[str] = field(default_factory=list)
    disabled_tools: List[str] = field(default_factory=list)


@dataclass
class ToolInfo:
    """注册后的工具信息。"""

    name: str
    description: str
    module: str
    tool: Any


@dataclass
class ToolRegistry:
    """注册中心结果。"""

    config: ToolRegistryConfig
    config_path: Path
    modules_scanned: List[str]
    module_errors: List[Dict[str, str]]
    discovered_tools: List[ToolInfo]
    enabled_tools: List[ToolInfo]
    disabled_tools: List[Dict[str, str]]


_registry_cache: Optional[ToolRegistry] = None
_registry_cache_key: Optional[tuple[Optional[float]]] = None


def _normalize_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        if item is None:
            continue
        s = str(item).strip()
        if s:
            result.append(s)
    return result


def _load_config(config_path: Path) -> ToolRegistryConfig:
    default = ToolRegistryConfig()
    if not config_path.exists():
        return default

    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except Exception as exc:
        warnings.warn(f"tools.yaml 读取失败，使用默认配置: {exc}")
        return default

    if not isinstance(raw, dict):
        warnings.warn("tools.yaml 格式错误（应为字典），使用默认配置")
        return default

    return ToolRegistryConfig(
        auto_discover=bool(raw.get("auto_discover", default.auto_discover)),
        search_packages=_normalize_string_list(raw.get("search_packages"))
        or default.search_packages,
        include_modules=_normalize_string_list(raw.get("include_modules")),
        exclude_modules=_normalize_string_list(raw.get("exclude_modules"))
        or default.exclude_modules,
        enabled_tools=_normalize_string_list(raw.get("enabled_tools")),
        disabled_tools=_normalize_string_list(raw.get("disabled_tools")),
    )


def _build_cache_key(config_path: Path) -> tuple[Optional[float]]:
    if not config_path.exists():
        return (None,)
    try:
        return (config_path.stat().st_mtime,)
    except Exception:
        return (None,)


def _is_excluded(module_name: str, excluded_prefixes: Iterable[str]) -> bool:
    for prefix in excluded_prefixes:
        if module_name == prefix or module_name.startswith(f"{prefix}."):
            return True
    return False


def _collect_modules(
    config: ToolRegistryConfig,
    module_errors: List[Dict[str, str]],
) -> List[str]:
    module_names = set(config.include_modules)

    if config.auto_discover:
        for package_name in config.search_packages:
            try:
                pkg = importlib.import_module(package_name)
            except Exception as exc:
                module_errors.append({"module": package_name, "error": str(exc)})
                continue

            if getattr(pkg, "__path__", None):
                for _, name, is_pkg in pkgutil.walk_packages(
                    pkg.__path__,
                    prefix=f"{pkg.__name__}.",
                ):
                    if not is_pkg:
                        module_names.add(name)
            else:
                module_names.add(package_name)

    names = [
        name
        for name in sorted(module_names)
        if not _is_excluded(name, config.exclude_modules)
    ]
    return names


def _is_tool_instance(obj: Any) -> bool:
    if obj is None:
        return False
    if BaseTool is not None and isinstance(obj, BaseTool):
        return True

    # 兼容非标准工具对象（只要具备最小调用协议）
    name = getattr(obj, "name", None)
    invoke = getattr(obj, "invoke", None)
    return bool(name) and callable(invoke)


def _extract_module_tools(module: Any) -> List[Any]:
    candidates: List[Any] = []

    explicit = getattr(module, "TOOLS", None)
    if isinstance(explicit, (list, tuple)):
        candidates.extend(explicit)

    for value in vars(module).values():
        if _is_tool_instance(value):
            candidates.append(value)

    deduped: List[Any] = []
    seen_ids = set()
    for item in candidates:
        marker = id(item)
        if marker in seen_ids:
            continue
        seen_ids.add(marker)
        deduped.append(item)
    return deduped


def _tool_description(tool_obj: Any) -> str:
    raw = getattr(tool_obj, "description", "") or getattr(tool_obj, "__doc__", "") or ""
    text = str(raw).strip()
    if not text:
        return "无描述"

    # 优先截取“描述：”后的核心说明
    marker = "描述："
    if marker in text:
        text = text.split(marker, 1)[1]
        for stop in ("使用时机：", "输入：", "输出：", "注意："):
            if stop in text:
                text = text.split(stop, 1)[0]
                break

    compact = " ".join(text.split()).strip()
    if not compact:
        return "无描述"
    if len(compact) > 140:
        return compact[:137] + "..."
    return compact


def _build_registry(config_path: Path) -> ToolRegistry:
    config = _load_config(config_path)
    module_errors: List[Dict[str, str]] = []
    modules = _collect_modules(config, module_errors)

    discovered: List[ToolInfo] = []
    disabled: List[Dict[str, str]] = []
    tools_by_name: Dict[str, ToolInfo] = {}

    for module_name in modules:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            module_errors.append({"module": module_name, "error": str(exc)})
            continue

        for tool_obj in _extract_module_tools(module):
            name = str(getattr(tool_obj, "name", "")).strip()
            if not name:
                continue

            info = ToolInfo(
                name=name,
                description=_tool_description(tool_obj),
                module=module_name,
                tool=tool_obj,
            )
            discovered.append(info)

            if name in tools_by_name:
                disabled.append(
                    {
                        "name": name,
                        "module": module_name,
                        "reason": f"重复工具名，已保留 {tools_by_name[name].module}",
                    }
                )
                continue
            tools_by_name[name] = info

    enabled: List[ToolInfo] = []
    enabled_filter = set(config.enabled_tools)
    disabled_filter = set(config.disabled_tools)

    for name in sorted(tools_by_name.keys()):
        info = tools_by_name[name]
        if enabled_filter and name not in enabled_filter:
            disabled.append({"name": name, "module": info.module, "reason": "未在 enabled_tools 列表中"})
            continue
        if name in disabled_filter:
            disabled.append({"name": name, "module": info.module, "reason": "被 disabled_tools 显式禁用"})
            continue
        enabled.append(info)

    for name in sorted(enabled_filter):
        if name not in tools_by_name:
            disabled.append({"name": name, "module": "-", "reason": "enabled_tools 中声明但未发现该工具"})
    for name in sorted(disabled_filter):
        if name not in tools_by_name:
            disabled.append({"name": name, "module": "-", "reason": "disabled_tools 中声明但未发现该工具"})

    return ToolRegistry(
        config=config,
        config_path=config_path,
        modules_scanned=modules,
        module_errors=module_errors,
        discovered_tools=sorted(discovered, key=lambda x: (x.name, x.module)),
        enabled_tools=enabled,
        disabled_tools=disabled,
    )


def clear_tool_registry_cache() -> None:
    """清空注册中心缓存。"""
    global _registry_cache, _registry_cache_key
    _registry_cache = None
    _registry_cache_key = None


def get_tool_registry(force_reload: bool = False) -> ToolRegistry:
    """获取工具注册中心结果（带缓存）。"""
    global _registry_cache, _registry_cache_key

    config_path = get_config_path("tools.yaml")
    cache_key = _build_cache_key(config_path)

    if not force_reload and _registry_cache is not None and _registry_cache_key == cache_key:
        return _registry_cache

    registry = _build_registry(config_path)
    _registry_cache = registry
    _registry_cache_key = cache_key
    return registry


def get_enabled_tool_infos(force_reload: bool = False) -> List[ToolInfo]:
    """返回启用工具的信息列表。"""
    return get_tool_registry(force_reload=force_reload).enabled_tools


def load_agent_tools(force_reload: bool = False) -> List[Any]:
    """返回可直接传给 LangChain Agent 的工具对象列表。"""
    return [info.tool for info in get_enabled_tool_infos(force_reload=force_reload)]
