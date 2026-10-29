#!/usr/bin/env python3
"""
Food price scraper for Norway vs Sweden dashboard.

Scrapes prices from:
- kassal.app (Norwegian grocery comparison)
- rema.no (Norwegian grocery store)
- nordby.se (Swedish grocery store)
"""

import json
import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

import requests
from bs4 import BeautifulSoup


class PriceScraper:
    """Base scraper class with common utilities."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; HarryHandel/1.0; +https://github.com/turbolego/HarryHandel)'
        })

    def clean_text(self, text: str) -> str:
        """Clean scraped text."""
        return text.strip().replace('\n', ' ').replace('\t', '').strip()

    def fetch_url(self, url: str):
        """Fetch a URL and return BeautifulSoup, or None on error."""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None


class RemaScraper(PriceScraper):
    """Scrape prices from rema.no by extracting embedded JSON data."""

    BASE_URL = "https://www.rema.no"

    def __init__(self):
        super().__init__()

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        """Scrape products from a rema category page by extracting embedded JSON."""
        products = []
        soup = self.fetch_url(category_url)
        if not soup:
            return products

        # Extract JSON data from script tags - rema.no embeds product data
        script_tags = soup.select('script')

        for script in script_tags:
            if script.string:
                try:
                    text = script.string
                    # Look for JSON with product data patterns
                    if '"products"' in text or '"price"' in text or 'id' in text:
                        import json as json_mod
                        try:
                            data = json_mod.loads(text)
                            products_data = self._extract_products_from_json(data)
                            if products_data:
                                products.extend(products_data)
                        except (json_mod.JSONDecodeError, ValueError):
                            continue
                except Exception:
                    continue

        # Also try to find Next.js __NEXT_DATA__
        next_data = soup.find('script', attrs={'id': '__NEXT_DATA__'})
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                products_data = self._extract_products_from_next_data(data)
                if products_data:
                    products.extend(products_data)
            except (json.JSONDecodeError, ValueError):
                pass

        return products

    def _extract_products_from_json(self, data: Any) -> List[Dict[str, Any]]:
        """Extract product data from various JSON structures."""
        products = []

        if isinstance(data, dict):
            for key in ['props', 'pageProps', 'data', 'initialState']:
                if key in data:
                    val = data[key]
                    if isinstance(val, dict):
                        products.extend(self._find_products_in_dict(val))
                    elif isinstance(val, list):
                        products.extend(self._find_products_in_list(val))

            products.extend(self._find_products_in_dict(data))

        return products

    def _extract_products_from_next_data(self, data: dict) -> List[Dict[str, Any]]:
        """Extract from Next.js __NEXT_DATA__ structure."""
        products = []
        props = data.get('props', {})
        page_props = props.get('pageProps', {})
        return self._extract_products_from_json(page_props)

    def _find_products_in_dict(self, data: dict) -> List[Dict[str, Any]]:
        """Recursively find product data in dict."""
        products = []

        if 'name' in data and ('price' in data or 'kroner' in data or 'ore' in data):
            products.append(self._parse_rem_product(data))

        for key, val in data.items():
            if isinstance(val, dict):
                products.extend(self._find_products_in_dict(val))
            elif isinstance(val, list):
                products.extend(self._find_products_in_list(val))

        return products

    def _find_products_in_list(self, data: list) -> List[Dict[str, Any]]:
        """Recursively find product data in list."""
        products = []
        for item in data:
            if isinstance(item, dict):
                products.extend(self._find_products_in_dict(item))
            elif isinstance(item, list):
                products.extend(self._find_products_in_list(item))
        return products

    def _parse_rem_product(self, data: dict) -> Dict[str, Any]:
        """Parse a rema product from embedded JSON."""
        try:
            name = data.get('name', 'Unknown')

            # Price info - rema.no has price as {kroner, ore} or as a string
            price_info = data.get('price', {})
            price_kroner = price_info.get('kroner', 0)
            price_ore = price_info.get('ore', 0)
            price = price_kroner + price_ore / 100  # Convert to decimal

            # Unit text
            unit_text = data.get('unitText', 'per kg')

            # Category
            category = data.get('groupName', 'supermarket')

            # Store
            stores = ['Rema 1000']

            return {
                'name': name,
                'category': category or 'supermarket',
                'stores': stores,
                'price': price if price > 0 else None,
                'currency': 'NOK',
                'unit': unit_text,
                'market': 'rema-norway'
            }
        except Exception as e:
            print(f"Warning: Failed to parse rema product: {e}")
            return {}


class NordbyScraper(PriceScraper):
    """Scrape prices from nordby.se (WordPress site)."""

    BASE_URL = "https://nordby.se"

    def __init__(self):
        super().__init__()

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        """Scrape products from nordby.se category page."""
        products = []
        soup = self.fetch_url(category_url)
        if not soup:
            return products

        # Try to find JSON-LD schema data
        schema_script = soup.find('script', attrs={'type': 'application/ld+json'})
        if schema_script and schema_script.string:
            try:
                data = json.loads(schema_script.string)
                products_data = self._extract_products_from_ld_json(data)
                if products_data:
                    products.extend(products_data)
            except (json.JSONDecodeError, ValueError):
                pass

        # Also look for inline product data in script tags
        for script in soup.select('script'):
            if script.string and ('product' in script.string.lower() or 'pris' in script.string.lower()):
                try:
                    data = json.loads(script.string)
                    products_data = self._extract_from_ld_json_script(data)
                    if products_data:
                        products.extend(products_data)
                except (json.JSONDecodeError, ValueError):
                    continue

        return products

    def _extract_products_from_ld_json(self, data: Any) -> List[Dict[str, Any]]:
        """Extract from JSON-LD structured data."""
        products = []

        if isinstance(data, dict):
            if '@type' in data and data.get('@type') == 'Product':
                products.append(self._parse_nordby_product(data))
            else:
                for key, val in data.items():
                    if isinstance(val, (dict, list)):
                        products.extend(self._extract_products_from_ld_json(val))

        elif isinstance(data, list):
            for item in data:
                products.extend(self._extract_products_from_ld_json(item))

        return products

    def _extract_from_ld_json_script(self, data: Any) -> List[Dict[str, Any]]:
        """Extract from inline JSON-LD script tags."""
        return self._extract_products_from_ld_json(data)

    def _parse_nordby_product(self, data: dict) -> Dict[str, Any]:
        """Parse a nordby product from JSON-LD data."""
        try:
            name = data.get('name', 'Unknown')

            # Price - could be in various formats
            offers = data.get('offers', {})
            price = None
            if offers:
                price_str = offers.get('price')
                if price_str:
                    try:
                        price = float(price_str)
                    except (ValueError, TypeError):
                        price = None

            # Currency
            currency = offers.get('priceCurrency', 'SEK')

            return {
                'name': name,
                'category': 'supermarket',
                'stores': ['Nordby'],
                'price': price,
                'currency': currency,
                'unit': 'per kg',
                'market': 'nordby-sweden'
            }
        except Exception as e:
            print(f"Warning: Failed to parse nordby product: {e}")
            return {}


class KassalScraper(PriceScraper):
    """Scrape prices from kassal.app.

    Note: kassal.app is a React/Livewire app. Data is loaded dynamically.
    This scraper extracts any embedded data references.
    """

    BASE_URL = "https://kassal.app"

    def __init__(self):
        super().__init__()

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        """Scrape kassal.app - extracts embedded data references."""
        products = []
        soup = self.fetch_url(category_url)
        if not soup:
            return products

        # Look for Livewire component data or API references
        for script in soup.select('script'):
            if script.string and ('api' in script.string.lower() or 'livewire' in script.string.lower()):
                try:
                    text = script.string
                    # Look for price patterns in the script content
                    prices = re.findall(r'"\d+[\d,.]*"', text)
                    for p in prices[:5]:
                        cleaned = p.replace('"', '').replace(',', '.')
                        try:
                            price_val = float(cleaned)
                            products.append({
                                'name': 'Kassal Product',
                                'category': 'unknown',
                                'stores': ['Kassal'],
                                'price': price_val,
                                'currency': 'NOK',
                                'unit': 'per item',
                                'market': 'kassal'
                            })
                        except ValueError:
                            continue
                except Exception:
                    continue

        return products


def main():
    parser = argparse.ArgumentParser(description='Scrape food prices and save to JSON')
    parser.add_argument('--output', default='data/prices.json', help='Output JSON file path')
    args = parser.parse_args()

    output_dir = Path(args.output).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    scrapers = [
        RemaScraper(),
        NordbyScraper(),
        KassalScraper(),
    ]

    all_products = {
        'last_updated': datetime.utcnow().isoformat(),
        'norway': [],
        'sweden': []
    }

    # Scrape from all sources
    print("Scraping rema.no (Norwegian grocery)...")
    rema_products = []
    rema_url = "https://www.rema.no/inspirasjon/sesong-og-matlyst/nyhetsvindu/"
    rema_products = RemaScraper().scrape_category(rema_url)
    all_products['norway'].extend(rema_products)
    print(f"  Found {len(rema_products)} products from rema.no")

    print("Scraping nordby.se (Swedish grocery)...")
    nordby_products = []
    nordby_url = "https://nordby.se/"
    nordby_products = NordbyScraper().scrape_category(nordby_url)
    all_products['sweden'].extend(nordby_products)
    print(f"  Found {len(nordby_products)} products from nordby.se")

    print("Scraping kassal.app (Norwegian comparison)...")
    kassal_products = []
    kassal_url = "https://kassal.app/"
    kassal_products = KassalScraper().scrape_category(kassal_url)
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