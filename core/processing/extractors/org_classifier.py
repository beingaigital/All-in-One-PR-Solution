#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
组织实体分类器 Cursor Write It-qcf ;
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set
from enum import Enum


DEFAULT_LIST_DIR = Path("data") / "list"
DEFAULT_LIST_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_LIST_FILES = {
    "ORG_COMPANY_WHITELIST": DEFAULT_LIST_DIR / "company_whitelist.txt",
    "ORG_BRAND_WHITELIST": DEFAULT_LIST_DIR / "brand_whitelist.txt",
    "ORG_COMPANY_BLACKLIST": DEFAULT_LIST_DIR / "company_blacklist.txt",
    "ORG_BRAND_BLACKLIST": DEFAULT_LIST_DIR / "brand_blacklist.txt",
}


class EntityType(Enum):
    """实体类型枚举 Cursor Write It-qcf ;"""
    BRAND = "brand"
    COMPANY = "company"
    COMPANY_TYPE = "company_type"
    UNKNOWN = "unknown"


class OrganizationClassifier:
    """组织实体分类器 Cursor Write It-qcf ;"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化分类器 Cursor Write It-qcf ;"""
        self.config = config or {}

        # 置信度阈值（可通过环境变量覆盖）
        self.company_confidence_threshold = float(
            self.config.get("company_confidence_min")
            or os.getenv("ORG_COMPANY_CONF_MIN", "0.6")
        )
        self.brand_confidence_threshold = float(
            self.config.get("brand_confidence_min")
            or os.getenv("ORG_BRAND_CONF_MIN", "0.65")  # 提高阈值：0.45 -> 0.65
        )

        # 名单（支持 env 变量/文件配置）
        self.company_whitelist = self._load_name_list("ORG_COMPANY_WHITELIST")
        self.brand_whitelist = self._load_name_list("ORG_BRAND_WHITELIST")
        self.company_blacklist = self._load_name_list(
            "ORG_COMPANY_BLACKLIST",
            defaults={"内容营销", "案例", "策略", "方案", "方法论"},
        )
        self.brand_blacklist = self._load_name_list(
            "ORG_BRAND_BLACKLIST",
            defaults={"内容营销", "案例库", "营销策略", "方法论", "研究报告"},
        )
        # 公司后缀关键词
        self.company_suffixes = [
            '公司', '集团', '有限公司', '股份有限公司', '有限责任公司',
            '企业', '工厂', '分公司', '子公司', '运营公司', '运营主体',
            '官方', '官方旗舰店', '旗舰店', '品牌方',
            'Co.', 'Ltd.', 'Inc.', 'Corp.', 'Corporation',
            'Limited', 'Company', 'Group', 'Enterprises'
        ]

        # 品牌特征关键词（出现在特定语境中）
        self.brand_keywords = [
            '品牌', '品牌形象', '母品牌', '品牌集团', '品牌系列',
            '主品牌', '子品牌', '品牌资产', '品牌调性', '品牌定位',
            '品牌价值', '品牌理念', '品牌故事', '品牌传播', '品牌营销',
            '品牌升级', '品牌重塑', '品牌建设', '品牌战略', '品牌管理'
        ]
        
        # 非品牌通用词（如果实体名包含这些，更可能是通用概念而非品牌）
        self.non_brand_generic_words = {
            '平台', '系统', '工具', '方案', '策略', '方法', '模式', '流程',
            '服务', '产品', '技术', '应用', '软件', '硬件', '设备',
            '报告', '研究', '分析', '洞察', '趋势', '观察', '总结',
            '案例', '案例库', '指南', '手册', '白皮书', '方法论',
            '营销', '传播', '推广', '运营', '增长', '投放', '内容',
            '数据', '信息', '知识', '经验', '实践', '理论', '框架',
            '行业', '市场', '用户', '客户', '消费者', '受众', '人群',
            '活动', '项目', '计划', '规划', '目标', '指标', 'KPI',
            '渠道', '媒体', '社交', '电商', '零售', '销售', '交易',
            '体验', '服务', '支持', '帮助', '解决', '优化', '提升'
        }

        # 行业类别定义（CompanyType）
        self.industry_types = {
            # 美妆护肤
            'beauty_cosmetics': {
                'label': '美妆品牌',
                'keywords': ['美妆', '化妆品', '护肤', '彩妆', '香水', '香氛',
                           'Beauty', 'Cosmetics', 'Skincare', 'Makeup', 'Perfume',
                           '欧莱雅', '兰蔻', '雅诗兰黛', 'SK-II', '资生堂',
                           'Dior', 'Chanel', 'MAC', 'YSL', 'Armani']
            },
            # 快消品
            'fmcg': {
                'label': '快消品牌',
                'keywords': ['快消', '日化', '消费品', 'FMCG', 'Consumer Goods',
                           '宝洁', '联合利华', '可口可乐', '百事', '雀巢']
            },
            # 汽车
            'automotive': {
                'label': '汽车品牌',
                'keywords': ['汽车', '车企', '车', 'Auto', 'Automotive', 'Vehicle',
                           '奥迪', '宝马', '奔驰', '特斯拉', '蔚来', '理想',
                           '小鹏', '比亚迪', '一汽', '上汽', '广汽', '吉利']
            },
            # 新能源
            'new_energy': {
                'label': '新能源车企',
                'keywords': ['新能源', '电动车', '纯电', '混动', 'EV', 'New Energy',
                           'Tesla', 'NIO', '理想', '小鹏', '比亚迪']
            },
            # 互联网/科技
            'internet_tech': {
                'label': '互联网平台',
                'keywords': ['互联网', '科技', 'Tech', 'Technology', 'Internet',
                           '腾讯', '阿里', '百度', '字节', '京东', '美团',
                           '滴滴', '小红书', '抖音', '快手']
            },
            # 手机/消费电子
            'consumer_electronics': {
                'label': '消费电子',
                'keywords': ['手机', '智能', '电子', 'Consumer Electronics',
                           '苹果', '华为', '小米', 'OPPO', 'vivo', '荣耀',
                           'iPhone', 'Samsung']
            },
            # 服装时尚
            'fashion': {
                'label': '服装时尚',
                'keywords': ['服装', '时尚', 'Fashion', 'Apparel', 'Clothing',
                           'Nike', 'Adidas', '优衣库', 'ZARA', 'H&M']
            },
            # 食品饮料
            'food_beverage': {
                'label': '食品饮料',
                'keywords': ['食品', '饮料', '餐饮', 'Food', 'Beverage',
                           '可口可乐', '百事', '星巴克', '麦当劳', '肯德基']
            },
            # 金融
            'finance': {
                'label': '金融',
                'keywords': ['银行', '金融', 'Finance', 'Banking', 'Insurance']
            },
            # 教育
            'education': {
                'label': '教育',
                'keywords': ['教育', 'Education', '培训', '在线教育']
            },
            # 家电
            'home_appliances': {
                'label': '家电',
                'keywords': ['家电', '电器', 'Home Appliances',
                           '海尔', '美的', '格力', 'TCL']
            },
            # 出行/文旅
            'travel': {
                'label': '出行文旅',
                'keywords': ['旅游', '出行', '文旅', 'Travel', 'Tourism']
            }
        }

        # 品牌名称模式（纯品牌名，无后缀）
        self.brand_name_pattern = re.compile(r'^[\w\u4e00-\u9fff]+$')

    def classify_entity(
        self,
        name: str,
        context: Optional[str] = None,
        category_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        分类实体 Cursor Write It-qcf ;
        """
        if not name or not name.strip():
            return {
                'type': EntityType.UNKNOWN.value,
                'confidence': 0.0,
                'attributes': {},
                'industry_types': [],
                'is_whitelisted': False,
                'is_blacklisted': False,
            }

        name = name.strip()
        normalized_name = self._normalize_name(name)

        is_company_whitelisted = normalized_name in self.company_whitelist
        is_brand_whitelisted = normalized_name in self.brand_whitelist
        is_company_blacklisted = normalized_name in self.company_blacklist
        is_brand_blacklisted = normalized_name in self.brand_blacklist
        is_blacklisted = is_company_blacklisted or is_brand_blacklisted

        if is_blacklisted:
            return {
                'type': EntityType.UNKNOWN.value,
                'confidence': 0.0,
                'attributes': {'blacklisted': True},
                'industry_types': [],
                'is_whitelisted': False,
                'is_blacklisted': True,
            }

        confidence = 0.0
        entity_type = EntityType.UNKNOWN
        attributes = {}
        matched_industries = []

        # 步骤1: 检查是否为Company（包含公司后缀 / 白名单）
        is_company = False
        if is_company_whitelisted:
            is_company = True
            confidence = 1.0
            entity_type = EntityType.COMPANY
            attributes['type'] = 'company'
            attributes['verified'] = True
        else:
            for suffix in self.company_suffixes:
                if suffix in name:
                    is_company = True
                    confidence = 0.9
                    entity_type = EntityType.COMPANY
                    attributes['type'] = 'company'
                    # 提取公司名称中的品牌部分
                    brand_part = self._extract_brand_from_company(name)
                    if brand_part:
                        attributes['brand_part'] = brand_part
                    break

        # 步骤2: 检查行业类型
        industry_matches = self._match_industry_type(name, context)
        if industry_matches:
            matched_industries = industry_matches
            if not is_company:
                # 如果没有公司后缀，可能是品牌或行业类别
                confidence = 0.7

        # 步骤3: 如果未识别为Company，检查是否为Brand
        if not is_company:
            if is_brand_whitelisted:
                entity_type = EntityType.BRAND
                confidence = max(confidence, 1.0)
                attributes['type'] = 'brand'
                attributes['level'] = 'group'
                attributes['verified'] = True
            else:
                # 检查上下文中的品牌关键词
                is_brand_context = False
                if context:
                    for keyword in self.brand_keywords:
                        if keyword in context:
                            is_brand_context = True
                            break

                # 检查分类代码（brand_info等模块中的更可能是品牌）
                is_brand_category = False
                if category_code:
                    brand_categories = ['brand_info', 'brand_positioning',
                                      'brand_vision_mission', 'brand_tone_values',
                                      'brand_assets_identity']
                    if any(cat in category_code for cat in brand_categories):
                        is_brand_category = True

                # 检查是否为通用词（非品牌）
                is_generic_word = self._is_generic_non_brand_word(name)
                
                # 判断为Brand（需要满足更严格的条件）
                if is_generic_word:
                    # 如果是通用词，标记为 unknown，不创建品牌节点
                    entity_type = EntityType.UNKNOWN
                    confidence = 0.2
                    attributes['type'] = 'unknown'
                    attributes['uncertain'] = True
                    attributes['reason'] = 'generic_word'
                elif is_brand_context and is_brand_category:
                    # 同时满足上下文和分类代码，高置信度
                    entity_type = EntityType.BRAND
                    confidence = 0.9
                    attributes['type'] = 'brand'
                    attributes['level'] = 'group'
                elif is_brand_context or is_brand_category:
                    # 满足其中一个条件，中等置信度
                    entity_type = EntityType.BRAND
                    confidence = 0.75 if is_brand_context else 0.7
                    attributes['type'] = 'brand'
                    attributes['level'] = 'group'
                elif self._is_likely_brand(name, context):
                    # 通过品牌名称验证，但需要更高置信度
                    entity_type = EntityType.BRAND
                    confidence = max(confidence, 0.65)  # 提高到 0.65
                    attributes['type'] = 'brand'
                    attributes['level'] = 'group'
                    attributes['uncertain'] = confidence < 0.7  # 低于 0.7 标记为不确定
                else:
                    # 无法确定，标记为 unknown，不创建品牌节点
                    entity_type = EntityType.UNKNOWN
                    confidence = 0.3
                    attributes['type'] = 'unknown'
                    attributes['uncertain'] = True
                    attributes['reason'] = 'insufficient_evidence'

        # 步骤4: 如果匹配到行业，添加行业信息
        if matched_industries:
            attributes['industry_types'] = matched_industries

        return {
            'type': entity_type.value,
            'confidence': confidence,
            'attributes': attributes,
            'industry_types': matched_industries,
            'is_whitelisted': is_company_whitelisted or is_brand_whitelisted,
            'is_blacklisted': is_blacklisted,
        }

    def _extract_brand_from_company(self, company_name: str) -> Optional[str]:
        """从公司名称中提取品牌部分 Cursor Write It-qcf ;"""
        # 先移除括号内容
        brand_part = re.sub(r'\([^)]+\)', '', company_name).strip()

        # 移除常见后缀
        patterns = [
            r'(.+?)(?:中国|上海|北京|广州|深圳|杭州|成都|苏州|南京|武汉|西安|重庆|天津|青岛|大连|厦门|福州|合肥|长沙|郑州|济南|石家庄|哈尔滨|长春|沈阳|昆明|南宁|南昌|贵阳|太原|乌鲁木齐|银川|西宁|拉萨|呼和浩特)',
            r'(.+?)(?:有限公司|股份有限公司|有限责任公司|公司|集团|企业|工厂|运营|官方|旗舰店)',
        ]

        for pattern in patterns:
            match = re.search(pattern, brand_part)
            if match:
                brand_part = match.group(1).strip()

        # 如果提取后明显变短且有意义，返回
        if len(brand_part) < len(company_name) and len(brand_part) > 1 and len(brand_part) <= 20:
            brand_part = re.sub(r'[（）、，。]', '', brand_part).strip()
            return brand_part if brand_part else None

        return None

    def _match_industry_type(self, name: str, context: Optional[str] = None) -> List[Dict[str, Any]]:
        """匹配行业类型 Cursor Write It-qcf ;"""
        matches = []
        search_text = name.lower()
        if context:
            search_text += " " + context.lower()

        for code, industry_info in self.industry_types.items():
            for keyword in industry_info['keywords']:
                if keyword.lower() in search_text:
                    matches.append({
                        'code': code,
                        'label': industry_info['label']
                    })
                    break  # 每个行业类型只匹配一次

        return matches

    def _is_likely_brand(self, name: str, context: Optional[str] = None) -> bool:
        """判断是否可能是品牌名（增强版） Cursor Write It-qcf ;"""
        if len(name) < 2 or len(name) > 20:
            return False

        # 排除公司后缀
        for suffix in self.company_suffixes:
            if suffix in name:
                return False

        # 排除通用词
        if self._is_generic_non_brand_word(name):
            return False

        # 排除纯数字或纯符号
        if re.match(r'^[\d\s\-_\.]+$', name):
            return False

        # 排除常见的非品牌模式
        non_brand_patterns = [
            r'^第[一二三四五六七八九十\d]+[章节部分]',
            r'^[上下]?[篇章节]',
            r'^[A-Za-z]+(?:Plan|Strategy|Guide|Report|Insight|Toolkit|System|Platform|Service)$',
            r'^\d+[年月日]',
            r'^[年月日]',
        ]
        for pattern in non_brand_patterns:
            if re.match(pattern, name):
                return False

        # 基本格式验证：允许中英文、数字、常见符号
        if not re.match(r'^[\w\u4e00-\u9fff\-\s]+$', name):
            return False

        # 如果上下文明确提到品牌，增加置信度
        if context:
            context_lower = context.lower()
            brand_indicators = ['品牌', 'brand', '商标', 'trademark']
            if any(indicator in context_lower for indicator in brand_indicators):
                return True

        # 默认返回 True（但置信度会较低）
        return True

    def _is_generic_non_brand_word(self, name: str) -> bool:
        """检查是否为通用词（非品牌） Cursor Write It-qcf ;"""
        name_lower = name.lower()
        
        # 检查是否完全匹配通用词
        if name in self.non_brand_generic_words:
            return True
        
        # 检查是否以通用词结尾
        for word in self.non_brand_generic_words:
            if name.endswith(word) or name_lower.endswith(word.lower()):
                # 但如果名称长度明显大于通用词，可能是品牌+通用词组合
                if len(name) > len(word) + 2:  # 允许品牌名+通用词
                    continue
                return True
        
        # 检查是否包含多个通用词（更可能是通用概念）
        generic_count = sum(1 for word in self.non_brand_generic_words if word in name or word.lower() in name_lower)
        if generic_count >= 2:
            return True
        
        return False

    def _load_name_list(self, env_key: str, defaults: Optional[Set[str]] = None) -> Set[str]:
        """从环境变量或文件加载名单"""
        names: Set[str] = set(defaults or [])
        env_value = os.getenv(env_key)
        if env_value:
            names.update({self._normalize_name(item) for item in env_value.split(',') if item.strip()})

        file_path = os.getenv(f"{env_key}_FILE")
        if not file_path and env_key in DEFAULT_LIST_FILES:
            file_path = str(DEFAULT_LIST_FILES[env_key])

        if file_path and Path(file_path).exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            names.add(self._normalize_name(line))
            except Exception:
                pass

        config_values = self.config.get(env_key.lower())
        if isinstance(config_values, (list, set, tuple)):
            names.update({self._normalize_name(item) for item in config_values if isinstance(item, str)})

        return {name for name in names if name}

    @staticmethod
    def _normalize_name(name: Any) -> str:
        if not isinstance(name, str):
            return ""
        n = name.strip().strip('\'"“”‘’').strip()
        n = re.sub(r'\s{2,}', ' ', n)
        return n

    def get_company_type_nodes(self) -> List[Dict[str, Any]]:
        """获取所有CompanyType节点定义 Cursor Write It-qcf ;"""
        return [
            {
                'code': code,
                'label': info['label'],
                'keywords': info['keywords']
            }
            for code, info in self.industry_types.items()
        ]


def test_classifier():
    """测试分类器 Cursor Write It-qcf ;"""
    classifier = OrganizationClassifier()

    test_cases = [
        ("欧莱雅", "品牌信息", "这是一个知名品牌"),
        ("欧莱雅中国有限公司", "电商运营", "公司运营电商平台"),
        ("兰蔻", "品牌定位", "品牌定位策略"),
        ("宝洁（广州）有限公司", "内容营销", "公司执行营销活动"),
        ("奥迪", "品牌信息", None),
        ("一汽奥迪", "电商运营", None),
        ("互联网", None, None),
        ("美妆", None, None),
    ]

    print("=" * 70)
    print("组织实体分类器测试")
    print("=" * 70)

    for name, category, context in test_cases:
        result = classifier.classify_entity(name, context, category)
        print(f"\n实体: {name}")
        print(f"  类型: {result['type']}")
        print(f"  置信度: {result['confidence']:.2f}")
        print(f"  属性: {result['attributes']}")
        if result['industry_types']:
            print(f"  行业: {[ind['label'] for ind in result['industry_types']]}")


if __name__ == "__main__":
    test_classifier()

