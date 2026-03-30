"""
TrendRadar 调度器
管理定时任务、Up主列表、议题存储
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.trendradar.bilibili_crawler import BilibiliCrawler
from core.trendradar.ai_topic_filter import AITopicFilter
from core.trendradar.trend_analyzer import TrendAnalyzer

class TrendRadarScheduler:
    """TrendRadar 调度器"""
    
    def __init__(self, config_path: str = "config/trendradar.yaml"):
        """初始化调度器"""
        self.config = self._load_config(config_path)
        self.scheduler = AsyncIOScheduler()
        
        # 初始化组件
        self.crawler = BilibiliCrawler(mode="crawler")
        self.filter = AITopicFilter(keywords=self.config.get("ai_keywords", []))
        self.analyzer = TrendAnalyzer()
        
        # 数据存储（简化版，使用文件）
        self.data_dir = Path("data/trendradar")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.ups_file = self.data_dir / "ups.json"
        self.topics_file = self.data_dir / "topics.json"
        
        # 加载数据
        self.ups: Dict[str, Dict[str, Any]] = self._load_ups()
        self.topics: Dict[str, Dict[str, Any]] = self._load_topics()
        
        # 启动定时任务
        self._start_scheduler()
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件"""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        return {}
    
    def _load_ups(self) -> Dict[str, Dict[str, Any]]:
        """加载 Up主列表"""
        if self.ups_file.exists():
            with open(self.ups_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _save_ups(self):
        """保存 Up主列表"""
        with open(self.ups_file, 'w', encoding='utf-8') as f:
            json.dump(self.ups, f, ensure_ascii=False, indent=2, default=str)
    
    def _load_topics(self) -> Dict[str, Dict[str, Any]]:
        """加载议题列表"""
        if self.topics_file.exists():
            with open(self.topics_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _save_topics(self):
        """保存议题列表"""
        with open(self.topics_file, 'w', encoding='utf-8') as f:
            json.dump(self.topics, f, ensure_ascii=False, indent=2, default=str)
    
    def _start_scheduler(self):
        """启动定时任务"""
        crawl_interval = self.config.get("crawl_interval", 3600)  # 默认1小时
        
        # 为每个 Up主创建定时任务
        for uid, up_info in self.ups.items():
            if up_info.get("enabled", True):
                self.scheduler.add_job(
                    self._crawl_up,
                    trigger=IntervalTrigger(seconds=crawl_interval),
                    args=[uid],
                    id=f"crawl_{uid}",
                    replace_existing=True
                )
        
        self.scheduler.start()
    
    async def _crawl_up(self, uid: str):
        """爬取 Up主内容"""
        try:
            # 获取视频列表
            videos = self.crawler.get_videos(uid, max_count=50)
            
            # 筛选 AI 相关议题
            for video in videos:
                video["source"] = "bilibili"
                topic = self.filter.filter(video)
                
                if topic:
                    topic_id = topic["id"]
                    self.topics[topic_id] = topic
            
            # 保存议题
            self._save_topics()
        except Exception as e:
            print(f"⚠️ 爬取 Up主 {uid} 失败: {e}")
    
    def list_ups(self) -> List[Dict[str, Any]]:
        """获取 Up主列表"""
        return list(self.ups.values())
    
    def add_up(self, uid: str, name: Optional[str] = None) -> Dict[str, Any]:
        """添加 Up主"""
        # 获取 Up主信息
        up_info = self.crawler.get_up_info(uid)
        if not up_info:
            up_info = {
                "uid": uid,
                "name": name or f"Up主_{uid}",
                "avatar": "",
                "description": "",
                "follower_count": 0
            }
        
        self.ups[uid] = up_info
        self._save_ups()
        
        # 添加定时任务
        crawl_interval = self.config.get("crawl_interval", 3600)
        self.scheduler.add_job(
            self._crawl_up,
            trigger=IntervalTrigger(seconds=crawl_interval),
            args=[uid],
            id=f"crawl_{uid}",
            replace_existing=True
        )
        
        return up_info
    
    def remove_up(self, uid: str) -> bool:
        """删除 Up主"""
        if uid not in self.ups:
            return False
        
        del self.ups[uid]
        self._save_ups()
        
        # 移除定时任务
        self.scheduler.remove_job(f"crawl_{uid}")
        
        return True
    
    def list_topics(self, page: int = 1, limit: int = 20, filters: Optional[Dict] = None) -> tuple[List[Dict[str, Any]], int]:
        """获取议题列表"""
        topics_list = list(self.topics.values())
        
        # 应用筛选
        if filters:
            # 简化实现，实际应支持更多筛选条件
            pass
        
        # 排序（按发布时间倒序）
        topics_list.sort(key=lambda x: x.get("publish_time", ""), reverse=True)
        
        # 分页
        total = len(topics_list)
        start = (page - 1) * limit
        end = start + limit
        
        return topics_list[start:end], total
    
    def get_topic(self, topic_id: str) -> Optional[Dict[str, Any]]:
        """获取议题详情"""
        return self.topics.get(topic_id)
    
    def get_related_topics(self, topic_id: str, top_n: int = 5) -> List[Dict[str, Any]]:
        """获取相关议题"""
        topic = self.topics.get(topic_id)
        if not topic:
            return []
        
        all_topics = list(self.topics.values())
        return self.analyzer.find_related_topics(topic, all_topics, top_n)
    
    def get_trends(self, period: str = "week") -> List[Dict[str, Any]]:
        """获取趋势分析"""
        topics_list = list(self.topics.values())
        return self.analyzer.analyze_trends(topics_list, period)
    
    def generate_report(self) -> Dict[str, Any]:
        """生成报告"""
        topics_list = list(self.topics.values())
        
        trends = self.analyzer.analyze_trends(topics_list, "week")
        sentiment = self.analyzer.analyze_sentiment(topics_list)
        
        return {
            "generated_at": datetime.now().isoformat(),
            "total_topics": len(topics_list),
            "trends": trends,
            "sentiment": sentiment,
            "top_keywords": self.analyzer._extract_top_keywords(topics_list, 10)
        }
    
    def update_config(self, keywords: List[str], crawl_interval: int):
        """更新配置"""
        self.config["ai_keywords"] = keywords
        self.config["crawl_interval"] = crawl_interval
        
        # 更新筛选器
        self.filter = AITopicFilter(keywords=keywords)
        
        # 重启调度器
        self.scheduler.shutdown()
        self._start_scheduler()



