#!/usr/bin/env python3
"""
功能清单注册器工具，提供统一的功能元数据读取能力 Cursor Write It-qcf ;
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURE_FILE = PROJECT_ROOT / "config" / "features.yaml"


class FeatureRegistry:
    """功能元数据的加载与检索工具 Cursor Write It-qcf ;"""

    def __init__(
        self,
        features: List[Dict[str, Any]],
        feature_file: Optional[Path] = None,
    ) -> None:
        """初始化功能注册器并构建索引 Cursor Write It-qcf ;"""
        self.features = features
        self.feature_file = feature_file or FEATURE_FILE
        self._index = {item["id"]: item for item in features}

    @classmethod
    def load(cls, feature_file: Optional[Path] = None) -> "FeatureRegistry":
        """从 YAML 文件加载功能元数据 Cursor Write It-qcf ;"""
        file_path = feature_file or FEATURE_FILE
        if not file_path.exists():
            raise FileNotFoundError(f"未找到功能配置文件: {file_path}")
        with file_path.open("r", encoding="utf-8") as fh:
            features = yaml.safe_load(fh) or []
        return cls(features, file_path)

    def list(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """按分类列出功能列表 Cursor Write It-qcf ;"""
        if not category:
            return self.features
        return [item for item in self.features if item.get("category") == category]

    def get(self, feature_id: str) -> Dict[str, Any]:
        """根据ID获取功能定义 Cursor Write It-qcf ;"""
        if feature_id not in self._index:
            raise KeyError(f"未找到功能: {feature_id}")
        return self._index[feature_id]

    def get_entry(self, feature_id: str) -> str:
        """获取功能对应的执行命令 Cursor Write It-qcf ;"""
        feature = self.get(feature_id)
        entry = feature.get("entry")
        if not entry:
            raise ValueError(f"功能 {feature_id} 未配置 entry")
        return entry

    def exists(self, feature_id: str) -> bool:
        """判断功能是否存在 Cursor Write It-qcf ;"""
        return feature_id in self._index


