"""任务上下文：TASK_ID 在 main 中生成，经 stream(task_id=...) 传入后供各工具读取。"""

from __future__ import annotations

import threading
from contextvars import ContextVar
from typing import Optional

# 当前任务 ID，由 main 生成、在 agent.stream(task_id=...) 时设置，供 tools 等写入 sandbox/任务ID
TASK_ID_CTX: ContextVar[Optional[str]] = ContextVar("task_id", default=None)

# 全局任务ID存储（作为后备方案）
_global_task_id_store: dict[str, Optional[str]] = {}


def get_task_id() -> Optional[str]:
    """
    获取当前任务ID。
    
    优先从 ContextVar 获取，如果获取不到，尝试从全局存储获取。
    
    Returns:
        任务ID，如果不存在则返回 None
    """
    # 优先从 ContextVar 获取
    task_id = TASK_ID_CTX.get()
    if task_id:
        return task_id
    
    # 如果 ContextVar 中没有，尝试从全局存储获取（使用线程ID作为key）
    thread_id = threading.get_ident()
    return _global_task_id_store.get(str(thread_id))


def set_task_id(task_id: Optional[str]) -> None:
    """
    设置当前任务ID。
    
    Args:
        task_id: 任务ID
    """
    if task_id:
        TASK_ID_CTX.set(task_id)
        # 同时存储到全局字典（作为后备）
        thread_id = threading.get_ident()
        _global_task_id_store[str(thread_id)] = task_id
    else:
        TASK_ID_CTX.set(None)
        thread_id = threading.get_ident()
        _global_task_id_store.pop(str(thread_id), None)