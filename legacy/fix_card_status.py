#!/usr/bin/env python3
"""Fix card status: cards without sources should be 'pending', not 'ready'."""

import json

with open('data/queue/cards.json', 'r') as f:
    cards_data = json.load(f)

cards = cards_data.get('cards', []) if isinstance(cards_data, dict) else []

# Cards that have sources (should stay "ready")
ready_ids = {"B_001", "R1", "M1", "Q1", "F1"}

# All new 20 card IDs - those without sources should be "pending"
all_new_ids = {"B_001", "R1", "M1", "Q1", "F1", "P1", "S1", "B_002", "R3", "M3", "Q3", "F3", "P3", "S3", "B_003", "R6", "M6", "Q6", "F6", "P6"}

updated = 0
for card in cards:
    cid = card.get('id', '')
    if cid in all_new_ids and cid not in ready_ids:
        # Check if this card actually has sources
        sources = card.get('sources', [])
        
        if not sources or len(sources) == 0:
            old_status = card.get('status', 'unknown')
            card['status'] = 'pending'
            updated += 1
            print(f"Updated {cid}: '{old_status}' -> 'pending'")

# Save updated cards
if isinstance(cards_data, dict):
    cards_data['cards'] = cards

with open('data/queue/cards.json', 'w', encoding='utf-8') as f:
    json.dump(cards_data, ensure_ascii=False, indent=2, fp=f)

print(f"\nTotal updated: {updated} cards from '{old_status}' to 'pending'")

# Verify final status
final_ready = sum(1 for c in cards if c.get('id', '') in ready_ids and c.get('status') == 'ready')
final_pending = sum(1 for c in cards if c.get('id', '') in all_new_ids and c not in ready_ids and c.get('status') == 'pending')
print(f"Verification: {final_ready} ready (with sources), {final_pending} pending (no sources)")
