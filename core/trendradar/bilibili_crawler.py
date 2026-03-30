"""
B站 Up主内容爬虫
支持 RSS、API、网页爬取三种模式
"""

import re
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import json

class BilibiliCrawler:
    """B站爬虫"""
    
    def __init__(self, mode: str = "crawler"):
        """
        初始化爬虫
        mode: "rss" | "api" | "crawler"
        """
        self.mode = mode
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
    
    def get_up_info(self, uid: str) -> Optional[Dict[str, Any]]:
        """获取 Up主信息"""
        try:
            if self.mode == "api":
                return self._get_up_info_api(uid)
            elif self.mode == "rss":
                return self._get_up_info_rss(uid)
            else:
                return self._get_up_info_crawler(uid)
        except Exception as e:
            print(f"⚠️ 获取 Up主信息失败: {e}")
            return None
    
    def _get_up_info_api(self, uid: str) -> Optional[Dict[str, Any]]:
        """通过 API 获取 Up主信息"""
        # B站 API 需要认证，这里使用简化实现
        url = f"https://api.bilibili.com/x/space/acc/info?mid={uid}"
        response = self.session.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get("code") == 0:
                info = data.get("data", {})
                return {
                    "uid": uid,
                    "name": info.get("name", ""),
                    "avatar": info.get("face", ""),
                    "description": info.get("sign", ""),
                    "follower_count": info.get("fans", 0)
                }
        return None
    
    def _get_up_info_rss(self, uid: str) -> Optional[Dict[str, Any]]:
        """通过 RSS 获取 Up主信息"""
        # B站 RSS: https://space.bilibili.com/{uid}/video
        # 需要解析 RSS feed
        rss_url = f"https://space.bilibili.com/{uid}/video"
        # 简化实现，实际需要解析 RSS XML
        return {
            "uid": uid,
            "name": f"Up主_{uid}",
            "avatar": "",
            "description": "",
            "follower_count": 0
        }
    
    def _get_up_info_crawler(self, uid: str) -> Optional[Dict[str, Any]]:
        """通过网页爬取获取 Up主信息"""
        url = f"https://space.bilibili.com/{uid}"
        response = self.session.get(url)
        if response.status_code == 200:
            # 解析 HTML 提取信息（简化实现）
            html = response.text
            # 实际需要解析 HTML，提取 name, avatar, description 等
            return {
                "uid": uid,
                "name": f"Up主_{uid}",
                "avatar": "",
                "description": "",
                "follower_count": 0
            }
        return None
    
    def get_videos(self, uid: str, max_count: int = 50) -> List[Dict[str, Any]]:
        """获取 Up主的视频列表"""
        try:
            if self.mode == "api":
                return self._get_videos_api(uid, max_count)
            elif self.mode == "rss":
                return self._get_videos_rss(uid, max_count)
            else:
                return self._get_videos_crawler(uid, max_count)
        except Exception as e:
            print(f"⚠️ 获取视频列表失败: {e}")
            return []
    
    def _get_videos_api(self, uid: str, max_count: int) -> List[Dict[str, Any]]:
        """通过 API 获取视频列表"""
        videos = []
        page = 1
        page_size = 20
        
        while len(videos) < max_count:
            url = f"https://api.bilibili.com/x/space/wbi/arc/search?mid={uid}&ps={page_size}&pn={page}"
            response = self.session.get(url)
            
            if response.status_code != 200:
                break
            
            data = response.json()
            if data.get("code") != 0:
                break
            
            vlist = data.get("data", {}).get("list", {}).get("vlist", [])
            if not vlist:
                break
            
            for v in vlist:
                videos.append({
                    "bvid": v.get("bvid", ""),
                    "title": v.get("title", ""),
                    "description": v.get("description", ""),
                    "up_uid": uid,
                    "publish_time": datetime.fromtimestamp(v.get("created", 0)),
                    "view_count": v.get("play", 0),
                    "like_count": v.get("video_review", 0),
                    "comment_count": v.get("comment", 0),
                    "tags": [],
                    "duration": v.get("length", ""),
                    "cover_url": v.get("pic", "")
                })
            
            if len(vlist) < page_size:
                break
            
            page += 1
        
        return videos[:max_count]
    
    def _get_videos_rss(self, uid: str, max_count: int) -> List[Dict[str, Any]]:
        """通过 RSS 获取视频列表"""
        # 简化实现，实际需要解析 RSS XML
        return []
    
    def _get_videos_crawler(self, uid: str, max_count: int) -> List[Dict[str, Any]]:
        """通过网页爬取获取视频列表"""
        # 简化实现，实际需要解析 HTML
        return []



