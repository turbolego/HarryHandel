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
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
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
                    price = recover_price(float(price_str))
                    if price is None:
                        continue
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
                # Plausibility: grocery items cost between 0.50 and 9999.99 NOK.
                # Rejects negatives (misparsed discounts), concatenated text
                # like "249024.9" and other scraping artifacts.
                if not (0.0 < price <= 9999.99):
                    continue
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



class KassalProductFetcher(PriceScraper):
    """Fetch the common product list from kassal.app/varer.
    
    Kassal maintains a unified product database for Norway.  The page at
    /varer lists every product with its name, supplier, and links to
    price comparisons.  We extract the name so that Norway and Sweden
    products can be matched by exact equality (like svenskegrensen.no does).
    """

    BASE_URL = "https://kassal.app"

    def fetch_product_names(self) -> List[str]:
        """Fetch all product names from the Kassal product list."""
        soup = self.fetch_page("https://kassal.app/varer")
        if not soup:
            return []

        product_names = []
        for link in soup.select('a[href*="/vare/"]'):
            href = link.get('href', '')
            if href.startswith('https://'):
                path = href.split('/vare/')[-1]
            else:
                path = href
            m = re.match(r'(\d+)-(.+)$', path)
            if m:
                name = m.group(2).replace('-', ' ').strip()
                if name and len(name) > 3 and len(name) < 80:
                    name = name[0].upper() + name[1:]
                    product_names.append(name)

        seen = set()
        unique = []
        for n in product_names:
            if n not in seen:
                seen.add(n)
                unique.append(n)

        print(f"  {len(unique)} products fetched from Kassal product list")
        return unique


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



class WillyScraper(PriceScraper):
    """Scrape prices from willys.se using Playwright.

    Each product card carries data-testid="product" + itemscope.  The name is
    in itemprop="name"; the per-unit comparison price is inline text
    "Jmf-pris XX,XX kr/unit" (e.g. "Jmf-pris 43,75 kr/kg").
    """

    BASE_URL = "https://willys.se"

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        soup = self.fetch_page(category_url)
        if not soup:
            return []

        products = []
        prod_cards = soup.select('[data-testid="product"][itemscope]')
        print(f"  {len(prod_cards)} product cards found on willys.se")

        for card in prod_cards:
            try:
                name_el = card.select_one('[itemprop="name"]')
                name = self.clean_text(name_el.get_text(strip=True)) if name_el else ""
                if not _name_is_plausible(name):
                    continue

                jmf_match = re.search(
                    r'Jmf-pris\s+(\d+[\d,]*)\s*kr/?\s*([a-z]+)', card.get_text()
                )
                if not jmf_match:
                    continue

                price = float(jmf_match.group(1).replace(',', '.'))
                unit = jmf_match.group(2).strip() or 'per item'

                if not _price_is_plausible(price):
                    continue

                products.append({
                    'name': name,
                    'category': 'supermarket',
                    'stores': ['Willys'],
                    'price': price,
                    'currency': 'SEK',
                    'unit': unit,
                    'market': 'willys-sweden'
                })
            except Exception as e:
                print(f"  Warning: Failed to parse Willy's product: {e}")

        return products


class MenyScraper(PriceScraper):
    """Scrape prices from meny.no (Norwegian grocery).

    Product cards are <div class="ws-product-vertical" itemscope
    itemtype="http://schema.org/Product">.  The name lives in an h3 with
    itemprop="name" plus an optional p.subtitle; the price is an
    aria-label of the form "Tilbud, nå 10,00 kroner." on
    .ws-price__main (with "Før 15,90 kroner" as the compare price).
    """

    BASE_URL = "https://www.meny.no"

    def scrape_category(self, category_url: str) -> List[Dict[str, Any]]:
        soup = self.fetch_page(category_url)
        if not soup:
            return []

        products = []
        cards = soup.select('.ws-product-vertical')
        print(f"  {len(cards)} product cards found on {category_url.split('/')[-2] if len(category_url.split('/')) > 2 else 'meny.no'}")

        for card in cards:
            try:
                title_el = card.select_one('h3.ws-product-vertical__title')
                sub_el = card.select_one('p.ws-product-vertical__subtitle')
                title = self.clean_text(title_el.get_text(strip=True)) if title_el else ""
                sub = self.clean_text(sub_el.get_text(strip=True)) if sub_el else ""
                name = (title + " " + sub).strip()
                if not _name_is_plausible(name):
                    continue

                price = None
                unit = 'per st'

                # Preferred: aria-label "Tilbud, nå 10,00 kroner."
                main_el = card.select_one('strong[class*="ws-price__main"]')
                if main_el is not None:
                    aria = main_el.get('aria-label') or ''
                    m = re.search(r'nå\s+([\d,.]+)\s+kroner', aria)
                    if m:
                        price = float(m.group(1).replace('.', '').replace(',', '.'))
                    else:
                        # Fall back to the rendered text: "10,00 kr"
                        text = main_el.get_text(strip=True).replace('kr', '').replace('\xa0', ' ').strip()
                        m2 = re.search(r'([\d,.]+)', text)
                        if m2:
                            price = float(m2.group(1).replace('.', '').replace(',', '.'))

                if price is None or not _price_is_plausible(price):
                    continue

                products.append({
                    'name': name,
                    'category': 'supermarket',
                    'stores': ['Meny'],
                    'price': price,
                    'currency': 'NOK',
                    'unit': unit,
                    'market': 'meny-norway'
                })
            except Exception as e:
                print(f"  Warning: Failed to parse Meny product: {e}")

        return products


