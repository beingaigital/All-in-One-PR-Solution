"""CLI 主入口：交互式命令行界面。"""

from __future__ import annotations

import sys
from rich.prompt import Prompt
from cli.display import print_icon, print_welcome, console
from cli.session_ui import show_session_selector
from cli.tools_ui import show_tools_list
from cli.profile_ui import show_profile_status
from cli.skills_ui import show_skills_status
from cli.models_ui import show_models_list
from cli.clear_utils import confirm_and_clear


def _run_session_loop(task_id: str | None = None) -> None:
    """延迟导入交互循环，避免启动时强依赖 Agent 运行时。"""
    from cli.interactive import run_session_loop

    run_session_loop(task_id=task_id)


def interactive() -> None:
    """进入交互式模式（默认命令）"""
    # 显示图标和欢迎信息
    print_icon()
    print_welcome()
    
    # 主循环：处理命令
    while True:
        try:
            # 在 user 提示前添加绿色横线作为对话区隔
            console.print("[green]────────────────────────────────────────────────────────────[/green]")
            user_input = Prompt.ask("[bold cyan]user[/bold cyan]")
            
            if not user_input:
                continue
            
            # 处理系统级命令（以 / 开头）
            if user_input.strip().startswith("/"):
                # 处理 /exit 命令
                if user_input.strip() == "/exit":
                    console.print(f"\n[cyan]感谢使用 [bold magenta]PRClaw[/bold magenta]，再见！[/cyan]\n")
                    break
                
                # 处理 /new 命令
                if user_input.strip() == "/new":
                    _run_session_loop(task_id=None)
                    continue
                
                # 处理 /memory 命令（选择会话）
                if user_input.strip() == "/memory":
                    selected_task_id = show_session_selector(limit=5)
                    if selected_task_id:
                        _run_session_loop(task_id=selected_task_id)
                    continue
                
                # 处理 /models 命令（显示模型配置）
                if user_input.strip() == "/models":
                    show_models_list()
                    continue
                
                # 处理 /tools 命令（显示工具列表）
                if user_input.strip().startswith("/tools"):
                    force_reload = user_input.strip() in {"/tools reload", "/tools --reload"}
                    show_tools_list(force_reload=force_reload)
                    continue

                # 处理 /profile 命令（显示 profile layer）
                if user_input.strip().startswith("/profile"):
                    force_reload = user_input.strip() in {"/profile reload", "/profile --reload"}
                    show_profile_status(force_reload=force_reload)
                    continue

                # 处理 /skills 命令（显示技能层状态）
                if user_input.strip().startswith("/skills"):
                    raw = user_input.strip()
                    force_reload = False
                    query = None
                    if raw in {"/skills reload", "/skills --reload"}:
                        force_reload = True
                    elif raw.startswith("/skills match "):
                        query = raw[len("/skills match "):].strip() or None
                    show_skills_status(force_reload=force_reload, query=query)
                    continue
                
                # 处理 /clear 命令（清除 memory 和 sandbox）
                if user_input.strip() == "/clear":
                    confirm_and_clear()
                    continue
                
                # 处理其他未知命令
                console.print(f"[yellow]未知命令: {user_input}[/yellow]")
                console.print("[cyan]可用命令:[/cyan]")
                console.print("  [cyan]/new[/cyan]     - 开启新的会话")
                console.print("  [cyan]/memory[/cyan]  - 查看并恢复之前的会话")
                console.print("  [cyan]/models[/cyan]  - 查看所有模型配置")
                console.print("  [cyan]/tools[/cyan]   - 查看所有可用工具")
                console.print("  [cyan]/tools reload[/cyan] - 重新扫描工具并刷新列表")
                console.print("  [cyan]/profile[/cyan] - 查看 profile layer 加载状态")
                console.print("  [cyan]/profile reload[/cyan] - 重新加载 profile 文件")
                console.print("  [cyan]/skills[/cyan]  - 查看 skills layer 状态")
                console.print("  [cyan]/skills reload[/cyan] - 重新加载 skills 配置")
                console.print("  [cyan]/skills match <query>[/cyan] - 预览 query 的技能自动激活结果")
                console.print("  [cyan]/clear[/cyan]   - 清除 memory 和 sandbox")
                console.print("  [cyan]/exit[/cyan]    - 退出程序")
                continue
            
            # 默认行为：只提示，不创建会话
            console.print("[yellow]提示: 使用 '/new' 开启新会话，或使用 '/memory' 恢复之前的会话[/yellow]")
            
        except KeyboardInterrupt:
            console.print(f"\n\n[cyan]感谢使用 [bold magenta]PRClaw[/bold magenta]，再见！[/cyan]\n")
            sys.exit(0)
        except EOFError:
            console.print(f"\n\n[cyan]感谢使用 [bold magenta]PRClaw[/bold magenta]，再见！[/cyan]\n")
            sys.exit(0)
        except Exception as e:
            console.print(f"\n[red]❌[/red] [red]发生错误:[/red] [white]{str(e)}[/white]\n")
            import traceback
            traceback.print_exc()


def main() -> None:
    """主函数：启动交互式模式。"""
    interactive()


if __name__ == "__main__":
    main()
