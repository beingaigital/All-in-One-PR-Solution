"""工具列表显示：展示注册中心扫描结果与启停状态。"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from utils.tool_registry import get_tool_registry

console = Console()


def _render_enabled_tools_table(registry) -> None:
    table = Table(
        title="[bold cyan]已启用工具[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
        border_style="cyan",
        row_styles=["", "dim"],
    )
    table.add_column("工具名", style="cyan", width=24, no_wrap=True)
    table.add_column("来源模块", style="yellow", width=28, no_wrap=True)
    table.add_column("描述", style="white")

    for info in registry.enabled_tools:
        table.add_row(info.name, info.module, info.description)

    console.print(table)


def _render_disabled_tools_table(registry) -> None:
    if not registry.disabled_tools:
        return
    table = Table(
        title="[bold yellow]未启用/异常工具[/bold yellow]",
        show_header=True,
        header_style="bold yellow",
        border_style="yellow",
        row_styles=["", "dim"],
    )
    table.add_column("工具名", style="cyan", width=24, no_wrap=True)
    table.add_column("来源模块", style="yellow", width=28, no_wrap=True)
    table.add_column("原因", style="white")

    for item in registry.disabled_tools:
        table.add_row(item.get("name", "-"), item.get("module", "-"), item.get("reason", "-"))

    console.print()
    console.print(table)


def _render_module_errors_table(registry) -> None:
    if not registry.module_errors:
        return
    table = Table(
        title="[bold red]模块加载错误[/bold red]",
        show_header=True,
        header_style="bold red",
        border_style="red",
        row_styles=["", "dim"],
    )
    table.add_column("模块", style="yellow", width=36)
    table.add_column("错误", style="white")

    for item in registry.module_errors:
        table.add_row(item.get("module", "-"), item.get("error", "-"))

    console.print()
    console.print(table)


def show_tools_list(force_reload: bool = False) -> None:
    """显示工具注册中心状态。"""
    registry = get_tool_registry(force_reload=force_reload)
    config_mode = "自动发现" if registry.config.auto_discover else "手动模块清单"
    console.print()
    console.print(f"[bold cyan]工具注册中心[/bold cyan]  模式: [white]{config_mode}[/white]")
    console.print(f"[dim]配置文件: {registry.config_path}[/dim]")
    console.print(f"[dim]扫描模块数: {len(registry.modules_scanned)} | 启用工具数: {len(registry.enabled_tools)}[/dim]")

    if registry.enabled_tools:
        console.print()
        _render_enabled_tools_table(registry)
    else:
        console.print("\n[yellow]当前没有可用工具。请检查 tools/ 目录和 config/tools.yaml。[/yellow]")

    _render_disabled_tools_table(registry)
    _render_module_errors_table(registry)
    console.print()
