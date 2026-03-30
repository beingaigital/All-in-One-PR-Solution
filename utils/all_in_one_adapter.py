"""All-in-One-PR-Solution 适配层。"""

from __future__ import annotations

import contextlib
import io
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.path import get_project_root
from utils.prclaw_config import get_all_in_one_root, get_prclaw_config, get_unified_config_path


_ADAPTER: Optional["AllInOneAdapter"] = None
_ADAPTER_LOCK = threading.Lock()


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
        return
    except Exception:
        pass

    try:
        with open(env_path, "r", encoding="utf-8") as fh:
            for line in fh:
                item = line.strip()
                if not item or item.startswith("#") or "=" not in item:
                    continue
                key, value = item.split("=", 1)
                key = key.strip()
                if key and key not in os.environ:
                    os.environ[key] = value.strip()
    except Exception:
        return


def _inject_python_path(path: Path) -> None:
    import sys

    p = str(path.resolve())
    if p not in sys.path:
        sys.path.insert(0, p)


def _quiet_call(fn, *args, **kwargs):
    """静默执行可能会向 stdout/stderr 打日志的调用。"""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        return fn(*args, **kwargs)


class AllInOneAdapter:
    """对 UnifiedPRSystem 的懒加载封装。"""

    def __init__(self, all_in_one_root: Optional[Path] = None, enable_rlhf: bool = True):
        self.cfg = get_prclaw_config()
        self.all_in_one_root = (all_in_one_root or get_all_in_one_root()).resolve()
        self.enable_rlhf = enable_rlhf
        self._system = None
        self._init_error: Optional[Exception] = None
        self._lock = threading.Lock()

    def _init_embedded_system(self):
        project_root = get_project_root()
        _inject_python_path(project_root)
        _load_env_file(project_root / ".env")
        config_path = get_unified_config_path()

        def _construct():
            from utils.unified_pr_system_local import UnifiedPRSystem

            if config_path.exists():
                return UnifiedPRSystem(
                    config_path=str(config_path),
                    enable_rlhf=self.enable_rlhf,
                )
            return UnifiedPRSystem(enable_rlhf=self.enable_rlhf)

        self._system = _quiet_call(_construct)

    def _init_external_system(self):
        _inject_python_path(self.all_in_one_root)
        _load_env_file(self.all_in_one_root / ".env")
        config_path = self.all_in_one_root / "unified_config.yaml"

        def _construct():
            from unified_pr_system import UnifiedPRSystem

            if config_path.exists():
                return UnifiedPRSystem(
                    config_path=str(config_path),
                    enable_rlhf=self.enable_rlhf,
                )
            return UnifiedPRSystem(enable_rlhf=self.enable_rlhf)

        self._system = _quiet_call(_construct)

    def _init_system(self):
        if self.cfg.use_embedded_unified_system:
            try:
                self._init_embedded_system()
                return
            except Exception:
                if not self.cfg.allow_external_unified_fallback:
                    raise
        self._init_external_system()

    def get_system(self):
        if self._system is not None:
            return self._system
        if self._init_error is not None:
            raise RuntimeError(f"UnifiedPRSystem 初始化失败: {self._init_error}") from self._init_error

        with self._lock:
            if self._system is not None:
                return self._system
            if self._init_error is not None:
                raise RuntimeError(f"UnifiedPRSystem 初始化失败: {self._init_error}") from self._init_error
            try:
                self._init_system()
                return self._system
            except Exception as exc:
                self._init_error = exc
                raise RuntimeError(f"UnifiedPRSystem 初始化失败: {exc}") from exc

    def close(self) -> None:
        sys_obj = self._system
        if sys_obj is None:
            return
        try:
            close_fn = getattr(sys_obj, "close", None)
            if callable(close_fn):
                close_fn()
        except Exception:
            pass

    def build_plan_query(self, enterprise_info: Dict[str, Any]) -> str:
        sys_obj = self.get_system()
        fn = getattr(sys_obj, "_build_plan_query", None)
        if callable(fn):
            try:
                return str(fn(enterprise_info)).strip() or "公关传播策略"
            except Exception:
                pass

        parts: List[str] = []
        for key in ["enterprise_name", "industry", "pr_goal", "market_type", "enterprise_stage"]:
            value = str(enterprise_info.get(key, "")).strip()
            if value:
                parts.append(value)
        return " ".join(parts) if parts else "公关传播策略"

    def query_knowledge(self, query: str, use_graph: bool = True) -> str:
        sys_obj = self.get_system()
        return str(_quiet_call(sys_obj.query_knowledge, query, use_graph=use_graph))

    def generate_plan(
        self,
        enterprise_info: Dict[str, Any],
        output_types: Optional[List[str]] = None,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        sys_obj = self.get_system()
        cfg = get_prclaw_config()
        final_output_types = output_types or cfg.default_output_types

        plan_generator = getattr(sys_obj, "plan_generator", None)
        if plan_generator is not None:
            try:
                return _quiet_call(
                    plan_generator.generate_plan,
                    enterprise_info=enterprise_info,
                    output_types=final_output_types,
                    context=context,
                )
            except Exception:
                pass

        return _quiet_call(
            sys_obj.generate_pr_plan,
            enterprise_info,
            final_output_types,
        )

    def generate_report(
        self,
        requirements: Dict[str, Any],
        confirm: bool = True,
        dry_run: bool = False,
        use_graph: bool = True,
    ) -> Dict[str, Any]:
        sys_obj = self.get_system()

        if not confirm:
            return _quiet_call(sys_obj.confirm_report_requirements, requirements)

        report_generator = getattr(sys_obj, "report_generator", None)
        if report_generator is not None:
            try:
                return _quiet_call(
                    report_generator.generate_report,
                    requirements,
                    dry_run=dry_run,
                    use_graph=use_graph,
                )
            except Exception:
                pass

        return _quiet_call(
            sys_obj.generate_report,
            requirements,
            confirm=True,
            dry_run=dry_run,
        )

    def collect_feedback(
        self,
        plan_id: str,
        rating: float,
        comment: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        sys_obj = self.get_system()
        return _quiet_call(
            sys_obj.collect_feedback,
            plan_id=plan_id,
            rating=rating,
            comment=comment,
            **kwargs,
        )


def get_all_in_one_adapter(force_reload: bool = False) -> AllInOneAdapter:
    """获取单例适配器。"""
    global _ADAPTER
    with _ADAPTER_LOCK:
        if force_reload and _ADAPTER is not None:
            try:
                _ADAPTER.close()
            except Exception:
                pass
            _ADAPTER = None

        if _ADAPTER is None:
            _ADAPTER = AllInOneAdapter()

        return _ADAPTER
