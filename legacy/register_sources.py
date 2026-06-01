#!/usr/bin/env python3
"""Register 5 new sources and update cards.json."""

import json
from datetime import datetime, timezone

# New sources to register
new_sources = [
    {
        "source_id": "src_cache_B_001_cat_kneading_purring",
        "title": "猫咪踩奶与呼噜声的神经生物学机制：催产素-内啡肽奖励循环与副交感激活",
        "type": "web",
        "kw": "cat kneading purring oxytocin endorphin parasympathetic vagus nerve mechanism",
        "url": "https://blog.catcognition.com/why-do-cats-knead/",
        "cache_path": "data/source_cache/shared/B_001_cat_kneading_purring_mechanism.txt",
        "retrieved_at": datetime.now(timezone.utc).isoformat()
    },
    {
        "source_id": "src_cache_R_01_zoo_animal_button_communication",
        "title": "动物园的AAC设备实验：黑猩猩lexigram键盘与海豚协作按钮任务研究",
        "type": "web",
        "kw": "chimpanzee dolphin AAC device lexigram button communication zoo research",
        "url": "https://www.animalsaroundtheglobe.com/teaching-animals-to-communicate-what-weve-learned-3-335813/",
        "cache_path": "data/source_cache/shared/R_01_zoo_animal_button_communication.txt",
        "retrieved_at": datetime.now(timezone.utc).isoformat()
    },
    {
        "source_id": "src_cache_M_01_senior_pet_adaptive_communication",
        "title": "老年宠物无障碍沟通改造：视听力下降适配的按钮与手信号方案",
        "type": "web",
        "kw": "elderly pet adaptive communication device vision hearing loss button training senior dog cat",
        "url": "https://ipuppee.com/blogs/news/pet-owner-independence-tips-communication-care",
        "cache_path": "data/source_cache/shared/M_01_senior_pet_adaptive_communication.txt",
        "retrieved_at": datetime.now(timezone.utc).isoformat()
    },
    {
        "source_id": "src_cache_Q_01_adult_dog_button_training",
        "title": "成年狗从零学按钮：分阶段训练方法与Stella案例研究",
        "type": "web",
        "kw": "adult dog learn communication buttons training from scratch late start critical period",
        "url": "https://ipuppee.com/blogs/news/how-to-introduce-communication-devices-to-your-dog",
        "cache_path": "data/source_cache/shared/Q_01_adult_dog_button_training.txt",
        "retrieved_at": datetime.now(timezone.utc).isoformat()
    },
    {
        "source_id": "src_cache_F_01_cat_button_territorial_war",
        "title": "猫咪用按钮发战书：Justin Bieber案例与clicking狩猎行为分析",
        "type": "web",
        "kw": "cat button communication territorial aggression window bird watching funny video Justin Bieber",
        "url": "https://petgd.com/heres-how-to-teach-your-cat-to-talk-with-buttons/",
        "cache_path": "data/source_cache/shared/F_01_cat_button_territorial_war.txt",
        "retrieved_at": datetime.now(timezone.utc).isoformat()
    }
]

# Load source registry
with open('data/source_registry/index.json', 'r') as f:
    registry = json.load(f)

# Add new sources
for src in new_sources:
    registry[src['source_id']] = src

# Save updated registry
with open('data/source_registry/index.json', 'w', encoding='utf-8') as f:
    json.dump(registry, ensure_ascii=False, indent=2, fp=f)

print(f"Registered {len(new_sources)} new sources in index.json")

# Now update cards.json with source info for the first 5 cards
with open('data/queue/cards.json', 'r') as f:
    cards_data = json.load(f)

cards = cards_data.get('cards', []) if isinstance(cards_data, dict) else []

# Map of card IDs to their sources
source_map = {
    "B_001": ["src_cache_B_001_cat_kneading_purring"],
    "R1": ["src_cache_R_01_zoo_animal_button_communication"],
    "M1": ["src_cache_M_01_senior_pet_adaptive_communication"],
    "Q1": ["src_cache_Q_01_adult_dog_button_training"],
    "F1": ["src_cache_F_01_cat_button_territorial_war"]
}

for card in cards:
    cid = card.get('id', '')
    if cid in source_map:
        card['sources'] = [source_map[cid][0]]
        card['claims'] = [{"source_id": s} for s in source_map[cid]]
        card['status'] = 'ready'

# Save updated cards
if isinstance(cards_data, dict):
    cards_data['cards'] = cards

with open('data/queue/cards.json', 'w', encoding='utf-8') as f:
    json.dump(cards_data, ensure_ascii=False, indent=2, fp=f)

print("Updated cards.json with source information for first 5 cards")
