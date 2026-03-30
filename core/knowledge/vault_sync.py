"""
sanhu_vault 同步管理器
负责协调索引、监控、写入等功能
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import hashlib
import asyncio

from core.knowledge.vault_indexer import VaultIndexer
from core.knowledge.vault_watcher import VaultWatcher
from core.knowledge.vault_writer import VaultWriter

class VaultSyncManager:
    """Vault 同步管理器"""
    
    def __init__(self, config_path: str = "unified_config.yaml"):
        """初始化同步管理器"""
        self.config = self._load_config(config_path)
        vault_config = self.config.get("vault", {})
        
        self.vault_path = Path(vault_config.get("path", "/Users/biaowenhuang/Documents/sanhu_vault"))
        self.watch_enabled = vault_config.get("watch_enabled", True)
        self.sync_interval = vault_config.get("sync_interval", 60)
        
        # 初始化组件
        self.indexer = VaultIndexer(self.vault_path)
        self.writer = VaultWriter(self.vault_path)
        self.watcher = None
        
        # 同步状态
        self._syncing = False
        self._last_sync: Optional[datetime] = None
        self._file_count = 0
        
        # 启动文件监控
        if self.watch_enabled:
            self._start_watcher()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return {}
    
    def _start_watcher(self):
        """启动文件监控"""
        try:
            self.watcher = VaultWatcher(
                self.vault_path,
                on_change=self._on_file_change
            )
            self.watcher.start()
        except Exception as e:
            print(f"⚠️ 文件监控启动失败: {e}")
    
    def _on_file_change(self, event_type: str, file_path: Path):
        """文件变更回调"""
        # 防抖处理：延迟执行索引更新
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self._debounced_index(file_path))
        except RuntimeError:
            # 如果没有事件循环，创建新的
            asyncio.run(self._debounced_index(file_path))
    
    async def _debounced_index(self, file_path: Path, delay: float = 0.5):
        """防抖索引更新"""
        await asyncio.sleep(delay)
        try:
            if file_path.suffix == '.md':
                self.indexer.index_file(file_path)
        except Exception as e:
            print(f"⚠️ 索引更新失败: {e}")
    
    async def full_sync(self) -> Dict[str, Any]:
        """执行全量同步"""
        if self._syncing:
            return {"status": "already_syncing"}
        
        self._syncing = True
        try:
            # 索引所有文件
            files = self.indexer.index_all()
            self._file_count = len(files)
            self._last_sync = datetime.now()
            
            return {
                "status": "success",
                "file_count": self._file_count,
                "timestamp": self._last_sync.isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }
        finally:
            self._syncing = False
    
    def get_status(self) -> Dict[str, Any]:
        """获取同步状态"""
        return {
            "syncing": self._syncing,
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
            "file_count": self._file_count
        }
    
    def list_files(self) -> List[Dict[str, Any]]:
        """列出所有已索引文件"""
        return self.indexer.list_files()
    
    def get_note(self, note_id: str) -> Optional[Dict[str, Any]]:
        """获取笔记内容"""
        return self.indexer.get_note(note_id)
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """搜索笔记"""
        return self.indexer.search(query)
    
    def close(self):
        """关闭同步管理器"""
        if self.watcher:
            self.watcher.stop()

