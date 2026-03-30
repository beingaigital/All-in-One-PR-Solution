"""
sanhu_vault 索引器
负责索引 Markdown 文件到 Neo4j 和向量数据库
"""

import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
try:
    import frontmatter
except ImportError:
    # 如果没有 frontmatter，使用简化实现
    frontmatter = None

from core.common.pr_neo4j_env import graph

class VaultIndexer:
    """Vault 索引器"""
    
    def __init__(self, vault_path: Path):
        """初始化索引器"""
        self.vault_path = Path(vault_path)
        self._index_cache: Dict[str, Dict[str, Any]] = {}
    
    def _get_note_id(self, file_path: Path) -> str:
        """生成笔记ID（基于文件路径的hash）"""
        rel_path = str(file_path.relative_to(self.vault_path))
        return hashlib.md5(rel_path.encode()).hexdigest()
    
    def _extract_frontmatter(self, content: str) -> tuple[Dict[str, Any], str]:
        """提取 frontmatter"""
        if frontmatter:
            try:
                post = frontmatter.loads(content)
                return dict(post.metadata), post.content
            except:
                return {}, content
        else:
            # 简化实现：如果没有 frontmatter 库，直接返回空元数据
            return {}, content
    
    def _extract_links(self, content: str) -> List[str]:
        """提取内部链接（Obsidian 格式：[[链接]]）"""
        pattern = r'\[\[([^\]]+)\]\]'
        return re.findall(pattern, content)
    
    def index_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """索引单个文件"""
        if not file_path.exists() or file_path.suffix != '.md':
            return None
        
        try:
            # 读取文件内容
            content = file_path.read_text(encoding='utf-8')
            
            # 提取元数据
            metadata, body = self._extract_frontmatter(content)
            links = self._extract_links(content)
            
            # 构建笔记对象
            note_id = self._get_note_id(file_path)
            rel_path = str(file_path.relative_to(self.vault_path))
            title = metadata.get('title') or file_path.stem
            tags = metadata.get('tags', [])
            if isinstance(tags, str):
                tags = [tags]
            
            note = {
                "id": note_id,
                "title": title,
                "path": rel_path,
                "content": content,
                "tags": tags,
                "created_at": datetime.fromtimestamp(file_path.stat().st_ctime),
                "updated_at": datetime.fromtimestamp(file_path.stat().st_mtime),
                "word_count": len(body.split()),
                "links": links
            }
            
            # 更新缓存
            self._index_cache[note_id] = note
            
            # 写入 Neo4j（如果连接可用）
            if graph:
                self._index_to_neo4j(note)
            
            return note
        except Exception as e:
            print(f"⚠️ 索引文件失败 {file_path}: {e}")
            return None
    
    def _index_to_neo4j(self, note: Dict[str, Any]):
        """索引到 Neo4j"""
        try:
            # 创建或更新 VaultNote 节点
            query = """
            MERGE (n:VaultNote {id: $id})
            SET n.title = $title,
                n.path = $path,
                n.content = $content,
                n.tags = $tags,
                n.word_count = $word_count,
                n.updated_at = $updated_at
            RETURN n
            """
            
            graph.query(query, {
                "id": note["id"],
                "title": note["title"],
                "path": note["path"],
                "content": note["content"],
                "tags": note["tags"],
                "word_count": note["word_count"],
                "updated_at": note["updated_at"].isoformat()
            })
        except Exception as e:
            print(f"⚠️ Neo4j 索引失败: {e}")
    
    def index_all(self) -> List[Dict[str, Any]]:
        """索引所有 Markdown 文件"""
        notes = []
        for md_file in self.vault_path.rglob("*.md"):
            note = self.index_file(md_file)
            if note:
                notes.append(note)
        return notes
    
    def list_files(self) -> List[Dict[str, Any]]:
        """列出所有已索引文件（简化版，仅返回基本信息）"""
        files = []
        for note_id, note in self._index_cache.items():
            files.append({
                "id": note_id,
                "title": note["title"],
                "path": note["path"],
                "updated_at": note["updated_at"].isoformat()
            })
        return files
    
    def get_note(self, note_id: str) -> Optional[Dict[str, Any]]:
        """获取笔记内容"""
        return self._index_cache.get(note_id)
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """搜索笔记（简单文本匹配）"""
        results = []
        query_lower = query.lower()
        
        for note in self._index_cache.values():
            # 在标题、内容、标签中搜索
            if (query_lower in note["title"].lower() or
                query_lower in note["content"].lower() or
                any(query_lower in tag.lower() for tag in note["tags"])):
                results.append(note)
        
        return results

