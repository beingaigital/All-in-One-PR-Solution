#!/usr/bin/env python3
"""
增强的RAG系统 - 整合品牌知识、方法论规则和RLHF
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from core.querying.pipelines import EnhancedPRRAGSystemV11
from core.rlhf.data import BrandKnowledgeManager, FeedbackCollector
from core.rlhf.policies import MethodologyRulesManager, MethodologyRule
from core.rlhf.trainer import QualityEvaluator, RLHFTrainer, RewardModel
from core.knowledge.reference_loader import ReferenceSources


class EnhancedPRRAGWithRLHF:
    """整合RLHF的增强RAG系统"""
    
    def __init__(self):
        """初始化增强RAG系统"""
        # 基础RAG组件（使用 v1.1 系统）
        self.rag_system = EnhancedPRRAGSystemV11()
        
        # 品牌知识和方法论规则
        self.brand_manager = BrandKnowledgeManager()
        self.rules_manager = MethodologyRulesManager()
        
        # 反馈和评估
        self.feedback_collector = FeedbackCollector()
        self.quality_evaluator = QualityEvaluator()
        
        # RLHF
        self.reward_model = RewardModel()
        self.rlhf_trainer = RLHFTrainer(
            self.feedback_collector,
            self.quality_evaluator,
            self.reward_model
        )
        # 参考文件（方法论 + 案例库）
        self.reference_sources = ReferenceSources()
        self.methodology_text = self.reference_sources.methodology_text()
    
    def query_with_brand_knowledge(
        self,
        question: str,
        brand_name: Optional[str] = None,
        use_graph: bool = True
    ) -> str:
        """使用品牌知识进行查询"""
        # 如果指定了品牌，先获取品牌知识
        brand_context = ""
        brand_info: Dict[str, Any] = {}
        if brand_name:
            brand = self.brand_manager.get_brand(brand_name)
            if brand:
                brand_info = brand.get('brand', {}) or {}
                brand_context = f"""