class KassalApiScraper:
    """Fetch Norwegian prices from the Kassalapp REST API.

    Uses the KASSALAPP_TOKEN GitHub secret (Authorization: Bearer).  The API
    gives the shared product catalog every chain lists under one EAN, so one
    search + one bulk call yields the same product priced in every Norwegian
    chain (Kiwi, Meny, Rema, Oda, ...) — exactly the shared-catalogue method
    svenskegrensen.no uses to compare Norway vs Sweden.

    Hobby plan: 60 requests/minute.  We pace requests at >= 1.1s and retry
    429s with backoff.  The token is never printed or written anywhere.
    """

    BASE = "https://kassal.app/api/v1"
    MAX_EANS = 100          # prices-bulk limit
    PAUSE = 1.1             # seconds between requests
    # Basket terms covering the comparable items (bacon, cola, chocolate...)
    BASKET = [
        'bacon', 'cola', 'melkesjokolade', 'chips', 'energidrikk',
        'smågodt', 'egg', 'smør', 'gullmelk', 'grovbrød', 'kaffe',
        'kjøttdeig', 'lettmelk', 'appelsinjuice', 'salami', 'kjeks',
    ]

    def __init__(self, token: str | None = None):
        # Read from env; the workflow injects the GitHub secret as env.
        self.token = token if token is not None else os.environ.get('KASSALAPP_TOKEN', '')

    def _request(self, method: str, path: str, payload=None, timeout=30):
        """One authenticated request.  Returns parsed JSON or None."""
        url = f"{self.BASE}/{path}"
        data = json.dumps(payload).encode('utf-8') if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header('Authorization', f'Bearer {self.token}')
        req.add_header('Accept', 'application/json')
        if data is not None:
            req.add_header('Content-Type', 'application/json')

        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode('utf-8', errors='replace')
                    return json.loads(body) if body else {}
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = 15 * (attempt + 1)
                    print(f"  Rate limited (429), sleeping {wait}s...")
                    time.sleep(wait)
                    continue
                detail = ''
                if 400 <= e.code < 500:
                    try:
                        body = e.read().decode('utf-8', errors='replace')
                        # Validation message only; never headers or the token.
                        detail = ' ' + body[:300].replace('\n', ' ')
                    except Exception:
                        pass
                print(f"  Kassal API {method} {path} -> HTTP {e.code} (skipping){detail}")
                return None
            except Exception as e:
                print(f"  Kassal API {method} {path} failed: {type(e).__name__}")
                if attempt < 2:
                    time.sleep(5)
                    continue
                return None
        return None

    def _collect_eans(self) -> List[Dict[str, Any]]:
        """Run basket searches and collect unique EAN'd products."""
        picks = []
        seen = set()
        for term in self.BASKET:
            if len(picks) >= self.MAX_EANS:
                break
            # Documented plain params only: optional boolean flags (422 risk)
            # are handled client-side instead.
            qs = urllib.parse.urlencode({'search': term, 'size': 10})
            resp = self._request('GET', f'products?{qs}')
            time.sleep(self.PAUSE)
            if not resp:
                continue
            for item in (resp.get('data') or []):
                ean = item.get('ean')
                price = item.get('current_price')
                if not ean or ean in seen:
                    continue
                if not _price_is_plausible(price):
                    continue
                seen.add(ean)
                picks.append({
                    'ean': ean,
                    'name': item.get('name'),
                    'weight': item.get('weight'),
                    'weight_unit': item.get('weight_unit'),
                    'term': term,
                })
                if len(picks) >= self.MAX_EANS:
                    break
        print(f"  {len(picks)} EANs collected from {len(self.BASKET)} searches")
        return picks

    def _fetch(self) -> List[Dict[str, Any]]:
        picks = self._collect_eans()
        if not picks:
            return []

        # One bulk call gives current prices for every chain stocking them.
        resp = self._request(
            'POST', 'products/prices-bulk',
            payload={'eans': [p['ean'] for p in picks], 'days': 7},
            timeout=60,
        )
        time.sleep(self.PAUSE)
        if not resp:
            print("  Kassal bulk price call failed - no Kassal API products")
            return []

        ean_info = {p['ean']: p for p in picks}
        products = []
        items = resp.get('data', resp if isinstance(resp, list) else [])
        for item in items:
            info = ean_info.get(item.get('ean'), {})
            name = (info.get('name') or item.get('name') or '').strip()
            if not _name_is_plausible(name):
                continue
            # current_price is the package price (kilopris arrives separately
            # as current_unit_price in the API), so label rows "per item" —
            # the package size is already part of the product name.
            unit = 'per item'
            rows = []
            for store in (item.get('stores') or []):
                if _price_is_plausible(store.get('current_price')):
                    rows.append((store.get('store'), store.get('name'),
                                 float(store['current_price'])))

            if not rows:
                # Most bulk responses carry chain prices only in price_history
                # entries {price, date, store}: keep the newest observation
                # per chain code.
                latest_by_store = {}
                for point in (item.get('price_history') or []):
                    code = point.get('store')
                    if not code or not _price_is_plausible(point.get('price')):
                        continue
                    prev = latest_by_store.get(code)
                    if prev is None or (point.get('date') or '') >= prev[1]:
                        latest_by_store[code] = (float(point['price']), point.get('date') or '')
                rows = [(code, None, price) for code, (price, _) in latest_by_store.items()]

            for code, store_name, price in rows:
                store_name = (store_name or code or '').strip()
                code = (code or 'unknown').lower()
                products.append({
                    'name': name,
                    'category': info.get('term', 'supermarket'),
                    'stores': [store_name] if store_name else ['Kassal'],
                    'price': float(price),
                    'currency': 'NOK',
                    'unit': unit,
                    'market': f'kassal-{code}',
                })
        if not products:
            # Diagnostic (product data only, never headers/token):
            sample = items[0] if items else {}
            st = (sample.get('stores') or [])
            ph = (sample.get('price_history') or [])
            with_stores = sum(1 for it in items if it.get('stores'))
            print(f"  debug: items={len(items)} with_stores={with_stores} "
                  f"item_keys={sorted(sample.keys())} stores={len(st)} "
                  f"history_sample={ph[:2]} sample_name={sample.get('name')}")
        print(f"  {len(products)} chain prices from Kassal API ({len(items)} EANs compared)")
        return products

    def scrape(self) -> List[Dict[str, Any]]:
        """Returns [] quietly when the token is absent (local runs)."""
        if not self.token:
            print("KASSALAPP_TOKEN not set - skipping Kassal API")
            return []
        return self._fetch()

