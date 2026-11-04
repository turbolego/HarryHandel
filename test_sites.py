#!/usr/bin/env python3
"""Test ICA.se and other grocery sites for price scraping feasibility."""

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re, json

def fetch_html(url, timeout=60000):
    # Existing fetch_html function

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout)
            html = page.content()
            browser.close()
            return html
    except Exception as e:
        return f"ERROR: {e}"

def analyze(url, label):
    print(f"\n{'='*60}")
    print(f"Testing {label}: {url}")
    print('='*60)
    html = fetch_html(url)
    if isinstance(html, str) and html.startswith("ERROR"):
        print(html)
        return None
    
    soup = BeautifulSoup(html, 'html.parser')
    print(f"HTML size: {len(html)}")
    
    # Find price-like patterns
    prices = re.findall(r'[\d,]+\s*(?:kr|sek)', html[:100000])
    print(f"Price patterns (first 10): {prices[:10]}")
    
    # Find product card classes
    cards = soup.select('[class*="product"], [class*="card"], [class*="item"]')
    print(f"Product-like elements: {len(cards)}")
    
    # Find price elements
    price_elems = soup.select('[class*="price"], [class*="pris"]')
    print(f"Price elements: {len(price_elems)}")
    if price_elems:
        for e in price_elems[:5]:
            print(f"  {e.get('class')}: {e.get_text(strip=True)[:50]}")
    
    # Find any product names
    names = soup.select('[class*="name"], [class*="title"], [class*="product"]')
    print(f"Name/title elements: {len(names)}")
    if names:
        for e in names[:5]:
            txt = e.get_text(strip=True)[:50]
            print(f"  {e.name} class={e.get('class')} text={txt!r}")
    
    # Save for inspection
    with open(f"/tmp/{label.replace(' ', '_')}.html", "w") as f:
        f.write(html)
    print(f"Saved to /tmp/{label.replace(' ', '_')}.html")
    
    # Look for API endpoints or JSON data
    api_calls = re.findall(r'https?://[^\s"\'<>]*api[^\s"\'<>]*', html)
    if api_calls:
        print(f"API endpoints found: {list(set(api_calls))[:5]}")
    
    return html



def test_modal_popup():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://turbolego.github.io/HarryHandel/", wait_until="networkidle")
        # Wait for the first history button to be present
        page.wait_for_selector("button[onclick*='openPairHistoryModal']")
        page.click("button[onclick*='openPairHistoryModal']")
        # Verify the modal is displayed (display should be 'flex')
        display = page.eval_on_selector("#pair-history-modal", "el => getComputedStyle(el).display")
        print("Modal display:", display)
        browser.close()

results = {}

# Sweden - ICA (main)
results['ica'] = analyze('https://www.ica.se/', 'ICA Sweden')

# Sweden - Willys/Hemköp (Coop group)
results['coop_se'] = analyze('https://www.coop.se/', 'Coop Sweden')

# Norway - Kiwi
results['kiwi'] = analyze('https://www.kiwi.no/', 'Kiwi Norway')

# Norway - Meny
results['meny'] = analyze('https://www.meny.no/', 'Meny Norway')

# Norway - Spar
results['spar_no'] = analyze('https://www.spar.no/', 'Spar Norway')

# Also check if any have product categories
print("\n" + "="*60)
print("Summary")
print("="*60)
for k, v in results.items():
    print(f"{k}: {'OK' if isinstance(v, str) else 'FAILED'}")
# Run modal popup test
test_modal_popup()

