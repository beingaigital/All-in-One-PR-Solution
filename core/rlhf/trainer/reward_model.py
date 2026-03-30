#!/usr/bin/env python3
"""
奖励模型定义。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

from core.rlhf.data.feedback_collector import Feedback
from .quality_evaluator import QualityAssessment


@dataclass
class RewardSignal:
    plan_id: str
    reward_score: float
    feedback_id: Optional[str]
    quality_assessment: Optional[QualityAssessment]
    timestamp: str


@dataclass
class TrainingData:
    plan_id: str
    plan_content: str
    context: Dict[str, Any]
    reward: float
    feedback: Optional[Feedback]
    quality_assessment: Optional[QualityAssessment]


class RewardModel:
    """简单的线性奖励模型。"""

    def __init__(self, model_path: Optional[str] = None) -> None:
        self.model_path = model_path
        self.weights = {
            "rating": 0.4,
            "quality": 0.3,
            "engagement": 0.2,
            "consistency": 0.1,
        }
        self.trained = False

    def predict_reward(
        self,
        plan_content: str,
        context: Dict[str, Any],
        feedback: Optional[Feedback] = None,
        quality_assessment: Optional[QualityAssessment] = None,
    ) -> float:
        reward = 0.0
        if feedback and feedback.rating is not None:
            normalized_rating = (feedback.rating - 3.0) / 2.0
            reward += normalized_rating * self.weights["rating"]

        if quality_assessment:
            normalized_quality = (quality_assessment.overall_score - 0.5) * 2.0
            reward += normalized_quality * self.weights["quality"]

        if feedback and feedback.categories:
            category_scores = {"high": 0.5, "medium": 0.0, "low": -0.5}
            for value in feedback.categories.values():
                if isinstance(value, str) and value in category_scores:
                    reward += category_scores[value] * 0.1

        if feedback and feedback.suggestions:
            reward -= len(feedback.suggestions) * 0.05

        return max(-1.0, min(1.0, reward))

    def train(self, training_data: List[TrainingData]) -> None:
        if len(training_data) < 5:
            print("训练数据不足，需要至少5条数据")
            return

        predictions = [
            self.predict_reward(data.plan_content, data.context, data.feedback, data.quality_assessment)
            for data in training_data
        ]
        errors = [abs(pred - data.reward) for pred, data in zip(predictions, training_data)]
        avg_error = float(np.mean(errors))

        if avg_error < 0.2:
            self.trained = True
            print(f"奖励模型训练完成，平均误差: {avg_error:.3f}")
        else:
            print(f"奖励模型训练中，平均误差: {avg_error:.3f}")

    def _extract_features(self, data: TrainingData) -> List[float]:
        features = [
            len(data.plan_content) / 1000.0,
            1.0 if data.context.get("brand") else 0.0,
            1.0 if data.context.get("industry") else 0.0,
            1.0 if data.context.get("pr_goal") else 0.0,
        ]

        if data.feedback:
            features.append((data.feedback.rating or 0) / 5.0)
            features.append(len(data.feedback.suggestions) / 10.0)
        else:
            features.extend([0.5, 0.0])

        features.append(data.quality_assessment.overall_score if data.quality_assessment else 0.5)
        return features

    def save_model(self, path: str) -> None:
        model_data = {"weights": self.weights, "trained": self.trained}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(model_data, fh, indent=2)

    def load_model(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as fh:
            model_data = json.load(fh)
        self.weights = model_data["weights"]
        self.trained = model_data["trained"]

