#!/usr/bin/env python3
"""
反馈收集系统
收集用户对生成方案的反馈和评分
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class FeedbackType(Enum):
    """反馈类型"""

    RATING = "rating"  # 评分
    COMMENT = "comment"  # 评论
    SUGGESTION = "suggestion"  # 建议
    STRUCTURED = "structured"  # 结构化反馈


@dataclass
class Feedback:
    """反馈数据类"""

    feedback_id: str
    plan_id: str
    user_id: Optional[str]
    feedback_type: str
    rating: Optional[float]  # 1-5分
    comment: Optional[str]
    categories: Dict[str, Any]  # 分类反馈
    suggestions: List[str]  # 改进建议
    metadata: Dict[str, Any]  # 元数据
    timestamp: str
    knowledge_sources: List[str]  # 使用的知识来源
    plan_type: str  # 方案类型 (A, B, C, D, E, F)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FeedbackCollector:
    """反馈收集器"""

    def __init__(self, db_path: str = "./data/feedback.db") -> None:
        """初始化反馈收集器"""
        self.db_path = db_path
        self._init_database()

    def _init_database(self) -> None:
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id TEXT PRIMARY KEY,
            plan_id TEXT NOT NULL,
            user_id TEXT,
            feedback_type TEXT NOT NULL,
            rating REAL,
            comment TEXT,
            categories TEXT,
            suggestions TEXT,
            metadata TEXT,
            timestamp TEXT NOT NULL,
            knowledge_sources TEXT,
            plan_type TEXT
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS feedback_analysis (
            analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
            feedback_id TEXT NOT NULL,
            analysis_type TEXT NOT NULL,
            analysis_result TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (feedback_id) REFERENCES feedback(feedback_id)
        )
        """
        )

        conn.commit()
        conn.close()

    def collect_feedback(
        self,
        plan_id: str,
        feedback_type: str,
        rating: Optional[float] = None,
        comment: Optional[str] = None,
        categories: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        knowledge_sources: Optional[List[str]] = None,
        plan_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """收集反馈"""
        feedback_id = f"feedback_{datetime.now().strftime('%Y%m%d%H%M%S')}_{plan_id}"

        feedback = Feedback(
            feedback_id=feedback_id,
            plan_id=plan_id,
            user_id=user_id,
            feedback_type=feedback_type,
            rating=rating,
            comment=comment,
            categories=categories or {},
            suggestions=suggestions or [],
            metadata=metadata or {},
            timestamp=datetime.now().isoformat(),
            knowledge_sources=knowledge_sources or [],
            plan_type=plan_type or "",
        )

        self._save_feedback(feedback)

        return {
            "feedback_id": feedback_id,
            "status": "success",
            "message": "反馈已收集",
        }

    def _save_feedback(self, feedback: Feedback) -> None:
        """保存反馈到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
        INSERT INTO feedback (
            feedback_id, plan_id, user_id, feedback_type, rating, comment,
            categories, suggestions, metadata, timestamp, knowledge_sources, plan_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                feedback.feedback_id,
                feedback.plan_id,
                feedback.user_id,
                feedback.feedback_type,
                feedback.rating,
                feedback.comment,
                json.dumps(feedback.categories, ensure_ascii=False),
                json.dumps(feedback.suggestions, ensure_ascii=False),
                json.dumps(feedback.metadata, ensure_ascii=False),
                feedback.timestamp,
                json.dumps(feedback.knowledge_sources, ensure_ascii=False),
                feedback.plan_type,
            ),
        )

        conn.commit()
        conn.close()

    def get_feedback(self, feedback_id: str) -> Optional[Feedback]:
        """获取反馈"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
        SELECT * FROM feedback WHERE feedback_id = ?
        """,
            (feedback_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_feedback(row)
        return None

    def get_feedback_by_plan(self, plan_id: str) -> List[Feedback]:
        """获取方案的所有反馈"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
        SELECT * FROM feedback WHERE plan_id = ? ORDER BY timestamp DESC
        """,
            (plan_id,),
        )

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_feedback(row) for row in rows]

    def _row_to_feedback(self, row: tuple) -> Feedback:
        """将数据库行转换为Feedback对象"""
        return Feedback(
            feedback_id=row[0],
            plan_id=row[1],
            user_id=row[2],
            feedback_type=row[3],
            rating=row[4],
            comment=row[5],
            categories=json.loads(row[6]) if row[6] else {},
            suggestions=json.loads(row[7]) if row[7] else [],
            metadata=json.loads(row[8]) if row[8] else {},
            timestamp=row[9],
            knowledge_sources=json.loads(row[10]) if row[10] else [],
            plan_type=row[11],
        )

    def analyze_feedback(self, feedback_id: Optional[str] = None, plan_id: Optional[str] = None) -> Dict[str, Any]:
        """分析反馈数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if feedback_id:
            cursor.execute("SELECT * FROM feedback WHERE feedback_id = ?", (feedback_id,))
            feedbacks = [cursor.fetchone()]
        elif plan_id:
            cursor.execute("SELECT * FROM feedback WHERE plan_id = ?", (plan_id,))
            feedbacks = cursor.fetchall()
        else:
            cursor.execute("SELECT * FROM feedback")
            feedbacks = cursor.fetchall()

        conn.close()

        if not feedbacks:
            return {"error": "未找到反馈数据"}

        total_count = len(feedbacks)
        ratings = [f[4] for f in feedbacks if f[4] is not None]
        avg_rating = sum(ratings) / len(ratings) if ratings else 0

        categories_count: Dict[str, Dict[str, int]] = {}
        for feedback in feedbacks:
            categories = json.loads(feedback[6]) if feedback[6] else {}
            for key, value in categories.items():
                categories_count.setdefault(key, {})
                categories_count[key].setdefault(value, 0)
                categories_count[key][value] += 1

        all_suggestions = []
        for feedback in feedbacks:
            suggestions = json.loads(feedback[7]) if feedback[7] else []
            all_suggestions.extend(suggestions)

        return {
            "total_count": total_count,
            "average_rating": avg_rating,
            "rating_distribution": self._count_ratings(ratings),
            "categories_distribution": categories_count,
            "common_suggestions": self._get_common_items(all_suggestions, top_n=10),
            "feedback_timeline": self._get_feedback_timeline(feedbacks),
        }

    def _count_ratings(self, ratings: List[float]) -> Dict[str, int]:
        """统计评分分布"""
        distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
        for rating in ratings:
            rating_int = int(rating)
            if 1 <= rating_int <= 5:
                distribution[str(rating_int)] += 1
        return distribution

    def _get_common_items(self, items: List[str], top_n: int = 10) -> List[Dict[str, Any]]:
        """获取最常见的项目"""
        from collections import Counter

        counter = Counter(items)
        return [{"item": item, "count": count} for item, count in counter.most_common(top_n)]

    def _get_feedback_timeline(self, feedbacks: List[tuple]) -> List[Dict[str, Any]]:
        """获取反馈时间线"""
        timeline = []
        for feedback in feedbacks:
            timeline.append(
                {
                    "timestamp": feedback[9],
                    "rating": feedback[4],
                    "feedback_type": feedback[3],
                }
            )
        return sorted(timeline, key=lambda x: x["timestamp"])

    def export_feedback(self, output_path: str, format: str = "json") -> bool:
        """导出反馈数据"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM feedback")
        rows = cursor.fetchall()
        conn.close()

        feedbacks = [self._row_to_feedback(row).to_dict() for row in rows]

        try:
            if format == "json":
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(feedbacks, f, ensure_ascii=False, indent=2)
            else:
                return False
            return True
        except Exception as exc:  # pragma: no cover - IO 错误
            print(f"导出反馈失败: {exc}")
            return False

