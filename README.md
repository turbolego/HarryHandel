# HarryHandel
[https://turbolego.github.io/PlogeKart/](https://turbolego.github.io/PlogeKart/)

## Overview

HarryHandel is a GitHub Pages dashboard that compares food prices in Norway vs Sweden. The project scrapes price data from:

- **kassal.app** - Norwegian grocery price comparison
- **rema.no** - Norwegian grocery store (Rema 1000)
- **nordby.se** - Swedish grocery store

## Data Structure

The scraped data is saved as JSON at `data/prices.json` with the following structure:

```json
{
  "last_updated": "2026-10-29T08:52:35.499904",
  "norway": [
    {
      "name": "Product name",
      "category": "Category",
      "stores": ["Store names"],
      "price": 12.50,
      "currency": "NOK",
      "unit": "per kg",
      "market": "source-name"
    }
  ],
  "sweden": [
    {
      "name": "Product name",
      "category": "Category",
      "stores": ["Store names"],
      "price": 11.50,
      "currency": "SEK",
      "unit": "per kg",
      "market": "source-name"
    }
  ]
}
```

## GitHub Actions Workflow

The `.github/workflows/scrape.yml` workflow:

- **Schedule**: Runs every Sunday at 2 AM UTC
- **Trigger**: Can also be run manually via workflow dispatch
- **Process**:
  1. Checks out the repository
  2. Sets up Python 3.11
  3. Installs dependencies (requests, beautifulsoup4, pandas)
  4. Runs the scraper (`src/scrapers/main.py`)
  5. Generates fallback demo data if no products found
  6. Commits and pushes any changes to `main` branch

## Local Development

```bash
# Run the scraper
cd src && python3 -m scrapers.main

# Generate fallback data
python3 generate_fallback_data.py
```

## Scrapers

- **RemaScraper**: Extracts embedded JSON data from rema.no product pages
- **NordbyScraper**: Extracts JSON-LD structured data from nordby.se
- **KassalScraper**: Extracts any embedded data references from kassal.app

## Dashboard

The dashboard at `index.html` displays:
- Price comparison chart (Chart.js)
- Product table with Norway/Sweden prices
- Statistics (averages, price gaps)
- Filter by category and search

## Adding New Scrapers

Add new scraper classes in `src/scrapers/` following the `PriceScraper` base class pattern. The `main()` function in `src/scrapers/main.py` should be updated to instantiate and run the new scraper.

## Note on Data Sources

The target websites (kassal.app, rema.no, nordby.se) are primarily JavaScript-rendered applications. The current scrapers extract embedded JSON data where available. For full data coverage, consider:

- Using the sites' official APIs if available
- Implementing headless browser scraping (Playwright/Selenium)
- Partnering with the sites for data access