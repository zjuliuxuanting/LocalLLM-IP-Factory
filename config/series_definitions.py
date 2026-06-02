"""系列定义 — 单一数据源

由 scripts/import_series_names.py 自动生成
数据源: docs/SERIES_TOPICS.md
结构定义: config/series_schema.json
"""
from typing import Optional


SERIES = {
  "B": {
    "name": "背景知识 / 沟通简史",
    "topic": "B 背景知识 / 沟通简史",
    "style": "科普叙事，有温度有深度，不学术腔",
    "forbidden": [
      "在本文中",
      "值得注意的是",
      "综上所述"
    ],
    "source_policy": "required",
    "target_ratio": 0.18,
    "engine_pref": "pubmed",
    "avg_chars": 450,
    "subtopics": [
      "驯化历史",
      "动物认知",
      "语言学",
      "进化生物学",
      "神经科学",
      "AAC技术",
      "比较心理学",
      "人类学",
      "动物行为"
    ],
    "goal_rule": "科普写作目标，必须包含具体知识点（如\"介绍XX研究发现/讲述XX历史过程\"）",
    "kw_rule": "英文关键词 ≥3 词，优先 pubmed/arxiv",
    "example_seed": {
      "title": "犬类驯化起源：考古学与基因组学的双重证据",
      "goal": "综合考古学发现和DNA研究，讲述狼如何在与人类共生的15000年中逐步演化为家犬的完整历程",
      "engine": "pubmed",
      "kw": "dog domestication origin archaeological genomic evidence"
    },
    "notes": "IP 的知识基础层。B1=沟通简史(12张✅)，B2=语言理解研究(4张)，B3+可扩展"
  },
  "R": {
    "name": "市场调研",
    "topic": "R 市场调研",
    "style": "记者风格。有数据有人物有观点",
    "forbidden": [
      "在本文中",
      "值得注意的是",
      "综上所述"
    ],
    "source_policy": "required",
    "target_ratio": 0.15,
    "engine_pref": "web",
    "avg_chars": 400,
    "subtopics": [
      "市场规模",
      "竞品分析",
      "用户画像",
      "投资趋势",
      "技术专利",
      "社交媒体",
      "政策法规",
      "商业模式"
    ],
    "goal_rule": "调研目标必须包含数据维度（市场规模/用户画像/竞品对比/技术趋势）",
    "kw_rule": "英文关键词 ≥3 词，偏商业/科技向",
    "example_seed": {
      "title": "宠物智能硬件赛道：谁在为动物沟通买单",
      "goal": "梳理2024-2025年宠物智能硬件的融资动态、用户规模和主要玩家，分析VC投资逻辑和赛道天花板",
      "engine": "web",
      "kw": "pet smart hardware investment funding market size 2025"
    },
    "notes": "数据驱动，支撑商业决策。R1=产品调研，R2=市场分析"
  },
  "M": {
    "name": "方法论",
    "topic": "M 方法论",
    "style": "实操派。像老师傅带徒弟",
    "forbidden": [
      "在本文中",
      "值得注意的是",
      "综上所述"
    ],
    "source_policy": "required",
    "target_ratio": 0.12,
    "engine_pref": "web",
    "avg_chars": 350,
    "subtopics": [
      "入门训练",
      "进阶技巧",
      "多宠管理",
      "按钮布局",
      "故障排除",
      "特殊需求宠物",
      "儿童参与",
      "老年宠物"
    ],
    "goal_rule": "实操目标必须包含具体步骤/技巧/常见错误",
    "kw_rule": "英文关键词 ≥2 词，侧重 training/method/guide",
    "example_seed": {
      "title": "按钮训练第一步：选对第一个词比选对按钮更重要",
      "goal": "从实操角度指导宠物主人如何选择第一个训练词汇——分析高频词vs实用词vs情感词的优劣，给出针对不同宠物性格的选词建议，并说明最常见的3个选词错误及后果",
      "engine": "web",
      "kw": "pet button training first word selection method guide"
    },
    "notes": "实操内容，用户留存的关键。种子不宜过多，防同质化"
  },
  "S": {
    "name": "小说叙事",
    "topic": "S 小说叙事",
    "style": "小说体，第一人称动物视角。感官描写为主。围绕按钮沟通体验",
    "forbidden": [
      "在本文中",
      "值得注意的是",
      "综上所述"
    ],
    "source_policy": "optional",
    "target_ratio": 0.15,
    "engine_pref": "web",
    "avg_chars": 500,
    "subtopics": [
      "起源故事",
      "Bunny叙事",
      "日常温情",
      "冒险幻想",
      "幽默反转",
      "跨物种友谊",
      "科技反思",
      "节日主题"
    ],
    "goal_rule": "叙事目标必须包含视角（第几人称/哪个角色）、核心场景和情感基调",
    "kw_rule": "英文关键词 ≥2 词，侧重场景/情感/体验",
    "example_seed": {
      "title": "第一次按下\"爱\"这个按钮的瞬间",
      "goal": "以一只金毛犬的第一人称视角，描写它第一次学会用按钮说出\"爱\"这个词时的感官体验——从困惑到理解到喜悦的心理变化过程，侧重触觉和嗅觉描写",
      "engine": "web",
      "kw": "dog button communication love emotion first person narrative"
    },
    "notes": "IP 的情感核心。S1=篝火旁(6张✅)，S2=Bunny(3张✅)，S3+可扩展新故事线"
  },
  "Q": {
    "name": "问答",
    "topic": "Q 问答",
    "style": "亲切解答、像老朋友。不居高临下",
    "forbidden": [
      "在本文中",
      "值得注意的是",
      "综上所述"
    ],
    "source_policy": "required",
    "target_ratio": 0.15,
    "engine_pref": "web",
    "avg_chars": 300,
    "subtopics": [
      "训练疑虑",
      "行为解读",
      "产品使用",
      "科学研究",
      "伦理讨论",
      "社区故事",
      "对比测评"
    ],
    "goal_rule": "问答目标必须包含具体问题和解答方向",
    "kw_rule": "英文关键词 ≥2 词",
    "example_seed": {
      "title": "我家狗为什么突然不用按钮了？——按钮沟通的倒退现象解析",
      "goal": "分析狗在使用按钮沟通一段时间后突然停止使用的原因（无聊/挫折/环境变化/健康问题），并给出针对每种原因的具体排查方法和重新激活策略",
      "engine": "web",
      "kw": "dog stopped using communication buttons regression causes"
    },
    "notes": "读者互动入口。从真实用户问题中提取"
  },
  "F": {
    "name": "趣味内容",
    "topic": "F 趣味内容",
    "style": "幽默轻松、让人想分享。可以夸张不胡说",
    "forbidden": [
      "在本文中",
      "值得注意的是",
      "综上所述"
    ],
    "source_policy": "required",
    "target_ratio": 0.15,
    "engine_pref": "web",
    "avg_chars": 400,
    "subtopics": [
      "翻车现场",
      "数据趣闻",
      "拟人化",
      "社会梗",
      "极客幽默",
      "温情反转",
      "挑战系列"
    ],
    "goal_rule": "趣味目标必须包含反转/冲突/共鸣元素和叙事角度",
    "kw_rule": "英文关键词 ≥2 词，侧重 funny/viral/meme 方向",
    "example_seed": {
      "title": "猫咪用按钮向物业投诉：这个铲屎官太懒了",
      "goal": "以猫的第一人称视角和\"正式投诉\"的格式，还原猫对人类\"服务质量\"的五大不满，制造职场文化与养宠日常的错位幽默",
      "engine": "web",
      "kw": "cat button complaint owner lazy funny pet humor"
    },
    "notes": "传播主力。创意最密集，最需要多样性保护"
  },
  "P": {
    "name": "人物故事",
    "topic": "P 人物故事",
    "style": "人物特写风格。有细节有人情味",
    "forbidden": [
      "在本文中",
      "值得注意的是",
      "综上所述"
    ],
    "source_policy": "required",
    "target_ratio": 0.1,
    "engine_pref": "web",
    "avg_chars": 500,
    "subtopics": [
      "创始人",
      "研究者",
      "用户故事",
      "宠物明星",
      "行业人物"
    ],
    "goal_rule": "人物故事目标必须包含人物身份、核心经历和叙事角度",
    "kw_rule": "英文关键词 ≥3 词，偏人物/采访/案例",
    "example_seed": {
      "title": "从言语治疗师到狗狗翻译官：Christina Hunger的故事",
      "goal": "讲述言语治疗师Christina Hunger如何从她的AAC专业背景中获得灵感，将人类辅助沟通技术应用到宠物狗Stella身上，以及这段经历如何改变了她的职业生涯和动物认知科学领域",
      "engine": "web",
      "kw": "Christina Hunger speech therapist dog AAC button Stella"
    },
    "notes": "品牌故事和人物IP"
  }
}


RETIRED_SERIES = []


def get_series(key: str) -> Optional[dict]:
    return SERIES.get(key)


def all_series_keys() -> list[str]:
    return [k for k in SERIES if k not in RETIRED_SERIES]


def get_source_policy(key: str) -> str:
    s = SERIES.get(key, {})
    return s.get("source_policy", "optional")


def get_target_ratio(key: str) -> float:
    s = SERIES.get(key, {})
    return s.get("target_ratio", 0.0)


def get_subtopics(key: str) -> list[str]:
    s = SERIES.get(key, {})
    return s.get("subtopics", [])


def get_example_seed(key: str) -> dict:
    s = SERIES.get(key, {})
    return s.get("example_seed", {})


def get_goal_rule(key: str) -> str:
    s = SERIES.get(key, {})
    return s.get("goal_rule", "写作目标，≥20字")


def get_kw_rule(key: str) -> str:
    s = SERIES.get(key, {})
    return s.get("kw_rule", "英文关键词 ≥2 词")