品牌信息:
- 名称: {brand_info.get('name', '')}
- 行业: {brand_info.get('industry', '')}
- 定位: {brand_info.get('brand_positioning', '')}
- 个性: {brand_info.get('brand_personality', '')}
- 目标受众: {brand_info.get('target_audience', '')}
"""
        
        # 获取适用规则
        context_dict = {
            'brand': brand_name,
            'industry': brand_info.get('industry', '') if brand_info else None
        }
        applicable_rules = self.rules_manager.get_applicable_rules(context_dict)
        
        # 解决规则冲突
        resolved_rules = self.rules_manager.resolve_rule_conflicts(applicable_rules)
        
        # 构建增强的查询
        enhanced_question = question
        if brand_context:
            enhanced_question = f"{brand_context}\n\n问题: {question}"
        
        # 方法论片段
        methodology_hint = self.methodology_text[:1200] if self.methodology_text else ""
        if methodology_hint:
            enhanced_question = f"{enhanced_question}\n\n方法论提示:\n{methodology_hint}"
        
        # 执行RAG查询（使用 v1.1 系统）
        answer = self.rag_system.query(enhanced_question, use_graph=use_graph)
        
        # 应用规则增强答案
        if resolved_rules:
            rules_context = "\n\n应用的方法论规则:\n"
            for rule in resolved_rules[:3]:  # 只显示前3个规则
                rules_context += f"- {rule.name}: {rule.description}\n"
            answer += rules_context
        
        return answer
    
    def generate_plan_with_feedback(
        self,
        enterprise_info: Dict[str, Any],
        output_types: List[str] = None
    ) -> Dict[str, Any]:
        """生成方案并收集反馈"""
        if output_types is None:
            output_types = ["A", "B", "C", "D", "E", "F"]
        
        # 获取品牌知识
        brand_name = enterprise_info.get('enterprise_name', '')
        brand_knowledge = ""
        if brand_name:
            brand = self.brand_manager.get_brand(brand_name)
            if brand:
                brand_info = brand['brand']
                brand_knowledge = json.dumps(brand_info, ensure_ascii=False)
        
        # 获取适用规则
        context = {
            'brand': brand_name,
            'industry': enterprise_info.get('industry', ''),
            'pr_goal': enterprise_info.get('pr_goal', ''),
            'scenario': 'plan_generation'
        }
        applicable_rules = self.rules_manager.get_applicable_rules(context)
        resolved_rules = self.rules_manager.resolve_rule_conflicts(applicable_rules)
        
        # 生成方案（这里需要调用实际的生成逻辑）
        # 为了演示，这里返回模拟结果
        results = {}
        plan_ids = []
        knowledge_sources = []
        
        for plan_type in output_types:
            plan_id = f"plan_{datetime.now().strftime('%Y%m%d%H%M%S')}_{plan_type}"
            plan_ids.append(plan_id)
            
            # 记录使用的知识来源
            sources = []
            if brand_knowledge:
                sources.append(f"brand_knowledge:{brand_name}")
            for rule in resolved_rules:
                sources.append(f"methodology_rule:{rule.rule_id}")
            knowledge_sources.extend(sources)
            
            # 生成方案内容（实际应该调用LLM）
            results[plan_type] = {
                'plan_id': plan_id,
                'content': f"生成的{plan_type}类型方案，结合方法论与品牌知识。",
                'knowledge_sources': sources,
                'applied_rules': [rule.name for rule in resolved_rules]
            }

        # 自动质量评估
        quality_assessments = {}
        for plan_type, plan_data in results.items():
            assessment = self.quality_evaluator.evaluate_plan(
                plan_id=plan_data['plan_id'],
                plan_content=plan_data['content'],
                context=context
            )
            quality_assessments[plan_type] = assessment
            results[plan_type]['quality_score'] = assessment.overall_score
            results[plan_type]['improvements'] = assessment.improvements
        
        return {
            'results': results,
            'quality_assessments': quality_assessments,
            'applied_rules': [rule.name for rule in resolved_rules],
            'brand_knowledge_used': brand_name if brand_knowledge else None
        }
    
    def collect_feedback_for_plan(
        self,
        plan_id: str,
        rating: float,
        comment: Optional[str] = None,
        categories: Optional[Dict[str, Any]] = None,
        suggestions: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        knowledge_sources: Optional[List[str]] = None,
        plan_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """收集方案反馈"""
        result = self.feedback_collector.collect_feedback(
            plan_id=plan_id,
            feedback_type='rating',
            rating=rating,
            comment=comment,
            categories=categories,
            suggestions=suggestions,
            user_id=user_id,
            knowledge_sources=knowledge_sources,
            plan_type=plan_type
        )
        
        # 如果收集到足够的反馈，触发训练
        feedback_count = len(self.feedback_collector.get_feedback_by_plan(plan_id))
        if feedback_count >= 5:
            # 触发RLHF训练
            self._trigger_rlhf_training()
        
        return result
    
    def _trigger_rlhf_training(self):
        """触发RLHF训练"""
        print("触发RLHF训练...")
        training_data = self.rlhf_trainer.prepare_training_data(min_feedback_count=5)
        if len(training_data) >= 5:
            self.rlhf_trainer.train_reward_model(training_data)
            print("RLHF训练完成")
        else:
            print(f"训练数据不足: {len(training_data)}/5")
    
    def get_feedback_analysis(self, plan_id: Optional[str] = None) -> Dict[str, Any]:
        """获取反馈分析"""
        return self.feedback_collector.analyze_feedback(plan_id=plan_id)
    
    def optimize_retrieval_with_feedback(self, query: str, brand_name: Optional[str] = None) -> str:
        """基于反馈优化检索"""
        # 获取历史反馈数据
        feedback_analysis = self.get_feedback_analysis()
        
        # 根据反馈调整检索策略
        # 优先使用获得高评分的知识来源
        if feedback_analysis and 'categories_distribution' in feedback_analysis:
            # 这里可以根据反馈调整检索权重
            pass
        
        # 执行查询并附带方法论提示
        return self.query_with_brand_knowledge(query, brand_name)
    
    def get_learning_progress(self) -> Dict[str, Any]:
        """获取学习进度"""
        training_stats = self.rlhf_trainer.get_training_stats()
        feedback_analysis = self.feedback_collector.analyze_feedback()
        
        return {
            'training_stats': training_stats,
            'feedback_stats': feedback_analysis,
            'model_trained': self.reward_model.trained
        }


def test_enhanced_rag_with_rlhf():
    """测试增强RAG系统"""
    system = EnhancedPRRAGWithRLHF()
    
    # 测试查询
    print("测试品牌知识查询...")
    answer = system.query_with_brand_knowledge(
        "如何提升品牌认知度？",
        brand_name="测试品牌"
    )
    print(f"答案: {answer[:200]}...")
    
    # 测试方案生成
    print("\n测试方案生成...")
    enterprise_info = {
        'enterprise_name': '测试品牌',
        'industry': '科技',
        'pr_goal': '品牌认知',
        'market_type': 'ToC'
    }
    results = system.generate_plan_with_feedback(enterprise_info, ["A", "B"])
    print(f"生成结果: {results}")
    
    # 测试反馈收集
    print("\n测试反馈收集...")
    if results['results']:
        plan_id = list(results['results'].values())[0]['plan_id']
        feedback_result = system.collect_feedback_for_plan(
            plan_id=plan_id,
            rating=4.5,
            comment="很好的方案",
            plan_type="A"
        )
        print(f"反馈结果: {feedback_result}")


if __name__ == "__main__":
    test_enhanced_rag_with_rlhf()