def load_existing_data(output_path: Path) -> Dict[str, Any]:
    """Load existing price data from file."""
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Strip junk entries left by earlier scrapes (e.g. "%", "kr",
            # "för -" promotion fragments that got saved as product names).
            for country in ('norway', 'sweden'):
                kept = [p for p in data.get(country, [])
                        if _name_is_plausible(p.get('name'))]
                data[country] = kept
            return data
        except Exception as e:
            print(f"Warning: Could not load existing data: {e}")
    return {'norway': [], 'sweden': []}


def normalize_name(name: str) -> str:
    """Normalize product name for matching."""
    return re.sub(r'\s+', ' ', name.lower()).strip()

def _price_is_plausible(price) -> bool:
    """Reject null, negative, zero and absurd prices from any source."""
    return isinstance(price, (int, float)) and 0.0 < float(price) <= 9999.99


_JUNK_NAME_FRAGMENTS = (
    '% vid köp', 'för -', 'populära varor', 'se våra', 'massor av',
    'börja firandet', 'bus eller', 'blir det', 'köp fler', 'läskigt',
    'veckans erbjudanden', 'hoppa till', 'hoppa över', 'visa fler sorter',
    'gjelder til', 'reklamblad',
)


def _name_is_plausible(name) -> bool:
    """Reject promotion text, headings and price fragments as product names.

    Fallback name extraction can emit "%", "kr", "pk" or "för -" — none of
    which are products.  Require a real word and block known page chrome.
    """
    if not isinstance(name, str):
        return False
    cleaned = name.strip()
    if len(cleaned) < 3 or len(cleaned) > 120:
        return False
    if cleaned.lower() in ('unknown', 'none', 'null', '-'):
        return False
    lowered = cleaned.lower()
    if any(frag in lowered for frag in _JUNK_NAME_FRAGMENTS):
        return False
    # Require at least two consecutive letters (a real word).
    return bool(re.search(r'[A-Za-zÀ-ÿ]{2,}', cleaned))


def recover_price(price):
    """Fix rema.no øre-concatenated prices like 399039.9 (ore + '39,90 kr').

    The composite is str(round(kr*100)) + kr-text, e.g. 39.90 kr renders as
    "3990" + "39,90" = 399039,90 -> parsed float 399039.9.  The real value is
    recoverable because the prefix must equal round(real*100).  Returns the
    recovered float, or None if the value is already fine / un-recoverable.
    """
    if _price_is_plausible(price):
        return float(price)
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        return None
    s = repr(float(price))
    if '.' not in s:
        return None
    # Try every split: suffix = real price text (e.g. '39.9'), prefix = øre part
    for i in range(1, len(s) - 2 + 1):
        prefix, suffix = s[:i], s[i:]
        if not prefix or not suffix[0].isdigit():
            continue
        if '.' not in suffix or suffix.startswith('.'):
            continue
        try:
            cand = float(suffix)
        except ValueError:
            continue
        if cand <= 0 or cand > 9999.99:
            continue
        if str(int(round(cand * 100))) == prefix:
            return cand
    return None


def merge_products(existing: List[Dict], new_products: List[Dict], country: str) -> List[Dict]:
    """Merge new products into existing list, preserving history."""
    kept = []
    for p in new_products:
        if not _name_is_plausible(p.get('name')):
            continue
        if _price_is_plausible(p.get('price')):
            kept.append(p)
            continue
        fixed = recover_price(p.get('price'))
        if fixed is not None:
            p['price'] = fixed
            kept.append(p)
    new_products = kept

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

    # Fetch Kassal product list for name matching (like svenskegrensen.no)
    print("Fetching Kassal product list for name matching...")
    kassal_fetcher = KassalProductFetcher()
    kassalProductNames = kassal_fetcher.fetch_product_names()

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

    print("Scraping meny.no (Norwegian grocery promotions)...")
    meny_products = MenyScraper().scrape_category("https://www.meny.no/kampanjer/")
    all_products['norway'].extend(meny_products)
    print(f"  Found {len(meny_products)} products from meny.no")

    # nordby.se's homepage lists DEALS across all categories (knitwear,
    # pharmacy, etc.) with promotion text that can't be parsed as prices and
    # yields junk product names.  Disabled until a real grocery category page
    # is found; curated Swedish entries in data/prices.json are preserved.
    # Kassal API chain prices: one shared catalog across Norwegian chains
    # (set KASSALAPP_TOKEN in repo secrets to enable).
    print("Scraping Kassal API (chain prices)...")
    kassal_products = KassalApiScraper().scrape()
    all_products['norway'].extend(kassal_products)
    print(f"  Found {len(kassal_products)} products from Kassal API")

    print("Skipping nordby.se (homepage is deals, not groceries)")

    # kassal.app's homepage shows price CHANGES (deltas like "-42.00"), not
    # actual prices, so scraping it pollutes the data.  Disabled on purpose.
    print("Skipping kassal.app (homepage lists price deltas, not prices)")

    # ICA Sweden's homepage has no grocery product cards — their price
    # display is entirely JS-rendered with no server-side price HTML.
    # Use Willy's instead, which shows Jmf-pris (comparison price per unit).
    print("Scraping willys.se (Swedish grocery)...")
    willy_products = WillyScraper().scrape_category("https://willys.se/")
    all_products['sweden'].extend(willy_products)
    print(f"  Found {len(willy_products)} products from willys.se")

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