"""
RLHF 数据层：封装反馈与知识管理 DAO。
"""

from .feedback_collector import FeedbackCollector, Feedback, FeedbackType
from .knowledge_manager import BrandKnowledgeManager

__all__ = ["FeedbackCollector", "Feedback", "FeedbackType", "BrandKnowledgeManager"]

