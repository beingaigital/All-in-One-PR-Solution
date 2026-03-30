"""
sanhu_vault 文件监控器
使用 watchdog 监控文件系统变更
"""

from pathlib import Path
from typing import Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

class VaultWatcher(FileSystemEventHandler):
    """Vault 文件监控器"""
    
    def __init__(self, vault_path: Path, on_change: Optional[Callable] = None):
        """初始化监控器"""
        self.vault_path = Path(vault_path)
        self.on_change = on_change
        self.observer = Observer()
    
    def on_created(self, event: FileSystemEvent):
        """文件创建事件"""
        if not event.is_directory and event.src_path.endswith('.md'):
            self._trigger_change('created', Path(event.src_path))
    
    def on_modified(self, event: FileSystemEvent):
        """文件修改事件"""
        if not event.is_directory and event.src_path.endswith('.md'):
            self._trigger_change('modified', Path(event.src_path))
    
    def on_deleted(self, event: FileSystemEvent):
        """文件删除事件"""
        if not event.is_directory and event.src_path.endswith('.md'):
            self._trigger_change('deleted', Path(event.src_path))
    
    def on_moved(self, event: FileSystemEvent):
        """文件移动事件"""
        if not event.is_directory:
            if event.src_path.endswith('.md'):
                self._trigger_change('moved', Path(event.src_path))
            if event.dest_path.endswith('.md'):
                self._trigger_change('created', Path(event.dest_path))
    
    def _trigger_change(self, event_type: str, file_path: Path):
        """触发变更回调"""
        if self.on_change:
            try:
                self.on_change(event_type, file_path)
            except Exception as e:
                print(f"⚠️ 文件变更回调失败: {e}")
    
    def start(self):
        """启动监控"""
        self.observer.schedule(self, str(self.vault_path), recursive=True)
        self.observer.start()
    
    def stop(self):
        """停止监控"""
        self.observer.stop()
        self.observer.join()



