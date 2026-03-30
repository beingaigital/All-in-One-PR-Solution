"""CLI 显示相关的辅助函数：使用 Rich 进行美化输出。"""

from __future__ import annotations

from typing import Any
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.syntax import Syntax
import json
import re

# 创建全局 Console 实例
console = Console()

def print_icon() -> None:
    """打印 PRClaw 项目的标题。"""
    logo_text = Text()
    logo_text.append("PR", style="bold cyan")
    logo_text.append("CLAW", style="bold magenta")
    logo_text.append(" · Public Relations Agent", style="bold white")
    console.print(Panel(logo_text, border_style="cyan", padding=(1, 2), expand=False))
    

def print_welcome() -> None:
    """打印欢迎信息和可用命令（使用 Rich）"""
    console.print("[bold white]欢迎使用 PRClaw - Agent智能助手[/bold white]")
    console.print()
    console.print("[yellow]可用命令：[/yellow]")
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
    console.print()


def print_token_usage(step_name: str, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
    """
    打印 token 使用信息
    
    Args:
        step_name: 步骤名称
        prompt_tokens: Prompt tokens
        completion_tokens: Completion tokens
        total_tokens: 总 tokens
    """
    console.print(
        f"[dim]Token 使用 ({step_name}): "
        f"Prompt={prompt_tokens}, "
        f"Completion={completion_tokens}, "
        f"Total={total_tokens}[/dim]"
    )


def format_timestamp() -> str:
    """返回格式化的时间戳"""
    return datetime.now().strftime("%H:%M:%S")


def print_status(message: str, status_type: str = "info") -> None:
    """
    打印状态信息（使用 Rich）
    
    Args:
        message: 状态消息
        status_type: 状态类型 ('info', 'success', 'warning', 'error', 'tool')
    """
    timestamp = format_timestamp()
    
    styles = {
        "info": "cyan",
        "success": "green",
        "warning": "yellow",
        "error": "red",
        "tool": "magenta",
    }
    
    style = styles.get(status_type, "white")
    console.print(f"[dim][{timestamp}][/dim] [{style}]{message}[/{style}]")


def print_tool_call(tool_name: str, args: dict[str, Any] | None = None) -> None:
    """
    打印工具调用信息（使用 Rich）
    
    Args:
        tool_name: 工具名称
        args: 工具参数
    """
    timestamp = format_timestamp()
    console.print(f"\n[dim][{timestamp}][/dim] [bold magenta]正在调用工具:[/bold magenta] [cyan]{tool_name}[/cyan]")
    if args:
        # 对每个参数值进行截断，确保所有参数都能显示
        MAX_VALUE_LENGTH = 150 
        truncated_args = {}
        for key, value in args.items():
            if isinstance(value, str):
                if len(value) > MAX_VALUE_LENGTH:
                    truncated_args[key] = value[:MAX_VALUE_LENGTH] + "..."
                else:
                    truncated_args[key] = value
            elif isinstance(value, (dict, list)):
                # 对于复杂类型，转换为字符串后截断（保持为字符串格式，避免 JSON 解析错误）
                value_str = json.dumps(value, ensure_ascii=False)
                if len(value_str) > MAX_VALUE_LENGTH:
                    # 直接使用字符串，避免 JSON 解析错误
                    truncated_args[key] = f"<{type(value).__name__}> {value_str[:MAX_VALUE_LENGTH]}..."
                else:
                    truncated_args[key] = value
            else:
                truncated_args[key] = value
        
        # 格式化参数，使用代码高亮
        args_str = json.dumps(truncated_args, ensure_ascii=False, indent=2)
        console.print(Syntax(args_str, "json", theme="monokai", line_numbers=False, word_wrap=True))


def print_tool_result(tool_name: str, result: str, max_length: int = 200) -> None:
    """
    打印工具调用结果（使用 Rich）
    
    Args:
        tool_name: 工具名称
        result: 工具返回结果
        max_length: 结果最大显示长度（非 JSON 时使用）
    """
    timestamp = format_timestamp()
    console.print(f"\n[dim][{timestamp}][/dim] [green]工具 [cyan]{tool_name}[/cyan] 执行完成[/green]")
    
    def _extract_json_payload(text: str) -> str:
        """
        从 text 中尽可能提取可 json.loads 的 payload。

        常见场景：
        - 工具输出本身就是 JSON 字符串
        - 工具输出是 LangChain 对象的字符串表示：content='...json...' additional_kwargs=...
        """
        t = (text or "").strip()
        if not t:
            return ""

        # 1) 已经是 JSON
        if t.startswith("{") or t.startswith("["):
            return t

        # 2) 尝试从 content='...'/content="..." 中提取（必须匹配同一种引号）
        m = re.search(r"content=(?P<q>['\"])(?P<content>.*?)(?P=q)", t, re.DOTALL)
        if m:
            inner = (m.group("content") or "").strip()
            if inner.startswith("{") or inner.startswith("["):
                return inner

        # 3) 兜底：截取最外层的大括号/中括号区域
        first_curly, last_curly = t.find("{"), t.rfind("}")
        if first_curly != -1 and last_curly != -1 and last_curly > first_curly:
            return t[first_curly : last_curly + 1].strip()

        first_bracket, last_bracket = t.find("["), t.rfind("]")
        if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
            return t[first_bracket : last_bracket + 1].strip()

        return t

    json_content = _extract_json_payload(result)
    
    # 尝试解析 JSON，使用和工具调用参数一样的格式（Syntax 高亮）
    try:
        parsed = json.loads(json_content)
        if isinstance(parsed, dict):
            # 对每个值进行截断，确保所有字段都能显示（与 print_tool_call 逻辑一致）
            MAX_VALUE_LENGTH = 150
            truncated_result = {}
            for key, value in parsed.items():
                if isinstance(value, str):
                    if len(value) > MAX_VALUE_LENGTH:
                        truncated_result[key] = value[:MAX_VALUE_LENGTH] + "..."
                    else:
                        truncated_result[key] = value
                elif isinstance(value, (dict, list)):
                    # 对于复杂类型，转换为字符串后截断
                    value_str = json.dumps(value, ensure_ascii=False)
                    if len(value_str) > MAX_VALUE_LENGTH:
                        truncated_result[key] = f"<{type(value).__name__}> {value_str[:MAX_VALUE_LENGTH]}..."
                    else:
                        truncated_result[key] = value
                else:
                    truncated_result[key] = value
            
            # 格式化结果，使用代码高亮
            result_str = json.dumps(truncated_result, ensure_ascii=False, indent=2)
            console.print(Syntax(result_str, "json", theme="monokai", line_numbers=False, word_wrap=True))
            return
        elif isinstance(parsed, list):
            # 列表类型也使用 Syntax 高亮
            result_str = json.dumps(parsed, ensure_ascii=False, indent=2)
            console.print(Syntax(result_str, "json", theme="monokai", line_numbers=False, word_wrap=True))
            return
    except (json.JSONDecodeError, TypeError):
        pass
    
    # 如果不是 JSON 或解析失败，使用普通文本显示
    if len(result) > max_length:
        preview = result[:max_length] + "..."
    else:
        preview = result
    
    console.print(f"     [bold cyan]result[/bold cyan]: [white]{preview}[/white]")


def print_agent_message(message_type: str, content: str) -> None:
    """
    打印 Agent 消息（使用 Rich Panel）
    
    Args:
        message_type: 消息类型（如 'AIMessage', 'HumanMessage'）
        content: 消息内容
    """
    timestamp = format_timestamp()
    if message_type == "AIMessage":
        # 使用 Panel 显示 Agent 回复
        panel = Panel(
            content,
            title=f"[bold blue]Agent 回复[/bold blue] [dim]({timestamp})[/dim]",
            border_style="blue",
            padding=(1, 2)
        )
        console.print()
        console.print(panel)
        console.print()
    elif message_type == "HumanMessage":
        console.print(f"[dim][{timestamp}][/dim] [yellow]用户输入:[/yellow] [white]{content}[/white]")


def print_separator() -> None:
    """打印分隔线（使用 Rich）"""
    console.print(f"\n[cyan]{'─' * 60}[/cyan]\n")
