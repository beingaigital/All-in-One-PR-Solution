import os
from langchain_community.graphs import Neo4jGraph

# Warning control
import warnings

warnings.filterwarnings("ignore")

"""
说明：
- 这里改为“直接在代码中配置 Neo4j 连接信息”，不再依赖 .env 文件的自动加载。
- 仍然允许通过真正的环境变量进行覆盖（例如在终端里 export NEO4J_URI=...），方便在不同环境部署。
- 请将下方 DEFAULT_* 常量改成你的本地或云端数据库信息，注意不要提交到公共仓库。
"""

# >>>>>>>>>>>>>>> 在这里填入你的真实 Neo4j 信息（示例占位，务必手动修改） <<<<<<<<<<<<<<
DEFAULT_NEO4J_URI = "neo4j://127.0.0.1:7687"
DEFAULT_NEO4J_USERNAME = "neo4j"
DEFAULT_NEO4J_PASSWORD = "12345678"
DEFAULT_NEO4J_DATABASE = "neo4j"

# 若设置了系统环境变量，则优先使用环境变量；否则退回到上面的默认常量
NEO4J_URI = os.getenv("NEO4J_URI", DEFAULT_NEO4J_URI)
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", DEFAULT_NEO4J_USERNAME)
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD)
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", DEFAULT_NEO4J_DATABASE)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ENDPOINT = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1") + "/embeddings"

# 公关传播RAG配置参数（v1.1 新结构）
PR_NODE_TYPES = {
    'CategoryL1': '一级分类节点',
    'CategoryL2': '二级分类节点',
    'Section': '内容分段节点',
    'Company': '公司实体节点',
    'Brand': '品牌实体节点',
    'CompanyType': '组织类型节点',
    'Campaign': '传播活动节点',
    'Concept': '概念/主题节点'
}

PR_RELATIONSHIPS = {
    'HAS_SUBCATEGORY': '一级分类包含二级分类',
    'HAS_SECTION': '二级分类包含内容分段',
    'MENTIONS_COMPANY': '内容分段提到公司',
    'MENTIONS_BRAND': '内容分段提到品牌',
    'INVOLVED_IN_CATEGORY': '公司参与分类',
    'BELONGS_TO_BRAND': '公司隶属于品牌',
    'BELONGS_TO_TYPE': '公司属于组织类型',
    'OPERATES_IN_TYPE': '品牌关联组织类型',
    'SPO_REL': '公司语义行为关系'
}

# v1.1 默认不依赖旧向量索引；若需要向量检索，请根据 Section 节点自建索引
VECTOR_INDEX_NAME = os.getenv('SECTION_VECTOR_INDEX', 'SectionEmbedding')
VECTOR_NODE_LABEL = os.getenv('SECTION_VECTOR_LABEL', 'Section')
VECTOR_SOURCE_PROPERTY = os.getenv('SECTION_VECTOR_SOURCE_PROP', 'content')
VECTOR_EMBEDDING_PROPERTY = os.getenv('SECTION_VECTOR_EMBED_PROP', 'textEmbedding')

# 公关传播特定属性
PR_PROPERTIES = {
    'Brand': ['name', 'industry', 'founded_year', 'brand_value'],
    'Agency': ['name', 'founded_year', 'specialization', 'reputation'],
    'Campaign': ['name', 'launch_date', 'budget', 'duration', 'status'],
    'Strategy': ['strategy_type', 'target_audience', 'key_message', 'channels'],
    'Media': ['media_type', 'reach', 'engagement_rate', 'cost'],
    'Target_Audience': ['demographics', 'psychographics', 'behavior', 'size'],
    'Content': ['content_type', 'tone', 'format', 'performance'],
    'KPI': ['metric_name', 'target_value', 'actual_value', 'measurement_date']
}

# Neo4j连接配置
try:
    graph = Neo4jGraph(
        url=NEO4J_URI,
        username=NEO4J_USERNAME,
        password=NEO4J_PASSWORD,
        database=NEO4J_DATABASE
    )
    print("✅ Neo4j连接成功")
except Exception as e:
    print(f"❌ Neo4j连接失败: {e}")
    graph = None

