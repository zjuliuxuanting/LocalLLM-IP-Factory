"""系列定义 — 单一数据源

所有系列配置集中于此。新增系列只需：
1. 在这里加一个条目
2. 在 seed_pool.json 加对应 key
3. 在 PROJECT_MAP.md 加编号规则
"""
from typing import Optional

SERIES = {
    "A": {
        "name": "背景知识",
        "topic": "A 背景知识",
        "style": "科普叙事，有温度有深度，不学术腔",
        "forbidden": ["在本文中", "值得注意的是", "综上所述"],
        "source_policy": "required",
        "target_ratio": 0.18,
        "engine_pref": "pubmed",
        "avg_chars": 450,
        "subtopics": ["子话题1", "子话题2", "子话题3"],
        "goal_rule": "科普写作目标，必须包含具体知识点",
        "kw_rule": "英文关键词 ≥3 词",
        "example_seed": {
            "title": "示例标题：核心发现与关键证据",
            "goal": "综合发现和研究，讲述这个主题的完整历程",
            "engine": "pubmed",
            "kw": "example english keywords at least three words",
        },
        "notes": "IP 的知识基础层",
    },
    "B": {
        "name": "市场调研",
        "topic": "B 调研",
        "style": "记者风格。有数据有人物有观点。",
        "forbidden": ["在本文中", "值得注意的是", "综上所述"],
        "source_policy": "required",
        "target_ratio": 0.15,
        "engine_pref": "web",
        "avg_chars": 400,
        "subtopics": ["市场规模", "竞品分析", "用户画像"],
        "goal_rule": "调研目标必须包含数据维度",
        "kw_rule": "英文关键词 ≥3 词",
        "example_seed": {
            "title": "市场分析：谁在为这个需求买单",
            "goal": "梳理融资动态、用户规模和主要玩家",
            "engine": "web",
            "kw": "market analysis investment funding trends",
        },
        "notes": "数据驱动，支撑商业决策",
    },
    "C": {
        "name": "方法论",
        "topic": "C 方法论",
        "style": "实操派。像老师傅带徒弟。",
        "forbidden": ["在本文中", "值得注意的是", "综上所述"],
        "source_policy": "required",
        "target_ratio": 0.12,
        "engine_pref": "web",
        "avg_chars": 350,
        "subtopics": ["入门", "进阶", "常见错误"],
        "goal_rule": "实操目标必须包含具体步骤/技巧/常见错误",
        "kw_rule": "英文关键词 ≥2 词",
        "example_seed": {
            "title": "第一步：选对方向比动手更重要",
            "goal": "从实操角度指导用户如何开始",
            "engine": "web",
            "kw": "beginner guide first steps method tutorial",
        },
        "notes": "实操内容，用户留存的关键",
    },
    "D": {
        "name": "小说叙事",
        "topic": "D 小说",
        "style": "小说体，第一人称视角。感官描写为主。",
        "forbidden": ["在本文中", "值得注意的是", "综上所述"],
        "source_policy": "optional",
        "target_ratio": 0.15,
        "engine_pref": "web",
        "avg_chars": 500,
        "subtopics": ["起源故事", "日常温情", "幽默反转"],
        "goal_rule": "叙事目标必须包含视角、核心场景和情感基调",
        "kw_rule": "英文关键词 ≥2 词",
        "example_seed": {
            "title": "第一次体验这个奇妙瞬间",
            "goal": "以第一人称视角描述第一次体验时的感官和心理变化",
            "engine": "web",
            "kw": "first person narrative emotional experience story",
        },
        "notes": "IP 的情感核心",
    },
    "E": {
        "name": "问答",
        "topic": "E 问答",
        "style": "亲切解答、像老朋友。不居高临下。",
        "forbidden": ["在本文中", "值得注意的是", "综上所述"],
        "source_policy": "required",
        "target_ratio": 0.15,
        "engine_pref": "web",
        "avg_chars": 300,
        "subtopics": ["常见问题", "行为解读", "产品使用"],
        "goal_rule": "问答目标必须包含具体问题和解答方向",
        "kw_rule": "英文关键词 ≥2 词",
        "example_seed": {
            "title": "为什么会出现这种情况?——常见问题解析",
            "goal": "分析原因并给出排查方法和解决策略",
            "engine": "web",
            "kw": "common questions troubleshooting guide solutions",
        },
        "notes": "读者互动入口",
    },
    "F": {
        "name": "趣味内容",
        "topic": "F 趣味",
        "style": "幽默轻松、让人想分享。可以夸张不胡说。",
        "forbidden": ["在本文中", "值得注意的是", "综上所述"],
        "source_policy": "required",
        "target_ratio": 0.15,
        "engine_pref": "web",
        "avg_chars": 400,
        "subtopics": ["翻车现场", "趣闻轶事", "幽默反转"],
        "goal_rule": "趣味目标必须包含反转/冲突/共鸣元素",
        "kw_rule": "英文关键词 ≥2 词",
        "example_seed": {
            "title": "离谱但真实：这件事让所有人都笑了",
            "goal": "还原真实发生的趣事，制造错位幽默",
            "engine": "web",
            "kw": "funny viral story humorous anecdote",
        },
        "notes": "传播主力",
    },
    "G": {
        "name": "人物故事",
        "topic": "G 人物",
        "style": "人物特写风格。有细节有人情味。",
        "forbidden": ["在本文中", "值得注意的是", "综上所述"],
        "source_policy": "required",
        "target_ratio": 0.10,
        "engine_pref": "web",
        "avg_chars": 500,
        "subtopics": ["创始人", "研究者", "用户故事"],
        "goal_rule": "人物故事目标必须包含人物身份、核心经历和叙事角度",
        "kw_rule": "英文关键词 ≥3 词",
        "example_seed": {
            "title": "从爱好者到专家：一个人的探索之路",
            "goal": "讲述一个人从兴趣出发，逐步成为领域专家的故事",
            "engine": "web",
            "kw": "personal story journey from amateur to expert",
        },
        "notes": "品牌故事和人物IP",
    },
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
