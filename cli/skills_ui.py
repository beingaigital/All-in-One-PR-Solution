"""Skills Layer 可视化。"""

from __future__ import annotations

from rich.table import Table

from cli.display import console
from utils.skill_registry import (
    format_active_skills_for_prompt,
    get_active_skills_for_query,
    get_skill_registry,
)


def show_skills_status(force_reload: bool = False, query: str | None = None) -> None:
    """显示技能注册与激活状态。"""
    registry = get_skill_registry(force_reload=force_reload)
    cfg = registry.config

    console.print()
    console.print("[bold cyan]Skills Layer[/bold cyan]")
    console.print(f"[dim]配置文件: {registry.config_path}[/dim]")
    console.print(
        "[dim]"
        f"enabled={cfg.enabled} | auto_activate={cfg.auto_activate} | "
        f"max_active_skills={cfg.max_active_skills} | max_total_chars={cfg.max_total_chars}"
        "[/dim]"
    )

    table = Table(
        show_header=True,
        header_style="bold magenta",
        border_style="cyan",
        row_styles=["", "dim"],
    )
    table.add_column("Skill", style="cyan", width=18, no_wrap=True)
    table.add_column("Status", style="white", width=10, no_wrap=True)
    table.add_column("Priority", style="yellow", width=8, no_wrap=True)
    table.add_column("Source", style="green", width=10, no_wrap=True)
    table.add_column("Keywords", style="white", width=30)
    table.add_column("Summary", style="white")

    for sid in sorted(registry.skills.keys()):
        skill = registry.skills[sid]
        status = "enabled" if (skill.enabled and not skill.error) else "disabled"
        kws = ", ".join(skill.keywords[:6]) if skill.keywords else "-"
        summary = skill.summary
        if skill.error:
            summary = f"error: {skill.error}"
        table.add_row(
            sid,
            status,
            str(skill.priority),
            skill.source,
            kws,
            summary,
        )

    console.print()
    console.print(table)

    if query:
        active = get_active_skills_for_query(query, force_reload=force_reload)
        console.print()
        if not active:
            console.print(f"[yellow]query '{query}' 没有匹配到激活技能[/yellow]")
        else:
            names = ", ".join(s.skill_id for s in active)
            console.print(f"[green]query '{query}' 激活技能: {names}[/green]")
            preview = format_active_skills_for_prompt(query, force_reload=force_reload)
            if preview:
                console.print("[dim]已生成技能上下文片段（用于本轮 prompt 注入）[/dim]")

    if registry.load_errors:
        err_table = Table(
            title="[bold red]Skills 加载错误[/bold red]",
            show_header=True,
            header_style="bold red",
            border_style="red",
        )
        err_table.add_column("Skill", style="yellow")
        err_table.add_column("File", style="white")
        err_table.add_column("Error", style="white")
        for item in registry.load_errors:
            err_table.add_row(
                item.get("skill_id", "-"),
                item.get("file", "-"),
                item.get("error", "-"),
            )
        console.print()
        console.print(err_table)

    console.print()
