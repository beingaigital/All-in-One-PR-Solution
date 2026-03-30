#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公关/营销知识图谱分类Schema
定义一级/二级分类结构
"""

# 完整的分类结构（一级/二级）
CATEGORY_SCHEMA = {
    "brand_info": {
        "label": "品牌信息",
        "sub_categories": {
            "brand_positioning": {
                "label": "品牌定位",
                "keywords": ["定位", "市场定位", "品牌定位", "定位策略", "Positioning", "目标市场"]
            },
            "brand_vision_mission": {
                "label": "品牌愿景与使命",
                "keywords": ["愿景", "使命", "Mission", "Vision", "品牌愿景", "品牌使命", "价值主张", "品牌理念"]
            },
            "brand_tone_values": {
                "label": "品牌调性与价值观",
                "keywords": ["调性", "价值观", "品牌价值", "品牌文化", "品牌个性", "品牌精神", "Tone", "Values"]
            },
            "brand_assets_identity": {
                "label": "品牌资产与形象",
                "keywords": ["品牌形象", "品牌资产", "Brand Identity", "VI", "视觉识别", "Logo", "品牌符号", "超级符号", "IP"]
            },
            "brand_challenges": {
                "label": "品牌挑战与痛点",
                "keywords": ["挑战", "痛点", "问题", "困境", "瓶颈", "危机", "品牌面临", "品牌现状"]
            },
            "brand_general": {
                "label": "品牌综合",
                "keywords": ["品牌", "Brand", "Branding", "品牌建设", "品牌传播", "品牌力", "品牌升级", "品牌焕新"]
            }
        }
    },

    "strategy": {
        "label": "传播策略",
        "sub_categories": {
            "strategic_objectives": {
                "label": "战略目标",
                "keywords": ["目标", "战略目标", "核心目标", "业务目标", "传播目标", "Objectives", "Goal", "KPI设定"]
            },
            "market_positioning": {
                "label": "市场定位",
                "keywords": ["市场定位", "市场策略", "细分市场", "目标市场", "Market Positioning"]
            },
            "communication_strategy": {
                "label": "品牌传播策略",
                "keywords": ["传播策略", "传播思路", "传播路径", "传播主线", "整合传播", "IMC", "Communication Strategy"]
            },
            "content_strategy": {
                "label": "内容策略",
                "keywords": ["内容策略", "内容规划", "内容主线", "Content Strategy", "内容框架"]
            },
            "channel_strategy": {
                "label": "渠道策略",
                "keywords": ["渠道策略", "渠道布局", "渠道规划", "Channel Strategy", "渠道矩阵"]
            },
            "media_strategy": {
                "label": "媒介策略",
                "keywords": ["媒介策略", "媒体策略", "Media Strategy", "媒介投放", "媒介组合", "Media Mix"]
            },
            "big_idea": {
                "label": "创意理念",
                "keywords": ["Big Idea", "创意主张", "核心概念", "创意策略", "主题", "Concept", "核心主张"]
            },
            "strategy_general": {
                "label": "策略综合",
                "keywords": ["策略", "Strategy", "战略", "规划", "策略思考", "策略框架", "策略逻辑"]
            }
        }
    },

    "ecommerce": {
        "label": "电商运营",
        "sub_categories": {
            "platform_strategy": {
                "label": "平台布局",
                "keywords": ["天猫", "京东", "抖音商城", "小红书", "拼多多", "电商平台", "旗舰店", "平台布局"]
            },
            "sales_strategy": {
                "label": "销售策略",
                "keywords": ["销售", "销量", "GMV", "成交", "转化", "客单价", "销售策略", "定价", "促销"]
            },
            "live_streaming": {
                "label": "直播与短视频",
                "keywords": ["直播", "直播带货", "直播间", "主播", "李佳琦", "薇娅", "罗永浩", "直播销售", "带货", "种草直播"]
            },
            "conversion": {
                "label": "用户转化",
                "keywords": ["转化", "转化率", "转化链路", "购买路径", "下单", "订单", "支付", "成交转化"]
            },
            "after_sales": {
                "label": "售后与客服",
                "keywords": ["售后", "客服", "退换货", "服务", "售后服务", "客户服务", "7天无理由"]
            },
            "ecommerce_promotion": {
                "label": "电商大促",
                "keywords": ["双十一", "双11", "双十二", "双12", "618", "大促", "购物节", "狂欢节", "秒杀", "限时抢购"]
            },
            "ecommerce_general": {
                "label": "电商综合",
                "keywords": ["电商", "新零售", "E-commerce", "电商运营", "店铺运营", "商城", "O2O", "线上", "电商推广"]
            }
        }
    },

    "content_marketing": {
        "label": "内容营销",
        "sub_categories": {
            "content_matrix": {
                "label": "内容矩阵",
                "keywords": ["内容矩阵", "内容规划", "内容布局", "内容体系", "Content Matrix"]
            },
            "distribution_channels": {
                "label": "渠道分发",
                "keywords": ["分发", "发布", "投放", "渠道", "多平台", "全渠道", "Distribution"]
            },
            "kol_influencer": {
                "label": "KOL与达人",
                "keywords": ["KOL", "KOC", "达人", "网红", "博主", "Influencer", "种草", "带货达人"]
            },
            "ip_campaign": {
                "label": "IP与话题",
                "keywords": ["IP", "话题", "热点", "话题营销", "IP联动", "话题传播", "Trending", "Hashtag"]
            },
            "short_video_content": {
                "label": "短视频内容",
                "keywords": ["短视频", "视频号", "抖音", "快手", "B站", "视频内容", "Vlog"]
            },
            "creative_tone": {
                "label": "内容创意与调性",
                "keywords": ["创意", "文案", "素材", "调性", "风格", "Creative", "内容创意", "创意内容"]
            },
            "content_general": {
                "label": "内容综合",
                "keywords": ["内容", "Content", "内容营销", "内容策略", "内容创作", "内容生产", "Social", "社交媒体"]
            }
        }
    },

    "campaign": {
        "label": "活动执行",
        "sub_categories": {
            "campaign_overview": {
                "label": "活动概述",
                "keywords": ["活动概述", "活动背景", "活动简介", "Campaign Overview"]
            },
            "campaign_objectives": {
                "label": "活动目标",
                "keywords": ["活动目标", "Campaign Goal", "活动效果", "预期目标"]
            },
            "campaign_format": {
                "label": "活动形式",
                "keywords": ["活动形式", "线下活动", "线上活动", "发布会", "路演", "快闪", "体验", "试驾", "沙龙"]
            },
            "campaign_theme": {
                "label": "活动主题",
                "keywords": ["活动主题", "主题", "Theme", "创意主题", "主题设计"]
            },
            "campaign_timeline": {
                "label": "活动节点与节奏",
                "keywords": ["节点", "节奏", "时间", "排期", "Timeline", "活动时间", "传播节奏", "执行节奏"]
            },
            "campaign_execution": {
                "label": "活动执行细节",
                "keywords": ["执行", "落地", "实施", "执行方案", "执行细节", "Execution", "落地方案"]
            },
            "communication_flow": {
                "label": "传播机制",
                "keywords": ["传播", "传播路径", "传播矩阵", "传播机制", "分发", "推广", "扩散"]
            },
            "campaign_kpi": {
                "label": "活动KPI",
                "keywords": ["KPI", "指标", "测评", "评估", "Metrics", "衡量标准"]
            },
            "campaign_general": {
                "label": "活动综合",
                "keywords": ["活动", "Campaign", "事件", "Event", "营销活动", "品牌活动"]
            }
        }
    },

    "membership": {
        "label": "会员运营",
        "sub_categories": {
            "membership_system": {
                "label": "会员体系",
                "keywords": ["会员体系", "会员系统", "会员架构", "Membership System", "会员制度"]
            },
            "points_system": {
                "label": "积分体系",
                "keywords": ["积分", "积分体系", "积分规则", "Points", "成长值", "积分商城"]
            },
            "user_growth": {
                "label": "用户成长机制",
                "keywords": ["用户成长", "成长体系", "等级", "会员等级", "升级", "成长路径"]
            },
            "crm_platform": {
                "label": "CRM系统",
                "keywords": ["CRM", "客户关系", "用户管理", "Customer Relationship", "数据管理"]
            },
            "benefits_incentives": {
                "label": "会员权益与激励",
                "keywords": ["权益", "福利", "激励", "奖励", "Benefits", "会员权益", "专属", "特权"]
            },
            "community_club": {
                "label": "社群与俱乐部",
                "keywords": ["社群", "俱乐部", "社区", "Community", "粉丝", "Club", "车友会"]
            },
            "membership_general": {
                "label": "会员综合",
                "keywords": ["会员", "Membership", "忠诚度", "留存", "复购", "裂变", "老带新"]
            }
        }
    },

    "data_insights": {
        "label": "数据洞察",
        "sub_categories": {
            "user_data": {
                "label": "用户数据分析",
                "keywords": ["用户数据", "用户画像", "用户行为", "User Data", "行为数据", "消费数据"]
            },
            "purchase_path": {
                "label": "购买路径分析",
                "keywords": ["购买路径", "转化漏斗", "用户旅程", "Customer Journey", "转化路径", "漏斗"]
            },
            "media_data": {
                "label": "投放数据分析",
                "keywords": ["投放数据", "媒介数据", "曝光", "点击", "CTR", "CPM", "CPC", "投放效果"]
            },
            "competitor_data": {
                "label": "竞品数据对比",
                "keywords": ["竞品数据", "对比数据", "市场数据", "行业数据", "Benchmark Data"]
            },
            "performance_analysis": {
                "label": "效果分析",
                "keywords": ["效果分析", "Performance", "数据分析", "ROI分析", "效果评估"]
            },
            "data_general": {
                "label": "数据综合",
                "keywords": ["数据", "Data", "Analytics", "分析", "洞察", "Insight", "DMP", "数据驱动", "BI"]
            }
        }
    },

    "competitor_analysis": {
        "label": "竞品分析",
        "sub_categories": {
            "competitor_brands": {
                "label": "竞品品牌",
                "keywords": ["宝马", "奔驰", "奥迪", "特斯拉", "蔚来", "理想", "小鹏", "比亚迪", "BMW", "Mercedes", "Tesla"]
            },
            "competitor_strategy": {
                "label": "竞品策略",
                "keywords": ["竞品策略", "竞争策略", "Competitor Strategy", "对手策略"]
            },
            "competitor_campaign": {
                "label": "竞品活动",
                "keywords": ["竞品活动", "对手活动", "竞品案例", "Competitor Campaign"]
            },
            "competitive_comparison": {
                "label": "竞品对比",
                "keywords": ["对比", "对标", "Benchmark", "比较", "SWOT", "差异化", "优劣势"]
            },
            "competitor_general": {
                "label": "竞品综合",
                "keywords": ["竞品", "竞争", "Competitor", "竞争对手", "竞争分析", "市场格局", "竞争格局"]
            }
        }
    },

    "case_study": {
        "label": "案例研究",
        "sub_categories": {
            "brand_cases": {
                "label": "品牌案例",
                "keywords": ["品牌案例", "Brand Case", "品牌实践", "品牌样本"]
            },
            "channel_cases": {
                "label": "渠道案例",
                "keywords": ["渠道案例", "平台案例", "Channel Case"]
            },
            "campaign_cases": {
                "label": "活动案例",
                "keywords": ["活动案例", "Campaign Case", "营销案例", "传播案例"]
            },
            "data_results": {
                "label": "数据表现",
                "keywords": ["数据表现", "效果数据", "Results", "成果数据"]
            },
            "success_factors": {
                "label": "成功要素",
                "keywords": ["成功要素", "关键因素", "Success Factor", "成功经验", "启示"]
            },
            "case_general": {
                "label": "案例综合",
                "keywords": ["案例", "Case", "案例分析", "实践", "最佳实践", "Best Practice", "经典", "标杆"]
            }
        }
    },

    "audience": {
        "label": "受众分析",
        "sub_categories": {
            "audience_profile": {
                "label": "受众画像",
                "keywords": ["受众画像", "用户画像", "人群画像", "Persona", "画像", "Profile"]
            },
            "behavior_preferences": {
                "label": "行为偏好",
                "keywords": ["行为", "偏好", "习惯", "喜好", "Behavior", "Preference", "消费习惯"]
            },
            "audience_segmentation": {
                "label": "受众细分",
                "keywords": ["细分", "人群细分", "Segmentation", "分层", "圈层"]
            },
            "psychological_insight": {
                "label": "心理洞察",
                "keywords": ["心理", "洞察", "需求", "痛点", "诉求", "Insight", "心智"]
            },
            "demographic": {
                "label": "人口统计属性",
                "keywords": ["年龄", "性别", "地域", "城市", "Z世代", "90后", "95后", "Demographic"]
            },
            "audience_general": {
                "label": "受众综合",
                "keywords": ["受众", "人群", "目标人群", "TA", "Target", "用户", "消费者", "客户"]
            }
        }
    },

    "execution": {
        "label": "执行落地",
        "sub_categories": {
            "execution_process": {
                "label": "执行流程",
                "keywords": ["执行流程", "实施流程", "操作流程", "Process", "流程"]
            },
            "execution_platform": {
                "label": "落地平台",
                "keywords": ["落地平台", "执行平台", "实施平台", "Platform"]
            },
            "execution_team": {
                "label": "执行团队",
                "keywords": ["团队", "人员", "分工", "Team", "协作", "组织架构"]
            },
            "timeline": {
                "label": "时间节点",
                "keywords": ["时间", "节点", "排期", "Timeline", "时间表", "进度", "里程碑"]
            },
            "resources": {
                "label": "资源分配",
                "keywords": ["资源", "预算", "Budget", "费用", "资源分配", "投入"]
            },
            "risk_management": {
                "label": "风险与应急",
                "keywords": ["风险", "应急", "Risk", "预案", "风险管理", "应对措施"]
            },
            "execution_general": {
                "label": "执行综合",
                "keywords": ["执行", "落地", "实施", "Execution", "推进", "执行方案", "实施方案"]
            }
        }
    },

    "results": {
        "label": "结果评估",
        "sub_categories": {
            "kpi_metrics": {
                "label": "KPI指标",
                "keywords": ["KPI", "指标", "Metrics", "关键指标", "核心指标"]
            },
            "results_summary": {
                "label": "成果总结",
                "keywords": ["成果", "结果", "成绩", "Results", "达成", "完成情况"]
            },
            "data_performance": {
                "label": "数据表现",
                "keywords": ["数据表现", "数据结果", "Performance", "表现", "数据成果"]
            },
            "user_feedback": {
                "label": "用户反馈",
                "keywords": ["反馈", "Feedback", "用户反馈", "评价", "口碑"]
            },
            "brand_lift": {
                "label": "品牌提升",
                "keywords": ["品牌提升", "Brand Lift", "认知提升", "影响力提升"]
            },
            "results_general": {
                "label": "效果综合",
                "keywords": ["效果", "成效", "复盘", "评估", "ROI", "转化", "曝光", "增长"]
            }
        }
    },

    "summary": {
        "label": "总结展望",
        "sub_categories": {
            "project_summary": {
                "label": "项目总结",
                "keywords": ["项目总结", "总结", "小结", "Summary", "回顾"]
            },
            "key_conclusion": {
                "label": "核心结论",
                "keywords": ["结论", "核心", "Conclusion", "关键", "要点", "亮点"]
            },
            "future_outlook": {
                "label": "未来展望",
                "keywords": ["展望", "未来", "下一步", "规划", "Outlook", "Future", "建议", "方向"]
            }
        }
    }
}


def get_all_categories():
    """获取所有分类信息"""
    return CATEGORY_SCHEMA


def get_category_l1_list():
    """获取所有一级分类"""
    return list(CATEGORY_SCHEMA.keys())


def get_category_l2_list():
    """获取所有二级分类（带code）"""
    l2_list = []
    for l1_code, l1_data in CATEGORY_SCHEMA.items():
        for l2_code, l2_data in l1_data['sub_categories'].items():
            l2_list.append({
                'code': f"{l1_code}.{l2_code}",
                'label': l2_data['label'],
                'parent_code': l1_code,
                'keywords': l2_data['keywords']
            })
    return l2_list


def classify_section(title: str = "", content: str = "") -> tuple:
    """
    根据标题和内容分类到CategoryL2
    返回: (level1_code, level2_code, level2_label)
    """
    combined_text = (title + " " + content).lower()

    best_match_l1 = None
    best_match_l2 = None
    best_match_label = None
    best_score = 0

    for l1_code, l1_data in CATEGORY_SCHEMA.items():
        for l2_code, l2_data in l1_data['sub_categories'].items():
            keywords = l2_data['keywords']
            score = 0

            # 计算匹配分数
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in title.lower():
                    score += 3  # 标题匹配权重更高
                elif keyword_lower in combined_text:
                    score += 1

            if score > best_score:
                best_score = score
                best_match_l1 = l1_code
                best_match_l2 = f"{l1_code}.{l2_code}"
                best_match_label = l2_data['label']

    if best_score > 0:
        return (best_match_l1, best_match_l2, best_match_label)

    # 默认返回
    return ("other", "other.general", "其他")


def get_category_by_code(l2_code: str):
    """根据二级分类code获取信息"""
    if '.' not in l2_code:
        return None

    l1_code, l2_subcode = l2_code.split('.', 1)

    if l1_code in CATEGORY_SCHEMA:
        l1_data = CATEGORY_SCHEMA[l1_code]
        if l2_subcode in l1_data['sub_categories']:
            l2_data = l1_data['sub_categories'][l2_subcode]
            return {
                'l1_code': l1_code,
                'l1_label': l1_data['label'],
                'l2_code': l2_code,
                'l2_label': l2_data['label'],
                'keywords': l2_data['keywords']
            }

    return None


