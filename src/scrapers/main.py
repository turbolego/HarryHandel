#!/usr/bin/env python3
"""
Food price scraper for Norway vs Sweden dashboard.

Uses Playwright for headless browser scraping to handle JavaScript-rendered sites.

Scrapes prices from:
- kassal.app (Norwegian grocery comparison)
- rema.no (Norwegian grocery store)
- nordby.se (Swedish grocery store)
- ica.se (Swedish grocery store)

Run via: cd src && python -m scrapers.main
"""

import json
import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


class PriceScraper:
    """Base scraper class with Playwright utilities."""

    def __init__(self, headless: bool = True):
        self.headless = headless

    def fetch_page(self, url: str) -> BeautifulSoup | None:
        """Fetch a URL using Playwright and return BeautifulSoup, or None on error."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context()
                page = context.new_page()
                page.goto(url, wait_until="networkidle")
                html = page.content()
                browser.close()
                return BeautifulSoup(html, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url} with Playwright: {e}")
            return None

    def clean_text(self, text: str) -> str:
        """Clean scraped text."""
        return text.strip().replace('\n', ' ').replace('\t', '').strip()


class RemaScraper(PriceScraper):
    """Scrape prices from rema.no using Playwright."""

    BASE_URL = "https://www.rema.no"

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        """Scrape products from a rema category page."""
        soup = self.fetch_page(category_url)
        if not soup:
            return []

        products = []

        # rema.no: price elements have class 'font-price' with absolute positioning
        # Format: "399039,90 kr" (price in øre, followed by "kr")
        price_elements = soup.select('[class*="font-price"]')

        for el in price_elements:
            try:
                price_text = el.get_text(strip=True)
                # Format: "399039,90 kr" - extract the number
                match = re.search(r'(\d+[\d,]*,\d{2})\s*kr', price_text)
                if match:
                    price_str = match.group(1).replace(',', '.')
                    price = float(price_str)
                    # Parse product info from the parent context
                    parent = el.parent
                    name = "Unknown"
                    if parent:
                        for _ in range(3):
                            if parent.name:
                                name_candidate = parent.select_one('a, [class*="product-name"], h3')
                                if name_candidate and name_candidate.get_text(strip=True):
                                    name = self.clean_text(name_candidate.get_text(strip=True))
                                    break
                                parent = parent.parent
                            else:
                                break

                    products.append({
                        'name': name,
                        'category': 'supermarket',
                        'stores': ['Rema 1000'],
                        'price': price,
                        'currency': 'NOK',
                        'unit': 'per item',
                        'market': 'rema-norway'
                    })
            except Exception as e:
                print(f"Warning: Failed to parse rema price element: {e}")

        return products


class NordbyScraper(PriceScraper):
    """Scrape prices from nordby.se using Playwright."""

    BASE_URL = "https://nordby.se"

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        soup = self.fetch_page(category_url)
        if not soup:
            return []

        products = []

        price_elements = soup.select('[class*="be-offer-price"]')

        for el in price_elements:
            try:
                price_text = el.get_text(strip=True)

                price = None
                unit = 'per kg'

                if re.match(r'^\d+$', price_text):
                    price = float(price_text)
                    unit = self._get_nordby_unit(el)
                elif ':' in price_text and '/ST' in price_text:
                    parts = price_text.split('/')
                    price = float(parts[0].replace(':', '.'))
                    unit = 'per st'
                elif 'kg' in price_text.lower():
                    parts = price_text.split('/')
                    price = float(parts[0].replace(':', '.'))
                    unit = 'per kg'
                elif price_text.endswith(' kr'):
                    p = price_text.replace(' kr', '').replace(',', '.')
                    price = float(p)
                    unit = 'per item'
                else:
                    match = re.search(r'(\d[\d,]*)', price_text.replace(' ', ''))
                    if match:
                        price = float(match.group(1).replace(',', '.'))

                if price is not None:
                    name = self._get_nordby_name(el)
                    products.append({
                        'name': name,
                        'category': 'supermarket',
                        'stores': ['Nordby'],
                        'price': price,
                        'currency': 'SEK',
                        'unit': unit,
                        'market': 'nordby-sweden'
                    })
            except Exception as e:
                print(f"Warning: Failed to parse nordby price element: {e}")

        return products

    def _get_nordby_unit(self, el) -> str:
        parent = el.parent
        for _ in range(3):
            if not parent or not parent.name:
                break
            siblings = parent.find_next_siblings()
            for sib in siblings[:3]:
                sib_text = sib.get_text(strip=True)
                if sib_text and 'kg' in sib_text.lower():
                    return 'per kg'
                if sib_text and 'st' in sib_text.lower():
                    return 'per st'
            parent = parent.parent
        return 'per kg'

    def _get_nordby_name(self, el) -> str:
        parent = el.parent
        for _ in range(4):
            if not parent or not parent.name:
                break
            name_candidate = parent.select_one('a, h3, [class*="product"]')
            if name_candidate:
                text = self.clean_text(name_candidate.get_text(strip=True))
                if text and len(text) > 3:
                    return text
                parent = parent.parent

        parent_text = el.parent.get_text(strip=True)
        cleaned = re.sub(r'[\d:,/.]+', '', parent_text).strip()
        if cleaned:
            return cleaned[:50]
        return "Unknown"


class KassalScraper(PriceScraper):
    BASE_URL = "https://kassal.app"

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        soup = self.fetch_page(category_url)
        if not soup:
            return []

        products = []
        product_lis = soup.select('li')

        for li in product_lis:
            try:
                li_text = li.get_text(strip=True)
                if not li_text:
                    continue

                price_match = re.match(r'(-?\d+\.?\d*)', li_text)
                if not price_match:
                    continue

                price = float(price_match.group(1))
                name_raw = li_text[price_match.end():].strip()
                store_tags = ['Oda', 'SPAR', 'Meny', 'Kiwi', 'Joker', 'Reitan']
                name = name_raw
                for tag in store_tags:
                    if tag in name:
                        idx = name.index(tag)
                        name = name[:idx].strip()

                if len(name) < 3:
                    continue

                unit = 'per item'
                products.append({
                    'name': name,
                    'category': 'unknown',
                    'stores': ['Kassal'],
                    'price': price,
                    'currency': 'NOK',
                    'unit': unit,
                    'market': 'kassal'
                })
            except Exception as e:
                print(f"Warning: Failed to parse kassal product: {e}")

        return products


class IcaScraper(PriceScraper):
    """Scrape prices from ica.se using Playwright."""

    BASE_URL = "https://www.ica.se"

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        soup = self.fetch_page(category_url)
        if not soup:
            return []

        products = []

        # ICA product cards - adjust selectors as needed
        product_cards = soup.select('[class*="product-card"], [class*="ProductCard"]')
        for card in product_cards:
            try:
                # Product name
                name_el = card.select_one('[class*="product-name"], h3, a')
                name = self.clean_text(name_el.get_text(strip=True)) if name_el else "Unknown"

                # Price
                price_el = card.select_one('[class*="price"], [class*="Price"]')
                price = None
                if price_el:
                    price_text = price_el.get_text(strip=True)
                    match = re.search(r'(\d+[,\d]*)\s*kr', price_text.replace(' ', ''))
                    if match:
                        price = float(match.group(1).replace(',', '.'))

                # Unit
                unit_el = card.select_one('[class*="unit"], [class*="Unit"]')
                unit = self.clean_text(unit_el.get_text(strip=True)) if unit_el else 'per item'

                if price is not None:
                    products.append({
                        'name': name,
                        'category': 'supermarket',
                        'stores': ['ICA'],
                        'price': price,
                        'currency': 'SEK',
                        'unit': unit,
                        'market': 'ica-sweden'
                    })
            except Exception as e:
                print(f"Warning: Failed to parse ICA product: {e}")

        return products


def load_existing_data(output_path: Path) -> Dict[str, Any]:
    """Load existing price data from file."""
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load existing data: {e}")
    return {'norway': [], 'sweden': []}


def normalize_name(name: str) -> str:
    """Normalize product name for matching."""
    return name.lower().replace('\s+', ' ').strip()


def merge_products(existing: List[Dict], new_products: List[Dict], country: str) -> List[Dict]:
    """Merge new products into existing list, preserving history."""
    # Build lookup by normalized name + market
    existing_map = {}
    for p in existing:
        key = (normalize_name(p['name']), p.get('market', ''))
        existing_map[key] = p

    for new_p in new_products:
        key = (normalize_name(new_p['name']), new_p.get('market', ''))
        now = datetime.utcnow().isoformat()
        price_point = {'date': datetime.utcnow().isoformat(), 'price': new_p['price']}

        if key in existing_map:
            # Update existing product
            existing_p = existing_map[key]
            # Update current price and other fields
            existing_p['price'] = new_p['price']
            existing_p['currency'] = new_p['currency']
            existing_p['unit'] = new_p.get('unit', existing_p.get('unit', 'per item'))
            existing_p['stores'] = new_p.get('stores', existing_p.get('stores', []))
            existing_p['category'] = new_p.get('category', existing_p.get('category', 'supermarket'))
            # Append to history
            history = existing_p.get('history', [])
            # Avoid duplicate price on same day
            if not any(h['price'] == new_p['price'] and h['date'].startswith(datetime.utcnow().date().isoformat()) for h in history):
                history.append(price_point)
            existing_p['history'] = history
            existing_p['last_seen'] = now
        else:
            # New product
            new_p['history'] = [{'date': datetime.utcnow().isoformat(), 'price': new_p['price']}]
            new_p['first_seen'] = datetime.utcnow().isoformat()
            new_p['last_seen'] = datetime.utcnow().isoformat()
            existing_map[key] = new_p

    return list(existing_map.values())


def main():
    parser = argparse.ArgumentParser(description='Scrape food prices and save to JSON')
    parser.add_argument('--output', default='data/prices.json', help='Output JSON file path')
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing data
    existing_data = load_existing_data(output_path)
    existing_norway = existing_data.get('norway', [])
    existing_sweden = existing_data.get('sweden', [])

    scraper = PriceScraper(headless=True)

    all_products = {
        'last_updated': datetime.utcnow().isoformat(),
        'norway': [],
        'sweden': []
    }

    # Scrape from all sources
    print("Scraping rema.no (Norwegian grocery)...")
    rema_products = RemaScraper().scrape_category("https://www.rema.no/inspirasjon/sesong-og-matlyst/nyhetsvindu/")
    all_products['norway'].extend(rema_products)
    print(f"  Found {len(rema_products)} products from rema.no")

    print("Scraping nordby.se (Swedish grocery)...")
    nordby_products = NordbyScraper().scrape_category("https://nordby.se/")
    all_products['sweden'].extend(nordby_products)
    print(f"  Found {len(nordby_products)} products from nordby.se")

    print("Scraping kassal.app (Norwegian comparison)...")
    kassal_products = KassalScraper().scrape_category("https://kassal.app/")
    all_products['norway'].extend(kassal_products)
    print(f"  Found {len(kassal_products)} products from kassal.app")

    print("Scraping ica.se (Swedish grocery)...")
    ica_products = IcaScraper().scrape_category("https://www.ica.se/")
    all_products['sweden'].extend(ica_products)
    print(f"  Found {len(ica_products)} products from ica.se")

    # Merge with existing data preserving history
    all_products['norway'] = merge_products(existing_norway, all_products['norway'], 'norway')
    all_products['sweden'] = merge_products(existing_sweden, all_products['sweden'], 'sweden')

    # Sort by price (lowest first)
    for country in ['norway', 'sweden']:
        all_products[country].sort(key=lambda x: (x.get('price') or float('inf'), x['name']))

    # Write output
    all_products['last_updated'] = datetime.utcnow().isoformat()
    print(f"Saving {len(all_products['norway'])} Norway products, {len(all_products['sweden'])} Sweden products...")
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(all_products, f, indent=2, ensure_ascii=False)

    print(f"Saved to {args.output}")


if __name__ == '__main__':
    main()