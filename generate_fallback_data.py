#!/usr/bin/env python3
"""Generate fallback demo data for the food prices dashboard."""

import json
from pathlib import Path
from datetime import datetime

output = Path("data/prices.json")
output.parent.mkdir(parents=True, exist_ok=True)

# Demo data with realistic Norwegian and Swedish food prices
data = {
    "last_updated": datetime.utcnow().isoformat(),
    "norway": [
        {"name": "Melk fullfedt", "category": "mejeri", "stores": ["Rema 1000", "Kiwi"], "price": 15.90, "currency": "NOK", "unit": "liter", "market": "norwegian-chains"},
        {"name": "Brød, hvit", "category": "brød", "stores": ["Rema 1000", "Kiwi", "Meny"], "price": 24.90, "currency": "NOK", "unit": "stk", "market": "norwegian-chains"},
        {"name": "Egg, 10 stk", "category": "mejeri", "stores": ["Rema 1000", "Kiwi", "Spar"], "price": 34.90, "currency": "NOK", "unit": "stk", "market": "norwegian-chains"},
        {"name": "Yoghurt nature", "category": "mejeri", "stores": ["Rema 1000", "Joker", "Naerbutikken"], "price": 12.50, "currency": "NOK", "unit": "liter", "market": "norwegian-chains"},
        {"name": "Kjøttdeigsburger", "category": "kjøtt", "stores": ["Coop Extra", "Reitan Retail", "Rema 1000"], "price": 89.90, "currency": "NOK", "unit": "kg", "market": "norwegian-chains"},
    ],
    "sweden": [
        {"name": "Mjölk hel", "category": "mejeri", "stores": ["Nordby"], "price": 14.50, "currency": "SEK", "unit": "liter", "market": "nordby-sweden"},
        {"name": "Bröd, vit", "category": "bröd", "stores": ["Nordby"], "price": 22.90, "currency": "SEK", "unit": "stk", "market": "nordby-sweden"},
        {"name": "Ägg, 10 stk", "category": "mejeri", "stores": ["Nordby"], "price": 32.50, "currency": "SEK", "unit": "stk", "market": "nordby-sweden"},
        {"name": "Yoghurt nature", "category": "mejeri", "stores": ["Nordby"], "price": 11.90, "currency": "SEK", "unit": "liter", "market": "nordby-sweden"},
        {"name": "Köttfärs", "category": "kött", "stores": ["Nordby", "Coop Prix"], "price": 129.00, "currency": "SEK", "unit": "kg", "market": "nordby-sweden"},
    ]
}

output.write_text(json.dumps(data, indent=2, ensure_ascii=False))
print(f"Generated fallback data at {output}")