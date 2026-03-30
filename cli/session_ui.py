"""Session UI：处理会话选择和交互。"""

from __future__ import annotations

from typing import Optional
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from utils.session_manager import get_session_manager

console = Console()


def show_session_selector(limit: int = 5) -> Optional[str]:
    """
    显示会话选择器，让用户选择要恢复的会话
    
    Args:
        limit: 显示的会话数量限制
        
    Returns:
        选中的任务 ID，如果用户取消则返回 None
    """
    session_manager = get_session_manager()
    sessions = session_manager.list_sessions(limit)
    
    if not sessions:
        console.print("[yellow]没有找到之前的会话。[/yellow]")
        return None
    
    # 创建表格显示会话列表
    table = Table(title="最近的会话", show_header=True, header_style="bold magenta")
    table.add_column("序号", style="cyan", width=6)
    table.add_column("任务 ID", style="green", width=40)
    table.add_column("描述", style="white", width=50)
    table.add_column("更新时间", style="dim", width=20)
    
    for idx, session in enumerate(sessions, 1):
        task_id = session.get("task_id", "N/A")
        description = session.get("description", "无描述")
        updated_at = session.get("updated_at", "N/A")
        # 格式化时间
        if updated_at != "N/A":
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(updated_at)
                updated_at = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        
        table.add_row(
            str(idx),
            task_id[:36] + "..." if len(task_id) > 36 else task_id,
            description[:48] + "..." if len(description) > 48 else description,
            updated_at
        )
    
    console.print()
    console.print(table)
    console.print()
    
    # 让用户选择（按Enter选择第一个，或输入序号）
    while True:
        try:
            choice = Prompt.ask(
                f"[cyan]请选择要恢复的会话 (1-{len(sessions)}, 按 Enter 确定)[/cyan]",
                default="1"
            )
            
            if not choice:
                # 按Enter，选择第一个
                selected_session = sessions[0]
                task_id = selected_session.get("task_id")
                console.print(f"[green]已选择会话: {task_id}[/green]")
                return task_id
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(sessions):
                selected_session = sessions[choice_num - 1]
                task_id = selected_session.get("task_id")
                console.print(f"[green]已选择会话: {task_id}[/green]")
                return task_id
            else:
                console.print(f"[red]请输入 1-{len(sessions)} 之间的数字[/red]")
        except ValueError:
            console.print("[red]请输入有效的数字[/red]")
        except KeyboardInterrupt:
            return None
