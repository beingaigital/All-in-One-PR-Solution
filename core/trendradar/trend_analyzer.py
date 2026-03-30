"""
趋势分析器
分析议题趋势、情感、关联关系
"""

from typing import Dict, List, Any
from datetime import datetime, timedelta
from collections import Counter

class TrendAnalyzer:
    """趋势分析器"""
    
    def analyze_trends(self, topics: List[Dict[str, Any]], period: str = "week") -> List[Dict[str, Any]]:
        """
        分析趋势
        
        period: "day" | "week" | "month"
        """
        if period == "day":
            delta = timedelta(days=1)
        elif period == "week":
            delta = timedelta(weeks=1)
        else:
            delta = timedelta(days=30)
        
        # 按时间分组
        time_groups = {}
        for topic in topics:
            publish_time = topic.get("publish_time")
            if isinstance(publish_time, str):
                publish_time = datetime.fromisoformat(publish_time)
            
            if not isinstance(publish_time, datetime):
                continue
            
            # 按时间段分组
            time_key = publish_time.strftime("%Y-%m-%d")
            if time_key not in time_groups:
                time_groups[time_key] = []
            time_groups[time_key].append(topic)
        
        # 生成趋势数据
        trends = []
        for time_key in sorted(time_groups.keys()):
            group_topics = time_groups[time_key]
            trends.append({
                "date": time_key,
                "count": len(group_topics),
                "avg_relevance": sum(t.get("relevance_score", 0) for t in group_topics) / len(group_topics),
                "avg_hot": sum(t.get("hot_score", 0) for t in group_topics) / len(group_topics),
                "top_keywords": self._extract_top_keywords(group_topics)
            })
        
        return trends
    
    def _extract_top_keywords(self, topics: List[Dict[str, Any]], top_n: int = 5) -> List[str]:
        """提取热门关键词"""
        all_tags = []
        for topic in topics:
            all_tags.extend(topic.get("tags", []))
        
        counter = Counter(all_tags)
        return [tag for tag, _ in counter.most_common(top_n)]
    
    def analyze_sentiment(self, topics: List[Dict[str, Any]]) -> Dict[str, int]:
        """情感分析（简化版）"""
        # 实际应使用情感分析模型
        return {
            "positive": 0,
            "neutral": len(topics),
            "negative": 0
        }
    
    def find_related_topics(self, topic: Dict[str, Any], all_topics: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
        """查找相关议题"""
        topic_tags = set(topic.get("tags", []))
        
        # 计算相似度（基于标签重叠）
        similarities = []
        for other in all_topics:
            if other.get("id") == topic.get("id"):
                continue
            
            other_tags = set(other.get("tags", []))
            overlap = len(topic_tags & other_tags)
            if overlap > 0:
                similarity = overlap / len(topic_tags | other_tags)
                similarities.append((similarity, other))
        
        # 按相似度排序
        similarities.sort(reverse=True, key=lambda x: x[0])
        
        return [topic for _, topic in similarities[:top_n]]



