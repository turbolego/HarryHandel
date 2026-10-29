#!/usr/bin/env python3
"""
Food price scraper for Norway vs Sweden dashboard.

Uses Playwright for headless browser scraping to handle JavaScript-rendered sites.

Scrapes prices from:
- kassal.app (Norwegian grocery comparison)
- rema.no (Norwegian grocery store)
- nordby.se (Swedish grocery store)

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
                    # The price element is within a product card - find nearby name element
                    parent = el.parent
                    name = "Unknown"
                    if parent:
                        # Look for name in the same card - typically a few levels up
                        for _ in range(3):  # navigate up a few levels
                            if parent.name:
                                # Check if this parent has a name-like element
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
                        'unit': 'per item',  # rema often doesn't specify unit in this view
                        'market': 'rema-norway'
                    })
            except Exception as e:
                print(f"Warning: Failed to parse rema price element: {e}")

        return products


class NordbyScraper(PriceScraper):
    """Scrape prices from nordby.se using Playwright."""

    BASE_URL = "https://nordby.se"

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        """Scrape products from nordby.se category page."""
        soup = self.fetch_page(category_url)
        if not soup:
            return []

        products = []

        # nordby.se: price elements have class 'be-offer-price'
        # Format variants: "1299", "29:95/ST", "139:95/kg", "799:", "1,399 kr"
        price_elements = soup.select('[class*="be-offer-price"]')

        for el in price_elements:
            try:
                price_text = el.get_text(strip=True)

                # Parse price based on format
                price = None
                unit = 'per kg'

                if re.match(r'^\d+$', price_text):
                    # Simple integer: likely øre or kr
                    price = float(price_text)
                    # Check context for unit
                    unit = self._get_nordby_unit(el)
                elif ':' in price_text and '/ST' in price_text:
                    # Format: "29:95/ST"
                    parts = price_text.split('/')
                    price = float(parts[0].replace(':', '.'))
                    unit = 'per st'
                elif 'kg' in price_text.lower():
                    # Format: "139:95/kg"
                    parts = price_text.split('/')
                    price = float(parts[0].replace(':', '.'))
                    unit = 'per kg'
                elif price_text.endswith(' kr'):
                    # Format: "1,399 kr"
                    p = price_text.replace(' kr', '').replace(',', '.')
                    price = float(p)
                    unit = 'per item'
                else:
                    # Try to extract any number
                    match = re.search(r'(\d[\d,]*)', price_text.replace(' ', ''))
                    if match:
                        price = float(match.group(1).replace(',', '.'))

                if price is not None:
                    # Find product name - look in the parent product container
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
        """Try to determine unit from the price element's context."""
        # Look at sibling elements or parent for unit info
        parent = el.parent
        for _ in range(3):
            if not parent or not parent.name:
                break
            # Check parent's parent for unit text
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
        """Extract product name from nordby context."""
        # Look in the parent product container for name info
        parent = el.parent
        for _ in range(4):
            if not parent or not parent.name:
                break
            # Check for name in parent or siblings
            name_candidate = parent.select_one('a, h3, [class*="product"]')
            if name_candidate:
                text = self.clean_text(name_candidate.get_text(strip=True))
                if text and len(text) > 3:
                    return text
            parent = parent.parent

        # Fallback: look at the price element's parent text and remove the price
        parent_text = el.parent.get_text(strip=True)
        # Remove common price patterns
        cleaned = re.sub(r'[\d:,/.]+', '', parent_text).strip()
        if cleaned:
            return cleaned[:50]
        return "Unknown"


class KassalScraper(PriceScraper):
    """Scrape prices from kassal.app using Playwright."""

    BASE_URL = "https://kassal.app"

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        """Scrape kassal.app - JS rendered, extract product data."""
        soup = self.fetch_page(category_url)
        if not soup:
            return []

        products = []

        # kassal.app: products are in <li> elements with price as first text node
        # Structure: <li class=""> -50.00Tynnribbe Fryst, ca. 4 kgOda</li>
        product_lis = soup.select('li')

        for li in product_lis:
            try:
                li_text = li.get_text(strip=True)
                if not li_text:
                    continue

                # Extract price: the text starts with a number (possibly with minus sign)
                # Format: "-50.00Tynnribbe..." or "25.00..."
                price_match = re.match(r'(-?\d+\.?\d*)', li_text)
                if not price_match:
                    continue

                price = float(price_match.group(1))
                # The rest of the text is the product name (minus the price)
                name_raw = li_text[price_match.end():].strip()
                # Remove any non-product text (the page seems to have "Oda" etc. as store tags)
                # Keep only the product name part - typically everything before store tags
                # The format is: "priceProduct nameStoreTag"
                # We'll take the name as everything after the price until obvious store tags
                store_tags = ['Oda', 'SPAR', 'Meny', 'Kiwi', 'Joker', 'Reitan']
                name = name_raw
                for tag in store_tags:
                    if tag in name:
                        # Truncate at the store tag
                        idx = name.index(tag)
                        name = name[:idx].strip()

                # Also filter out very short names or just symbols
                if len(name) < 3:
                    continue

                # Determine unit - from the kassal page structure, most are "per item"
                # but we can try to detect from the product context
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


def main():
    parser = argparse.ArgumentParser(description='Scrape food prices and save to JSON')
    parser.add_argument('--output', default='data/prices.json', help='Output JSON file path')
    args = parser.parse_args()

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

    # Sort by price (lowest first)
    for country in ['norway', 'sweden']:
        all_products[country].sort(key=lambda x: (x.get('price') or float('inf'), x['name']))

    # Write output
    print(f"Saving {len(all_products['norway'])} Norway products, {len(all_products['sweden'])} Sweden products...")
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(all_products, f, indent=2, ensure_ascii=False)

    print(f"Saved to {args.output}")


if __name__ == '__main__':
    main()