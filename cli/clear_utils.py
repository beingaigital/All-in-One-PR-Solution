"""清理工具：清除 memory 和 sandbox 中的内容。"""

from __future__ import annotations

import shutil
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm

from utils.path import get_stm_dir, get_sandbox_dir

console = Console()


def clear_memory_and_sandbox() -> None:
    """
    清除 memory/STM 下的所有内容以及 sandbox 除测试外的所有文件夹
    """
    stm_dir = get_stm_dir()
    sandbox_dir = get_sandbox_dir()
    
    cleared_items = []
    
    # 清除 memory/STM 下的所有内容
    if stm_dir.exists():
        for item in stm_dir.iterdir():
            if item.is_file():
                item.unlink()
                cleared_items.append(f"文件: {item.name}")
            elif item.is_dir():
                shutil.rmtree(item)
                cleared_items.append(f"文件夹: {item.name}")
    
    # 清除 sandbox 除测试外的所有文件夹
    if sandbox_dir.exists():
        for item in sandbox_dir.iterdir():
            if item.is_dir() and item.name != "测试":
                shutil.rmtree(item)
                cleared_items.append(f"sandbox/{item.name}")
    
    if cleared_items:
        console.print(f"[green]已清除 {len(cleared_items)} 项：[/green]")
        for item in cleared_items[:10]:  # 只显示前10项
            console.print(f"  - {item}")
        if len(cleared_items) > 10:
            console.print(f"  ... 还有 {len(cleared_items) - 10} 项")
    else:
        console.print("[yellow]没有需要清除的内容[/yellow]")


def confirm_and_clear() -> None:
    """确认后清除 memory 和 sandbox。"""
    console.print("[yellow]警告：此操作将清除以下内容：[/yellow]")
    console.print("  - memory/STM 下的所有文件和文件夹")
    console.print("  - sandbox 下除'测试'外的所有文件夹")
    console.print()
    
    if Confirm.ask("[bold red]确定要执行清除操作吗？[/bold red]", default=False):
        clear_memory_and_sandbox()
    else:
        console.print("[cyan]已取消清除操作[/cyan]")
