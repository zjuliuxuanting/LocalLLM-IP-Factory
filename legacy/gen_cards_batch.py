#!/usr/bin/env python3
"""Generate 20 card entries from seed_pool.json, status=pending."""

import json
import random
from datetime import datetime, timezone

with open('data/seed_pool.json', 'r') as f:
    seed_data = json.load(f)

# Series order: B→R→M→Q→F→P→S (knowledge base first), random within series
series_order = ['B', 'R', 'M', 'Q', 'F', 'P', 'S']

selected_seeds = []
for i in range(20):
    series_idx = i % len(series_order)
    series = series_order[series_idx]
    if series in seed_data and 'seeds' in seed_data[series]:
        pending = [s for s in seed_data[series]['seeds'] if s.get('status') == 'pending']
        if pending:
            seed = random.choice(pending)
            selected_seeds.append((series, seed))

print(f"Selected {len(selected_seeds)} seeds:")
for i, (s, seed) in enumerate(selected_seeds):
    print(f"  {i+1}. [{s}] {seed['title']}")

# Load existing cards.json to get next ID
with open('data/queue/cards.json', 'r') as f:
    cards_data = json.load(f)

cards = cards_data.get('cards', []) if isinstance(cards_data, dict) else []

# Track IDs per series for numbering
id_counters = {}

for i, (series, seed) in enumerate(selected_seeds):
    # Generate ID
    counter = id_counters.get(series, 0) + 1
    id_counters[series] = counter
    
    if series == 'B':
        card_id = f"B_{counter:03d}"
    else:
        # Use letter + number format for other series
        # Find max existing ID for this series to continue numbering
        existing_nums = []
        for c in cards:
            cid = c.get('id', '')
            if cid.startswith(series) and (len(cid) == 1 or cid[1:].isdigit()):
                try:
                    num = int(cid[1:])
                    existing_nums.append(num)
                except ValueError:
                    pass
        
        if existing_nums:
            next_num = max(existing_nums) + counter
        else:
            next_num = counter
        card_id = f"{series}{next_num}"
    
    # Create card entry
    card_entry = {
        "id": card_id,
        "section": series,
        "title": seed['title'],
        "status": "ready",
        "goal": seed.get('goal', ''),
        "search": {
            "engine": seed.get('engine', 'web'),
            "keywords": seed.get('kw', '')
        },
        "sources": [],
        "claims": []
    }
    
    cards.append(card_entry)

# Save updated cards.json
if isinstance(cards_data, dict):
    cards_data['cards'] = cards
else:
    cards_data = {'version': 'v3', 'updated_at': datetime.now(timezone.utc).isoformat(), 'cards': cards}

with open('data/queue/cards.json', 'w', encoding='utf-8') as f:
    json.dump(cards_data, ensure_ascii=False, indent=2, fp=f)

print(f"\nCreated {len(selected_seeds)} new card entries in cards.json")
print("Card IDs:", [c['id'] for c in selected_seeds])
