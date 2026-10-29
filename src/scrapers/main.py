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
                # Wait for price-like elements to appear
                page.wait_for_selector("[data-qa*='price'], .price, [class*='price']", timeout=15000)
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

        # Extract from product cards
        product_cards = soup.select('[data-qa="product"]')
        if not product_cards:
            product_cards = soup.select('.ProductCard')

        for card in product_cards:
            try:
                product = self._parse_rem_product(card)
                if product:
                    products.append(product)
            except Exception as e:
                print(f"Warning: Failed to parse rema product: {e}")

        return products

    def _parse_rem_product(self, card: BeautifulSoup) -> Dict[str, Any]:
        """Parse a rema product from BeautifulSoup element."""
        try:
            # Product name
            name_elem = card.select_one('.ProductName, a[class*="product-name"]')
            name = self.clean_text(name_elem.text) if name_elem else "Unknown"

            # Price
            price_elem = card.select_one('.Price, span[class*="price"]')
            price = None
            if price_elem:
                price_text = self.clean_text(price_elem.text)
                match = re.search(r'(\d+[\d,]*\.?\d*)', price_text)
                if match:
                    price = float(match.group(1).replace(',', '.'))

            # Unit weight
            unit_elem = card.select_one('.UnitWeight, span[class*="weight"]')
            unit = self.clean_text(unit_elem.text) if unit_elem else "per kg"

            return {
                'name': name,
                'category': 'supermarket',
                'stores': ['Rema 1000'],
                'price': price,
                'currency': 'NOK',
                'unit': unit,
                'market': 'rema-norway'
            }
        except Exception as e:
            print(f"Warning: Failed to parse rema product: {e}")
            return {}


class NordbyScraper(PriceScraper):
    """Scrape prices from nordby.se using Playwright."""

    BASE_URL = "https://nordby.se"

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        """Scrape products from nordby.se category page."""
        soup = self.fetch_page(category_url)
        if not soup:
            return []

        products = []

        # Look for product rows/sections
        product_rows = soup.select('tr[class*="product"]')
        if not product_rows:
            product_rows = soup.select('[data-qa="product-row"]')
        if not product_rows:
            product_rows = soup.select('.Shelf .Product')

        for row in product_rows:
            try:
                parsed = self._parse_nordby_product(row)
                if parsed:
                    products.append(parsed)
            except Exception as e:
                print(f"Warning: Failed to parse nordby product: {e}")

        return products

    def _parse_nordby_product(self, row: BeautifulSoup) -> Dict[str, Any]:
        """Extract product data from nordby product element."""
        try:
            # Product name
            name_elem = row.select_one('a, h3')
            name = self.clean_text(name_elem.text) if name_elem else "Unknown"

            # Price
            price_elem = row.select_one('[class*="price"], span[class*="kr"]')
            price = None
            if price_elem:
                price_text = self.clean_text(price_elem.text)
                match = re.search(r'(\d+[\d,]*\.?\d*)', price_text)
                if match:
                    price = float(match.group(1).replace(',', '.'))

            return {
                'name': name,
                'category': 'supermarket',
                'stores': ['Nordby'],
                'price': price,
                'currency': 'SEK',
                'unit': 'per kg',
                'market': 'nordby-sweden'
            }
        except Exception as e:
            print(f"Warning: Failed to parse nordby product: {e}")
            return {}


class KassalScraper(PriceScraper):
    """Scrape prices from kassal.app using Playwright."""

    BASE_URL = "https://kassal.app"

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        """Scrape kassal.app - JS rendered, extract any available data."""
        soup = self.fetch_page(category_url)
        if not soup:
            return []

        products = []

        # Look for product cards or data in script tags
        product_cards = soup.select('[data-qa="product-card"]')
        if not product_cards:
            product_cards = soup.select('.product-card')

        for card in product_cards:
            try:
                parsed = self._parse_kassal_product(card)
                if parsed:
                    products.append(parsed)
            except Exception as e:
                print(f"Warning: Failed to parse kassal product card: {e}")

        return products

    def _parse_kassal_product(self, card: BeautifulSoup) -> Dict[str, Any]:
        """Parse a kassal product card."""
        try:
            # Product name
            name_elem = card.select_one('[data-qa="product-name"]')
            name = self.clean_text(name_elem.text) if name_elem else "Unknown"

            # Price
            price_elem = card.select_one('[data-qa="price"]')
            price = None
            if price_elem:
                price_text = self.clean_text(price_elem.text)
                match = re.search(r'(\d+[\d,]*\.?\d*)', price_text)
                if match:
                    price = float(match.group(1).replace(',', '.'))

            # Unit
            unit_elem = card.select_one('[data-qa="unit"]')
            unit = self.clean_text(unit_elem.text) if unit_elem else "per item"

            return {
                'name': name,
                'category': 'unknown',
                'stores': ['Kassal'],
                'price': price,
                'currency': 'NOK',
                'unit': unit,
                'market': 'kassal'
            }
        except Exception as e:
            print(f"Warning: Failed to parse kassal product: {e}")
            return {}


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