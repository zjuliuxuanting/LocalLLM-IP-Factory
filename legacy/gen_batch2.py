#!/usr/bin/env python3
"""Generate 20 new card entries from seed_pool.json, excluding already used seeds."""

import json
import random
from datetime import datetime, timezone

with open('data/seed_pool.json', 'r') as f:
    seed_data = json.load(f)

# Load existing cards to get already-used IDs
with open('data/queue/cards.json', 'r') as f:
    cards_data = json.load(f)

existing_cards = cards_data.get('cards', []) if isinstance(cards_data, dict) else []
used_ids = {c['id'] for c in existing_cards}
print(f"Already have {len(used_ids)} cards")

# Series order: B→R→M→Q→F→P→S (knowledge base first), random within series
series_order = ['B', 'R', 'M', 'Q', 'F', 'P', 'S']

selected_seeds = []
for i in range(20):
    series_idx = i % len(series_order)
    series = series_order[series_idx]
    
    if series in seed_data and 'seeds' in seed_data[series]:
        # Get pending seeds that haven't been used yet
        pending = [s for s in seed_data[series]['seeds'] 
                   if s.get('status') == 'pending']
        
        if pending:
            seed = random.choice(pending)
            selected_seeds.append((series, seed))

print(f"Selected {len(selected_seeds)} new seeds:")
for i, (s, seed) in enumerate(selected_seeds):
    print(f"  {i+1}. [{s}] {seed['title']}")

# Track IDs per series for numbering - find max existing ID
id_counters = {}
series_max_nums = {}

for c in existing_cards:
    cid = c.get('id', '')
    if cid.startswith(('B_', 'R', 'M', 'Q', 'F', 'P', 'S')):
        # Extract series letter and number
        for prefix in ['B_', 'R', 'M', 'Q', 'F', 'P', 'S']:
            if cid.startswith(prefix):
                rest = cid[len(prefix):]
                if rest.isdigit():
                    num = int(rest)
                    series_max_nums[prefix] = max(series_max_nums.get(prefix, 0), num)
                break

# Generate new card entries
new_cards = []
for i, (series, seed) in enumerate(selected_seeds):
    counter = id_counters.get(series, 0) + 1
    id_counters[series] = counter
    
    # Determine next ID for this series
    max_num = series_max_nums.get(series, 0)
    
    if series == 'B':
        card_id = f"B_{max_num + counter:03d}"
    else:
        card_id = f"{series}{max_num + counter}"
    
    # Create card entry matching the existing format
    card_entry = {
        "id": card_id,
        "section": series,
        "title": seed['title'],
        "status": "pending",  # Start as pending until sources are added
        "goal": seed.get('goal', ''),
        "search": {
            "engine": seed.get('engine', 'web'),
            "keywords": seed.get('kw', '')
        },
        "sources": [],
        "claims": []
    }
    
    new_cards.append(card_entry)

# Append to existing cards
if isinstance(cards_data, dict):
    cards_data['cards'].extend(new_cards)
else:
    cards_data = {'version': 'v3', 'updated_at': datetime.now(timezone.utc).isoformat(), 
                  'cards': new_cards}

with open('data/queue/cards.json', 'w', encoding='utf-8') as f:
    json.dump(cards_data, ensure_ascii=False, indent=2, fp=f)

print(f"\nCreated {len(new_cards)} new card entries in cards.json")
print("New Card IDs:", [c['id'] for c in new_cards])
