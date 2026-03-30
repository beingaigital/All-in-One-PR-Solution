#!/usr/bin/env python3
"""
RLHF 训练主循环。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.rlhf.data.feedback_collector import Feedback, FeedbackCollector
from .quality_evaluator import QualityAssessment, QualityEvaluator
from .reward_model import RewardModel, TrainingData


class RLHFTrainer:
    """负责准备训练数据、训练奖励模型并输出统计信息。"""

    def __init__(
        self,
        feedback_collector: FeedbackCollector,
        quality_evaluator: QualityEvaluator,
        reward_model: Optional[RewardModel] = None,
    ) -> None:
        self.feedback_collector = feedback_collector
        self.quality_evaluator = quality_evaluator
        self.reward_model = reward_model or RewardModel()
        self.training_history: List[Dict[str, Any]] = []

    def prepare_training_data(
        self,
        min_feedback_count: int = 5,
        plan_content_storage: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[TrainingData]:
        conn = sqlite3.connect(self.feedback_collector.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT * FROM feedback
            WHERE rating IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1000
            """
        )
        rows = cursor.fetchall()
        conn.close()

        if len(rows) < min_feedback_count:
            return []

        training_data: List[TrainingData] = []
        for row in rows:
            try:
                feedback = self.feedback_collector._row_to_feedback(row)
                plan_content = ""
                context: Dict[str, Any] = {}
                if plan_content_storage and feedback.plan_id in plan_content_storage:
                    storage = plan_content_storage[feedback.plan_id]
                    plan_content = storage.get("content", "")
                    context = storage.get("context", {})

                quality_assessment: Optional[QualityAssessment] = None
                if plan_content:
                    quality_assessment = self.quality_evaluator.evaluate_plan(
                        plan_id=feedback.plan_id,
                        plan_content=plan_content,
                        context=context,
                    )

                reward = self.reward_model.predict_reward(
                    plan_content=plan_content,
                    context=context,
                    feedback=feedback,
                    quality_assessment=quality_assessment,
                )

                training_data.append(
                    TrainingData(
                        plan_id=feedback.plan_id,
                        plan_content=plan_content,
                        context=context,
                        reward=reward,
                        feedback=feedback,
                        quality_assessment=quality_assessment,
                    )
                )
            except Exception as exc:  # pragma: no cover - 容错
                print(f"处理训练数据失败: {exc}")
                continue

        return training_data

    def train_reward_model(self, training_data: Optional[List[TrainingData]] = None) -> bool:
        training_data = training_data or self.prepare_training_data()
        if len(training_data) < 5:
            print("训练数据不足，无法训练奖励模型")
            return False

        print(f"开始训练奖励模型，训练数据量: {len(training_data)}")
        self.reward_model.train(training_data)
        self.training_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "training_data_count": len(training_data),
                "model_trained": self.reward_model.trained,
            }
        )
        return True

    def get_training_stats(self) -> Dict[str, Any]:
        return {
            "training_history": self.training_history,
            "model_trained": self.reward_model.trained,
            "total_training_runs": len(self.training_history),
        }

