"""Profile Layer 状态展示。"""

from __future__ import annotations

from rich.table import Table

from cli.display import console
from utils.profile_loader import get_profile_context


def show_profile_status(force_reload: bool = False) -> None:
    """展示 profile 文件加载状态。"""
    ctx = get_profile_context(force_reload=force_reload)

    console.print()
    console.print("[bold cyan]Profile Layer[/bold cyan]")
    console.print(f"[dim]配置文件: {ctx.config_path}[/dim]")
    console.print(
        f"[dim]状态: {'enabled' if ctx.enabled else 'disabled'} | max_chars_per_file={ctx.max_chars_per_file}[/dim]"
    )

    table = Table(
        show_header=True,
        header_style="bold magenta",
        border_style="cyan",
        row_styles=["", "dim"],
    )
    table.add_column("Section", style="cyan", width=12, no_wrap=True)
    table.add_column("File", style="yellow", width=38)
    table.add_column("Status", style="white", width=12, no_wrap=True)
    table.add_column("Chars", style="green", width=8, no_wrap=True)
    table.add_column("Note", style="white")

    for key in ctx.section_order:
        sec = ctx.sections.get(key)
        if not sec:
            table.add_row(key, "-", "missing", "0", "未配置")
            continue

        status = "loaded" if sec.exists and not sec.error else "error"
        note = ""
        if sec.error:
            note = sec.error
        elif sec.truncated:
            note = "已截断"
        elif not sec.exists:
            status = "missing"
            note = "文件不存在"

        table.add_row(
            key,
            str(sec.file_path),
            status,
            str(len(sec.content or "")),
            note,
        )

    console.print()
    console.print(table)
    console.print()
