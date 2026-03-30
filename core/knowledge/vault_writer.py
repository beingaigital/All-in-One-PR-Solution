"""
sanhu_vault 写入器
负责创建、更新、删除笔记文件
"""

try:
    import frontmatter
except ImportError:
    frontmatter = None
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

class VaultWriter:
    """Vault 写入器"""
    
    def __init__(self, vault_path: Path):
        """初始化写入器"""
        self.vault_path = Path(vault_path)
    
    def _ensure_directory(self, file_path: Path):
        """确保目录存在"""
        file_path.parent.mkdir(parents=True, exist_ok=True)
    
    def create_note(
        self,
        title: str,
        content: str,
        path: str,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """创建新笔记"""
        file_path = self.vault_path / path
        
        # 确保路径以 .md 结尾
        if not file_path.suffix:
            file_path = file_path.with_suffix('.md')
        
        # 确保目录存在
        self._ensure_directory(file_path)
        
        # 构建 frontmatter
        if frontmatter:
            metadata = {
                "title": title,
                "created_at": datetime.now().isoformat(),
            }
            if tags:
                metadata["tags"] = tags
            
            # 写入文件
            post = frontmatter.Post(content, **metadata)
            file_path.write_text(frontmatter.dumps(post), encoding='utf-8')
        else:
            # 简化实现：如果没有 frontmatter 库，直接写入内容
            file_path.write_text(content, encoding='utf-8')
        
        # 返回笔记对象（简化版）
        return {
            "id": self._get_note_id(file_path),
            "title": title,
            "path": str(file_path.relative_to(self.vault_path)),
            "content": content,
            "tags": tags or [],
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "word_count": len(content.split()),
            "links": []
        }
    
    def _get_note_id(self, file_path: Path) -> str:
        """生成笔记ID"""
        import hashlib
        rel_path = str(file_path.relative_to(self.vault_path))
        return hashlib.md5(rel_path.encode()).hexdigest()
    
    def update_note(self, note_id: str, content: str) -> Optional[Dict[str, Any]]:
        """更新笔记"""
        # 简化版：需要通过索引器查找文件路径
        # 实际实现中应该维护 note_id -> file_path 的映射
        # 这里返回 None 表示需要先通过索引器获取文件路径
        return None
    
    def update_note_by_path(self, path: str, content: str) -> Optional[Dict[str, Any]]:
        """通过路径更新笔记"""
        file_path = self.vault_path / path
        
        if not file_path.exists():
            return None
        
        try:
            if frontmatter:
                # 读取现有 frontmatter
                post = frontmatter.load(file_path)
                
                # 更新内容
                post.content = content
                post.metadata["updated_at"] = datetime.now().isoformat()
                
                # 写入文件
                file_path.write_text(frontmatter.dumps(post), encoding='utf-8')
            else:
                # 简化实现：直接写入内容
                file_path.write_text(content, encoding='utf-8')
            
            # 返回更新后的笔记对象（简化版）
            if frontmatter:
                title = post.metadata.get("title", file_path.stem)
                tags = post.metadata.get("tags", [])
            else:
                title = file_path.stem
                tags = []
            
            return {
                "id": self._get_note_id(file_path),
                "title": title,
                "path": str(file_path.relative_to(self.vault_path)),
                "content": content,
                "tags": tags,
                "updated_at": datetime.now(),
                "word_count": len(content.split())
            }
        except Exception as e:
            print(f"⚠️ 更新笔记失败: {e}")
            return None
    
    def delete_note(self, note_id: str) -> bool:
        """删除笔记"""
        # 简化版：需要通过索引器查找文件路径
        # 实际实现中应该维护 note_id -> file_path 的映射
        return False
    
    def delete_note_by_path(self, path: str) -> bool:
        """通过路径删除笔记"""
        file_path = self.vault_path / path
        
        if not file_path.exists():
            return False
        
        try:
            file_path.unlink()
            return True
        except Exception as e:
            print(f"⚠️ 删除笔记失败: {e}")
            return False

