"""模型信息显示：显示当前所有模型配置。"""

from __future__ import annotations

import yaml

from cli.display import console
from utils.path import get_config_path


def show_models_list() -> None:
    """
    显示所有模型配置信息
    """
    # 加载模型配置
    config_path = get_config_path("model.yaml")
    if not config_path.exists():
        console.print("[red]错误: 模型配置文件不存在[/red]")
        return
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        console.print(f"[red]错误: 无法读取模型配置文件: {str(e)}[/red]")
        return
    
    # 模型用途说明
    model_descriptions = {
        "main": "主流程模型：作为 ReAct Agent 的底座",
        "text_generation": "文本生成模型：用于文本生成任务",
        "element_extraction": "元素提取模型：用于从文本中提取结构化信息",
        "code_generation": "代码生成模型：用于代码生成任务",
    }
    
    # 创建表格
    from rich.table import Table
    
    table = Table(
        title="[bold cyan]模型配置列表[/bold cyan]",
        show_header=True,
        header_style="bold magenta",
        border_style="cyan",
        row_styles=["", "dim"]
    )
    
    table.add_column("模型名称", style="cyan", width=15, no_wrap=True)
    table.add_column("用途", style="white", width=40, no_wrap=True)
    table.add_column("Provider", style="yellow", width=15, no_wrap=True)
    table.add_column("Model", style="green", width=20, no_wrap=True)
    table.add_column("API Key 环境变量", style="dim", width=20, no_wrap=True)
    
    # 添加模型信息（含 main / text_generation / element_extraction / code_generation 等，与 config/model.yaml 一致）
    for model_name in ["main", "text_generation", "element_extraction", "code_generation"]:
        if model_name in config:
            model_config = config[model_name]
            provider = model_config.get("provider", "N/A")
            model = model_config.get("model", "N/A")
            api_key_env = model_config.get("api_key_env", "N/A")
            description = model_descriptions.get(model_name, "未知用途")
            
            table.add_row(
                model_name,
                description,
                provider,
                model,
                api_key_env
            )
    
    console.print()
    console.print(table)
    console.print()
