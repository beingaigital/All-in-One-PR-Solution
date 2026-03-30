"""
AI议题智能筛选器
从爬取的内容中筛选与 AI/大模型相关的议题
"""

from typing import Dict, List, Optional
from datetime import datetime

class AITopicFilter:
    """AI议题筛选器"""
    
    def __init__(self, keywords: Optional[List[str]] = None):
        """初始化筛选器"""
        self.keywords = keywords or [
            "AI", "人工智能", "大模型", "LLM", "GPT", "Claude", "Gemini",
            "AGI", "机器学习", "深度学习", "神经网络", "Transformer"
        ]
        # 转换为小写用于匹配
        self.keywords_lower = [k.lower() for k in self.keywords]
    
    def filter(self, content: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        筛选内容，返回 AI 议题对象或 None
        
        content: 包含 title, description, tags 等字段的字典
        """
        title = content.get("title", "").lower()
        description = content.get("description", "").lower()
        tags = [t.lower() for t in content.get("tags", [])]
        
        # 关键词匹配
        relevance_score = self._calculate_relevance(title, description, tags)
        
        if relevance_score < 0.3:  # 阈值可配置
            return None
        
        # 计算热度分数
        hot_score = self._calculate_hot_score(content)
        
        # 生成摘要（简化版，实际应使用 LLM）
        summary = self._generate_summary(content)
        
        return {
            "id": content.get("bvid") or content.get("id", ""),
            "title": content.get("title", ""),
            "source": content.get("source", "bilibili"),
            "source_id": content.get("bvid") or content.get("id", ""),
            "relevance_score": relevance_score,
            "hot_score": hot_score,
            "publish_time": content.get("publish_time", datetime.now()),
            "summary": summary,
            "tags": content.get("tags", [])
        }
    
    def _calculate_relevance(self, title: str, description: str, tags: List[str]) -> float:
        """计算相关性分数（0-1）"""
        score = 0.0
        total_weight = 0.0
        
        # 标题匹配（权重 0.5）
        title_matches = sum(1 for kw in self.keywords_lower if kw in title)
        if title_matches > 0:
            score += 0.5 * min(title_matches / 2, 1.0)  # 最多匹配2个关键词
        total_weight += 0.5
        
        # 描述匹配（权重 0.3）
        desc_matches = sum(1 for kw in self.keywords_lower if kw in description)
        if desc_matches > 0:
            score += 0.3 * min(desc_matches / 3, 1.0)
        total_weight += 0.3
        
        # 标签匹配（权重 0.2）
        tag_matches = sum(1 for tag in tags for kw in self.keywords_lower if kw in tag)
        if tag_matches > 0:
            score += 0.2 * min(tag_matches / 2, 1.0)
        total_weight += 0.2
        
        return score / total_weight if total_weight > 0 else 0.0
    
    def _calculate_hot_score(self, content: Dict[str, Any]) -> float:
        """计算热度分数（0-1）"""
        view_count = content.get("view_count", 0)
        like_count = content.get("like_count", 0)
        comment_count = content.get("comment_count", 0)
        
        # 归一化处理（简化版）
        # 实际应根据历史数据动态调整阈值
        view_score = min(view_count / 100000, 1.0)  # 10万播放量 = 1.0
        like_score = min(like_count / 10000, 1.0)  # 1万点赞 = 1.0
        comment_score = min(comment_count / 1000, 1.0)  # 1千评论 = 1.0
        
        # 加权平均
        hot_score = (view_score * 0.5 + like_score * 0.3 + comment_score * 0.2)
        return hot_score
    
    def _generate_summary(self, content: Dict[str, Any]) -> str:
        """生成摘要（简化版，实际应使用 LLM）"""
        title = content.get("title", "")
        description = content.get("description", "")
        
        # 简化实现：返回描述的前200字符
        if description:
            return description[:200] + "..." if len(description) > 200 else description
        return title



