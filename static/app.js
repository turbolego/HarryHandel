let allPrices = { norway: [], sweden: [] };
let chart = null;
// Fuzzy-matched NO/SE pairs (per-unit SEK prices) computed by updateDisplay();
// consumed by updateChart() so the chart always mirrors the table's matches.
let CHART_PAIRS = [];

// Exchange rates (approximate, updated in workflow)
const FX_RATES = {
    NOK: 1,
    SEK: 0.90,
    USD: 0.09,
    EUR: 0.085
};

// Product groups for collapsible sections
// Each group has: name (display), keywords (match either country's product names),
// and an optional filterFn for complex logic (e.g. butter but NOT margarine)
const PRODUCT_GROUPS = [
    {
        name: "Butter",
        keywords: ["smör", "smør", "meierismør"],
        filterFn: (p) => !/margarin/i.test(p.name) && !/smörolja|raps.?smör/i.test(p.name)
    },
    {
        name: "Energy drinks",
        keywords: ["red bull", "redbull", "energidryck", "energy drink"]
    },
    {
        name: "Margarine & oils",
        keywords: ["margarin", "smörolja", "raps.?smör", "flytande"],
        filterFn: (p) => /margarin|smörolja|raps.?smör|flytande/i.test(p.name)
    },
    {
        name: "Milk & cream",
        keywords: ["mjölk", "melk", "grädde", "fløyte", "grädd"]
    },
    {
        name: "Cheese",
        keywords: ["ost", "färskost", "ferskost"]
    },
    {
        name: "Bread",
        keywords: ["bröd", "brød"]
    },
    {
        name: "Meat & charcuterie",
        keywords: ["skinka", "skinke", "korv", "pølse", "färs", "kjøtt", "kött"]
    },
    {
        name: "Fruit & veg",
        keywords: ["banan", "äpple", "eple", "apelsin", "appelsin", "gurka", "agurk", "morötter", "gulrot", "lök", "løk", "tomater", "sallad", "salat", "broccoli", "brokoli"]
    },
    {
        name: "Coffee & tea",
        keywords: ["kaffe", "te", "zoegas"]
    },
    {
        name: "Snacks & sweets",
        keywords: ["chips", "godis", "sjokolade", "sukker", "kex", "kiks"]
    }
];

// Which group a product belongs to (first match wins)
function getProductGroup(product) {
    if (!product || !product.name) return null;
    const name = product.name.toLowerCase();
    for (const g of PRODUCT_GROUPS) {
        if (g.keywords.some(kw => name.includes(kw.toLowerCase()))) {
            if (g.filterFn && !g.filterFn(product)) continue;
            return g.name;
        }
    }
    return null;
}

// Get the most comparable price for a product (per-unit normalized).
// Returns { value, unit } where unit is "per 100ml", "per kg", "per piece", or "".
function comparablePrice(p) {
    if (p.price_per_100ml) return { value: p.price_per_100ml, unit: "per 100ml" };
    if (p.price_per_kg)    return { value: p.price_per_kg,    unit: "per kg" };
    if (p.price_per_piece) return { value: p.price_per_piece,  unit: "per piece" };
    return { value: p.price, unit: "" };
}

// Display price cell: raw price + normalized sub-label if available
function priceCell(p) {
    if (!p) return '<td class="numeric">—</td>';
    const cp = comparablePrice(p);
    const sub = cp.unit
        ? `<span class="price-sub">${cp.value.toFixed(2)} ${cp.unit.replace("per ", "")}</span>`
        : '';
    return `<td class="numeric">${p.price.toFixed(2)}<br>${sub}</td>`;
}

// Sub-label for a price cell: shows pack qty + per-unit price when available
function _priceSubLabel(p) {
    if (!p) return '';
    let parts = [];
    if (p.quantity && p.quantity > 1) {
        parts.push(`${p.quantity}×`);
    }
    const cp = comparablePrice(p);
    if (cp.unit) {
        parts.push(`${cp.value.toFixed(2)}/${cp.unit.replace("per ", "")}`);
    }
    return parts.length ? `<span class="price-sub">${parts.join(' ')}</span>` : '';
}

// Generate a tiny sparkline SVG from history array [{date, price}]
function generateSparkline(history) {
    if (!history || history.length < 2) return '';
    const prices = history.map(h => h.price);
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;
    const width = 80;
    const height = 20;
    const padding = 2;
    const points = history.map((h, i) => {
        const x = padding + (i / (history.length - 1)) * (width - 2 * padding);
        const y = height - padding - ((h.price - min) / range) * (height - 2 * padding);
        return `${x},${y}`;
    }).join(' ');
    const svg = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <polyline fill="none" stroke="var(--accent)" stroke-width="1.5" points="${points}"/>
    </svg>`;
    return svg;
}

// ----- 1. Load prices from the data file -----
async function loadPrices() {
    try {
        const response = await fetch("/HarryHandel/data/prices.json");
        allPrices = await response.json();

        // Sanity guard: drop scraper artifacts (negative, zero or absurd
        // prices) so one bad feed can never wreck the dashboard.
        const plausible = (p) => typeof p.price === "number" && p.price > 0 && p.price <= 9999.99;
        allPrices.norway = (allPrices.norway || []).filter(plausible);
        allPrices.sweden = (allPrices.sweden || []).filter(plausible);

        updateDisplay();
        initCategories();
        setupChartControls();
        setupTableControls();
    } catch (error) {
        console.error("Failed to load prices:", error);
        const lastUpdated = document.getElementById("last-updated");
        if (lastUpdated) lastUpdated.textContent = "Failed to load data";
    }
}

// ----- 2. Update the UI display -----
function updateDisplay() {
    // Update display with proper date formatting
    const dateStr = allPrices.last_updated ? new Date(allPrices.last_updated).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "—";
    const lastUpdatedEl = document.getElementById("last-updated");
    if (lastUpdatedEl) lastUpdatedEl.textContent = dateStr;

    // --- Meta stats ---
    const norwayCount = document.getElementById("norway-count");
    const swedenCount = document.getElementById("sweden-count");
    if (norwayCount) norwayCount.textContent = allPrices.norway.length;
    if (swedenCount) swedenCount.textContent = allPrices.sweden.length;

    // --- Price gap ---
    const nokPrices = allPrices.norway.map((p) => p.price).filter((p) => p != null);
    const sekPrices = allPrices.sweden.map((p) => p.price).filter((p) => p != null);
    const avgNOK = nokPrices.length ? nokPrices.reduce((a, b) => a + b, 0) / nokPrices.length : 0;
    const avgSEK = sekPrices.length ? sekPrices.reduce((a, b) => a + b, 0) / sekPrices.length : 0;
    const avgNOK_in_SEK = avgNOK * FX_RATES.SEK;
    const priceGap = avgSEK > 0 ? ((avgNOK_in_SEK - avgSEK) / avgSEK) * 100 : 0;

    const norwayAvgEl = document.getElementById("norway-avg");
    const swedenAvgEl = document.getElementById("sweden-avg");
    const priceGapEl = document.getElementById("price-gap");
    if (norwayAvgEl) norwayAvgEl.textContent = `Average: ${avgNOK.toFixed(1)} NOK`;
    if (swedenAvgEl) swedenAvgEl.textContent = `Average: ${avgSEK.toFixed(1)} SEK`;
    if (priceGapEl) priceGapEl.textContent = priceGap >= 0
        ? `Norway is ${priceGap.toFixed(1)}% more expensive`
        : `Sweden is ${Math.abs(priceGap).toFixed(1)}% more expensive`;
    if (priceGapEl && priceGapEl.parentElement) {
        priceGapEl.parentElement.dataset.gapSigned = String(priceGap >= 0);
    }

    // --- Populate the matched-products table ---
    const tbody = document.querySelector("#products-table tbody");
    tbody.innerHTML = "";

    // Build lookup maps: name (normalized) → product. For each unique name
    // we keep the cheapest entry (for price/gap math) but also attach
    // `allStores` — every store that carries the product — so the store
    // columns can link to ALL of them, not just the cheapest.
    function buildByCountry(prices) {
        const byName = {};
        prices.forEach((p) => {
            if (p.price) {
                const key = p.name.toLowerCase().replace(/\s+/g, " ").trim();
                (byName[key] = byName[key] || []).push(p);
            }
        });
        const map = {};
        Object.entries(byName).forEach(([key, list]) => {
            list.sort((a, b) => a.price - b.price);
            const cheapest = list[0];
            cheapest.avgPrice = list.reduce((s, p) => s + p.price, 0) / list.length;
            const seen = new Set();
            cheapest.allStores = [];
            list.forEach((p) => {
                (p.stores && p.stores.length ? p.stores : [p.market]).forEach((s) => {
                    const id = `${s}|${p.market}`;
                    if (seen.has(id)) return;
                    seen.add(id);
                    cheapest.allStores.push({ store: s, market: p.market, url: p.url || null, name: p.name });
                });
            });
            map[key] = cheapest;
        });
        return map;
    }
    const norwayMap = buildByCountry(allPrices.norway);
    const swedenMap = buildByCountry(allPrices.sweden);

    // --- Build the matched list.  Norwegian and Swedish retailers use
    // different names for the same product ("Bananer pr stk" vs "Bananer",
    // "Blåbær 400g beger" vs "Blåbär fruktdryck"), so exact-name equality
    // yields zero matches.  Match on the significant content words instead:
    // strip the weight/size suffix, drop stopwords, and require at least
    // one shared word plus a Jaccard similarity above the threshold.
    const STOPWORDS = new Set([
        "pr", "stk", "g", "kg", "l", "ml", "dl", "klass", "ekologisk",
        "original", "klasses", "sverige", "import", "per", "st", "stkk",
        "cm", "pk", "bx", "pack",
        "100", "200", "400", "500", "600", "750", "180", "250", "330",
        "390", "473", "150", "130", "65", "80", "85", "42", "72", "78",
        "1000", "2000", "4000", "500", "1500",
    ]);
    // Swedish -> Norwegian word translations so "Morötter" can match "Gulrot".
    // svenskegrensen.no solves the naming problem by using one common product
    // catalog for both countries; we approximate it with a translation map.
    const SE_TO_NO = {
        "vitkål": "hodekål", "huvudkål": "hodekål",
        "sötpotatis": "søtpotatis", "apelsin": "appelsin",
        "blåbär": "blåbær", "morötter": "gulrot",
        "citron": "sitron", "gurka": "agurk",
        "sallad": "salat", "isberg": "salat", "sallads": "salat",
        "broccoli": "brokoli", "champinjoner": "champignon",
        "picklad": "sylta", "rödlök": "rødløk", "lök": "løk",
        "jordgubbar": "jordbær", "päron": "pære", "pär": "pære",
        "kebabsås": "kebabsaus",
        // Butter / dairy
        "smör": "smør", "margarin": "margarin", "grädd": "grädde",
        "grädde": "fløyte", "mjölk": "melk", "färskost": "ferskost",
        "skinka": "skinke", "korv": "pølse", "bröd": "brød",
        "grön": "grønn", "frosen": "frys", "frost": "frys",
        "färs": "färs", "skinka": "skinke", "sallads": "salat",
        "meierismør": "meierismør",
    };
    const SUFFIX_RE = /\s+\d+(?:[.,]\d+)?\s*(?:g|kg|l|ml|dl|st|stk|pack|bx|boks|cl|liter|litre|cm)\b/i;
    const WORD_RE = /[a-zà-ÿ]{2,}/g;

    function sigWords(name) {
        if (!name) return new Set();
        let n = name.toLowerCase().replace(/\s+/g, " ").trim();
        n = n.replace(SUFFIX_RE, "");
        const words = (n.match(WORD_RE) || [])
            .filter((w) => !STOPWORDS.has(w))
            .map((w) => SE_TO_NO[w] || w);
        return new Set(words);
    }

    // Does the shorter term occur inside the longer one (compound/substring
    // match), treating only terms of >= 4 letters as significant so a match
    // like "smör" inside "meierismör" counts while 3-letter noise does not.
    function isCompound(a, b) {
        const s = a.length <= b.length ? a : b;
        const l = a.length <= b.length ? b : a;
        return s.length >= 4 && l.length > s.length && l.includes(s);
    }

    // Significant terms shared between two name sets: exact matches plus
    // compound (substring) matches.
    function sharedTerms(a, b) {
        const shared = [];
        a.forEach((w) => {
            if (b.has(w)) { shared.push(w); return; }
            b.forEach((v) => { if (w !== v && isCompound(w, v)) shared.push(w); });
        });
        return shared;
    }

    // Combined score: exact overlap (Jaccard) plus a compound bonus, so a
    // Norwegian compound like "Meierismør" can match the Swedish "smör".
    function combinedScore(a, b) {
        if (!a.size || !b.size) return 0;
        let inter = 0;
        a.forEach((w) => {
            if (b.has(w)) { inter++; return; }
            b.forEach((v) => { if (w !== v && isCompound(w, v)) inter++; });
        });
        const union = a.size + b.size - inter;
        return union ? inter / union : 0;
    }

    // Pair counts only when overlap is clear: enough shared terms, or a
    // single distinctive shared word (>= 5 chars), or a shared compound
    // term (>= 4 chars) with a decent score.
    function isGoodMatch(a, b, score) {
        if (score < 0.25) return false;
        const shared = sharedTerms(a, b);
        if (shared.length >= 2) return true;
        if (shared.some((w) => w.length >= 5)) return true;
        if (shared.length === 1 && shared[0].length >= 4 && score >= 0.34) return true;
        return false;
    }

    // Size-aware fuzzy match: pick the best Swedish product by combined
    // score, and among near-ties prefer one whose weight/volume is closest
    // to the Norwegian product's (so 500 g butter matches 500 g butter).
    function sizeOf(key) {
        const m = key.toLowerCase().match(/(\d+(?:[.,]\d+)?)\s*(kg|g|l|ml|dl|cl)\b/);
        if (!m) return null;
        let v = parseFloat(m[1].replace(",", "."));
        const u = m[2];
        if (u === "kg") v *= 1000;
        else if (u === "l") v *= 1000;
        else if (u === "cl") v *= 10;
        else if (u === "dl") v *= 100;
        return v; // normalised to grams / ml
    }

    function fuzzyMatch(norwayKey, swedenKeys) {
        const nw = sigWords(norwayKey);
        const noSize = sizeOf(norwayKey);
        let best = null, bestScore = 0;
        for (const sk of swedenKeys) {
            let score = combinedScore(nw, sigWords(sk));
            if (score > bestScore + 0.0001 || (score === bestScore && best === null)) {
                bestScore = score; best = sk;
            }
        }
        if (!best) return null;
        // Tie-break on size when the Norwegian product has a size.
        if (noSize != null) {
            const noSizeExact = noSize;
            let sizeBest = null, sizeBestDelta = Infinity;
            // Consider candidates within 15% of the top score for a size tie-break.
            const candidates = [];
            for (const sk of swedenKeys) {
                const s = combinedScore(nw, sigWords(sk));
                if (s >= bestScore * 0.85) candidates.push({ sk, s });
            }
            for (const c of candidates) {
                const seSize = sizeOf(c.sk);
                if (seSize == null) continue;
                const delta = Math.abs(Math.log(seSize / noSizeExact)); // ~0 means same size
                if (delta < sizeBestDelta) { sizeBestDelta = delta; sizeBest = c.sk; }
            }
            if (sizeBest != null && sizeBestDelta <= 0.35) return sizeBest; // <=0.35 ≈ 1.4x size
        }
        return isGoodMatch(nw, sigWords(best), bestScore) ? best : null;
    }

    const swedenKeys = Object.keys(swedenMap);
    const matchedKeys = [];
    const matchedSweden = {};
    const usedSweden = new Set();
    for (const nk of Object.keys(norwayMap)) {
        const sk = fuzzyMatch(nk, swedenKeys);
        if (sk && !usedSweden.has(sk)) {
            usedSweden.add(sk);
            matchedKeys.push(nk);
            matchedSweden[nk] = sk;
        }
    }

    // --- Render the table.  The old design only showed products that had
    // a name match between Norway and Sweden, but the two countries use
    // completely different names for the same items (e.g. "Bananer pr stk"
    // vs "Bananer"), so that produced zero rows and the "No matching
    // products found." message.  Render every product instead; matched
    // pairs get the full gap columns, unmatched products show their own
    // price with the other side blank.
    document.getElementById("products-body").innerHTML = "";

    if (allPrices.norway.length === 0 && allPrices.sweden.length === 0) {
        document.getElementById("products-empty").hidden = false;
        document.getElementById("products-count").textContent = "No products loaded";
        updateChart();
        return;
    }

    // Build the row list: matched pairs first (so they sort naturally to
    // the top), then unmatched products.  Use matchedSweden from the pass
    // above — appending to usedSweden here would turn every pair into an
    // unmatched row (the Sweden key is already marked as used).

    // Source URLs for each market (linked from store names in the table).
    // Keys must match the `market` field in data/prices.json.
    const SOURCE_URLS = {
        // Norway
        "rema-norway":         "https://www.rema.no/",
        "meny-norway":         "https://www.meny.no/",
        "kassal-spar_no":      "https://www.spar.no/",
        "kassal-meny_no":      "https://www.meny.no/",
        "kassal-bunnpris":     "https://www.bunnpris.no/",
        "kassal-europris_no":  "https://www.europris.se/",
        "kassal-oda_no":       "https://www.oda.no/",
        "kassal-joker_no":     "https://www.joker.no/",
        "kassal-fudi":         "https://fudi.no/",
        "kassal-engrossnett_no": "https://kassal.app/",  // wholesaler, no public price page
        // Sweden
        "nordby-sweden":       "https://www.nordbysupermarket.se/",
        "coop-sweden":         "https://www.coop.se/",
        "willys-sweden":       "https://www.willys.se/",
        "hemkop-sweden":       "https://www.hemkop.se/",
    };

    // Per-store product-search URL templates. When a store has no scraped
    // direct product page, we fall back to a search that lands on the product.
    // Verified to resolve (200) for the stores below.
    const STORE_SEARCH = {
        // Norway (Kassal chain codes + scraper store names)
        "ODA_NO":          "https://www.oda.no/sok/?q={q}",
        "MENY_NO":         "https://www.meny.no/sok?q={q}",
        "Meny":            "https://www.meny.no/sok?q={q}",
        "SPAR_NO":         "https://www.spar.no/sok?q={q}",
        "JOKER_NO":        "https://www.joker.no/sok?q={q}",
        "BUNNPRIS":        "https://www.bunnpris.no/sok?q={q}",
        "EUROPRIS_NO":     "https://www.europris.no/sok?q={q}",
        "FUDI":            "https://www.fudi.no/search?q={q}",
        "Rema 1000":       "https://www.rema.no/search?q={q}",
        "Kassal":          "https://kassal.app/?q={q}",
        // Sweden
        "Willys":          "https://www.willys.se/sok?q={q}",
        "Hemköp":          "https://www.hemkop.se/sok?q={q}",
        "Hemkop":          "https://www.hemkop.se/sok?q={q}",
    };

    // Render store names as links to their source; fall back to plain text
    // (never a broken "#") when a market has no known URL. Also strips the
    // "_NO"/"_SE" chain-code suffix from display names.
    //
    // Each store links to the SPECIFIC product:
    //   1. the scraped direct product page (product.url) when available,
    //   2. that store's product search (lands on the product) otherwise,
    //   3. the chain homepage as a last resort.
    function storeLinks(allStores) {
        if (!allStores || !allStores.length) return "—";
        const clean = (s) => String(s).replace(/_NO\b/i, "").replace(/_SE\b/i, "").trim();
        return allStores.map((e) => {
            let href = e.url || null;
            if (!href && STORE_SEARCH[e.store]) {
                href = STORE_SEARCH[e.store].replace("{q}", encodeURIComponent(e.name || ""));
            }
            if (!href) href = SOURCE_URLS[e.market] || "";
            const label = clean(e.store);
            if (!href) return `<span class="store-plain">${label}</span>`;
            return `<a class="store-link" href="${href}" target="_blank" rel="noopener noreferrer" title="${label}">${label}</a>`;
        }).join(" · ");
    }

    const rows = [];
    for (const nk of Object.keys(norwayMap)) {
        const sk = matchedSweden[nk];
        if (sk) {
            rows.push({ kind: "pair", no: norwayMap[nk], se: swedenMap[sk] });
        } else {
            rows.push({ kind: "norway", no: norwayMap[nk] });
        }
    }
    for (const sk of swedenKeys) {
        if (!usedSweden.has(sk)) {
            rows.push({ kind: "sweden", se: swedenMap[sk] });
        }
    }

    document.getElementById("products-empty").hidden = true;
    document.getElementById("products-count").textContent =
        `${rows.length} products (${matchedKeys.length} matched pairs)`;

    // Group rows by product group
    const groupedRows = {};
    const ungroupedRows = [];
    for (const row of rows) {
        const product = row.no || row.se;
        const group = getProductGroup(product);
        if (group) {
            if (!groupedRows[group]) groupedRows[group] = [];
            groupedRows[group].push(row);
        } else {
            ungroupedRows.push(row);
        }
    }

    // Sort: matched pairs first, then by the selected comparator where
    // applicable; unmatched rows sort by their own price.
    const sortBy = document.getElementById("products-sort").value;
    const pairFirst = (a, b) => {
        const aPair = a.kind === "pair" ? 0 : 1;
        const bPair = b.kind === "pair" ? 0 : 1;
        return aPair - bPair;
    };
    const priceSort = (a, b) => {
        const pa = comparablePrice(a.no || a.se).value;
        const pb = comparablePrice(b.no || b.se).value;
        return sortBy.includes("desc") ? pb - pa : pa - pb;
    };
    const nameSort = (a, b) => {
        const na = (a.no || a.se).name;
        const nb = (b.no || b.se).name;
        return sortBy.includes("desc") ? nb.localeCompare(na) : na.localeCompare(nb);
    };
    const gapSort = (a, b) => {
        const ga = a.kind === "pair"
            ? Math.abs(comparablePrice(a.no).value * FX_RATES.SEK - comparablePrice(a.se).value)
            : 0;
        const gb = b.kind === "pair"
            ? Math.abs(comparablePrice(b.no).value * FX_RATES.SEK - comparablePrice(b.se).value)
            : 0;
        return sortBy.includes("asc") ? ga - gb : gb - ga;
    };
    const sortFns = { "gap-desc": gapSort, "gap-asc": gapSort,
                      "name-asc": nameSort, "name-desc": nameSort,
                      "norway-price-desc": priceSort, "sweden-price-desc": priceSort };
    // Sort each group's rows
    for (const g of Object.values(groupedRows)) {
        g.sort((a, b) => pairFirst(a, b) || (sortFns[sortBy] || gapSort)(a, b));
    }
    ungroupedRows.sort((a, b) => pairFirst(a, b) || (sortFns[sortBy] || gapSort)(a, b));

    // Build final rows array with group headers
    const orderedGroups = [...Object.keys(groupedRows)].sort();
    const finalRows = [];
    for (const group of orderedGroups) {
        finalRows.push({ kind: "group-header", group });
        for (const r of groupedRows[group]) {
            finalRows.push({ ...r, group });
        }
    }
    if (ungroupedRows.length) {
        finalRows.push({ kind: "group-header", group: "Other" });
        for (const r of ungroupedRows) {
            finalRows.push({ ...r, group: "Other" });
        }
    }

    // Render rows

    // All fuzzy-matched pairs, sorted by price gap (descending).  CHART_PAIRS
    // is built from these and updateChart() renders the comparison chart (it
    // applies the chart-count / sort controls there).
    const gapSorted = [...rows]
        .filter(r => r.kind === "pair")
        .sort((a, b) => {
            const ga = Math.abs(comparablePrice(a.no).value * FX_RATES.SEK - comparablePrice(a.se).value);
            const gb = Math.abs(comparablePrice(b.no).value * FX_RATES.SEK - comparablePrice(b.se).value);
            return gb - ga;
        });

    // Store the matched pairs (with per-unit SEK prices) so updateChart()
    // renders the comparison chart from the SAME fuzzy-matched data as the
    // table.  updateChart() runs right after this and respects the chart
    // sort / count controls.
    CHART_PAIRS = gapSorted.map((row) => ({
        label: (row.no || row.se).name,
        no: comparablePrice(row.no).value * FX_RATES.SEK,  // Norway, in SEK
        se: comparablePrice(row.se).value,                  // Sweden, in SEK
    }));

    // Render grouped rows with collapsible headers
    const productsTbody = document.getElementById("products-body");
    productsTbody.innerHTML = "";
    finalRows.forEach((row) => {
        if (row.kind === "group-header") {
            const tr = document.createElement("tr");
            tr.className = "group-header";
            const groupCount = (groupedRows[row.group] || ungroupedRows || []).length;
            tr.innerHTML = `<td colspan="9" class="group-header-cell">
                <button class="group-toggle" aria-expanded="true" data-group="${row.group.replace(/\s+/g, '-')}">▼</button>
                <span class="group-name">${row.group}</span>
                <span class="group-count">${groupCount} products</span>
            </td>`;
            productsTbody.appendChild(tr);
            return;
        }
        const tr = document.createElement("tr");
        tr.dataset.group = row.group || "";
        const no = row.no;
        const se = row.se;
        // Use comparable (per-unit normalized) prices for gap calculation
        const noCp  = no ? comparablePrice(no).value : null;
        const seCp  = se ? comparablePrice(se).value : null;
        const noInSEK = noCp !== null ? noCp * FX_RATES.SEK : null;
        const diff = noInSEK !== null && seCp !== null ? noInSEK - seCp : null;
        const diffPct = diff !== null && seCp ? (diff / seCp) * 100 : null;
        const sparkline = no ? generateSparkline(no.history) : (se ? generateSparkline(se.history) : "");

        const noStores = no ? storeLinks(no.allStores) : "—";
        const seStores = se ? storeLinks(se.allStores) : "—";

        // Direct links to the specific product page (per country), when the
        // scraper captured a URL.  Shown as small NO / SE chips under the name.
        const prodLinks = [
            no && no.url ? `<a class="prod-link prod-link--no" href="${no.url}" target="_blank" rel="noopener noreferrer" title="${no.name} @ ${no.stores[0] || 'Norway'}">NO</a>` : "",
            se && se.url ? `<a class="prod-link prod-link--se" href="${se.url}" target="_blank" rel="noopener noreferrer" title="${se.name} @ ${se.stores[0] || 'Sweden'}">SE</a>` : "",
        ].filter(Boolean).join("");

        const noCell = no ? `<td class="numeric">${no.price.toFixed(2)}<br>${_priceSubLabel(no)}</td>` :
                       '<td class="numeric">—</td>';
        const seCell = se ? `<td class="numeric">${se.price.toFixed(2)}<br>${_priceSubLabel(se)}</td>` :
                       '<td class="numeric">—</td>';
        const gapCell = diff !== null
            ? `<td class="numeric">${diff >= 0 ? "+" : ""}${diff.toFixed(2)}</td>`
            : '<td class="numeric">—</td>';
        const gapPctCell = diffPct !== null
            ? `<td class="${diff >= 0 ? "more-expensive" : "cheaper"}">${diffPct >= 0 ? "+" : ""}${diffPct.toFixed(1)}%</td>`
            : '<td class="numeric">—</td>';

        const nameText = no ? no.name : (se ? se.name : "—");
        tr.innerHTML = `
        <td class="prod-cell"><span class="prod-name">${nameText}</span>${prodLinks ? `<span class="prod-links">${prodLinks}</span>` : ""}</td>
        <td>${(no || se).category || "-"}</td>
        <td>${noStores}</td>
        <td>${seStores}</td>
        ${noCell}
        ${seCell}
        ${gapCell}
        ${gapPctCell}
        <td class="sparkline-cell">${sparkline}</td>`;
        document.getElementById("products-body").appendChild(tr);
    });

    // --- Collapse/expand group headers ---
    productsTbody.querySelectorAll(".group-toggle").forEach((btn) => {
        btn.addEventListener("click", () => {
            const expanded = btn.getAttribute("aria-expanded") === "true";
            btn.setAttribute("aria-expanded", String(!expanded));
            btn.textContent = expanded ? "▶" : "▼";
            const groupName = btn.dataset.group;
            // Toggle rows in this group
            productsTbody.querySelectorAll(`tr[data-group]`).forEach((tr) => {
                if (tr.dataset.group === groupName) tr.hidden = expanded;
            });
        });
    });

    // --- Update the bar chart ---
    updateChart();
}

// ----- 3. Initialize category filter -----
function initCategories() {
    const categories = new Set();
    [...allPrices.norway, ...allPrices.sweden].forEach((p) => {
        if (p.category && p.category !== "Unknown") categories.add(p.category);
    });
    const catSelect = document.getElementById("products-category");
    catSelect.innerHTML = '<option value="all">All categories</option>';
    [...categories].sort().forEach((cat) => {
        const opt = document.createElement("option");
        opt.value = cat;
        opt.textContent = cat;
        catSelect.appendChild(opt);
    });
}

// ----- 2. Chart update -----
function updateChart() {
    const ctx = document.getElementById("comparisonChart");
    if (chart) chart.destroy();

    // Use the fuzzy-matched pairs (same matches as the table), normalised to
    // SEK.  CHART_PAIRS is populated by updateDisplay() on every render.
    const sortBy = document.getElementById("chart-sort").value;
    const countSel = document.getElementById("chart-count").value;
    let sortedData = [...CHART_PAIRS];

    if (sortBy === "gap-asc") {
        sortedData.sort((a, b) => Math.abs(a.no - a.se) - Math.abs(b.no - b.se));
    } else if (sortBy === "price-asc") {
        sortedData.sort((a, b) => a.no - b.no);
    } else if (sortBy === "name-asc") {
        sortedData.sort((a, b) => a.label.localeCompare(b.label));
    } else if (sortBy === "price-desc") {
        sortedData.sort((a, b) => b.no - a.no);
    } else {
        // default "gap-desc"
        sortedData.sort((a, b) => Math.abs(b.no - b.se) - Math.abs(a.no - a.se));
    }

    const limit = countSel === "all"
        ? sortedData.length
        : Math.min(parseInt(countSel, 10) || 15, sortedData.length);
    const dataItems = sortedData.slice(0, limit);

    const chartLabels = dataItems.map((x) => x.label);
    const chartNorway = dataItems.map((x) => x.no);
    const chartSweden = dataItems.map((x) => x.se);

    const chartData = {
        labels: chartLabels,
        datasets: [
            {
                label: "Norway (SEK equiv.)",
                data: chartNorway,
                backgroundColor: "rgba(208, 62, 45, 0.7)",
                borderColor: "rgba(208, 62, 45, 1)",
                borderWidth: 1,
            },
            {
                label: "Sweden (SEK)",
                data: chartSweden,
                backgroundColor: "rgba(0, 106, 167, 0.7)",
                borderColor: "rgba(0, 106, 167, 1)",
                borderWidth: 1,
            },
        ],
    };

    const chartOptions = {
        responsive: true,
        plugins: {
            title: {
                display: true,
                text: `Top ${dataItems.length} Products by Price Gap (in SEK)`,
                font: { size: 16 },
            },
            legend: { labels: { font: { size: 12 } } },
        },
        scales: {
            y: {
                beginAtZero: true,
                title: { display: true, text: "Price (SEK)" },
                font: { size: 14 },
            },
        },
    };

    try {
        chart = new Chart(ctx, { type: "bar", data: chartData, options: chartOptions });
    } catch (e) {
        console.error("Chart creation failed:", e);
    }
}

// ----- 4. Chart controls setup -----
function setupChartControls() {
    document.getElementById("chart-sort").addEventListener("change", updateChart);
    document.getElementById("chart-count").addEventListener("change", updateChart);
}

// ----- 4. Table controls setup -----
function setupTableControls() {
    const searchInput = document.getElementById("products-search");
    const categorySelect = document.getElementById("products-category");
    const sortSelect = document.getElementById("products-sort");
    const tbody = document.querySelector("#products-table tbody");

    function filterTable() {
        const q = (document.getElementById("products-search").value || "").toLowerCase().trim();
        const cat = document.getElementById("products-category").value;
        const sort = document.getElementById("products-sort").value;
        const rows = tbody.querySelectorAll("tr");

        rows.forEach((tr) => {
            const nameCell = tr.querySelector("td:first-child").textContent.toLowerCase();
            const matchesSearch = nameCell.includes(q);
            const matchesCat =
                document.getElementById("products-category").value === "all" ||
                tr.querySelector("td:nth-child(2)").textContent.toLowerCase().includes(cat.toLowerCase());

            tr.hidden = !matchesSearch || !matchesCat;
        });

        // Re-sort visible rows
        const sortValue = document.getElementById("products-sort").value;
        const comparator = {
            "gap-desc": (a, b) => {
                const ga = parseFloat(a.cells[5].textContent) || 0;
                const bb = parseFloat(b.cells[5].textContent) || 0;
                return Math.abs(bb) - Math.abs(ga);
            },
            "gap-asc": (a, b) => {
                const ga = parseFloat(a.cells[5].textContent) || 0;
                const bb = parseFloat(b.cells[5].textContent) || 0;
                return Math.abs(ga) - Math.abs(bb);
            },
            "name-asc": (a, b) => a.cells[0].textContent.localeCompare(b.cells[0].textContent),
            "name-desc": (a, b) => b.cells[0].textContent.localeCompare(a.cells[0].textContent),
            "norway-price-desc": (a, b) => {
                const pa = parseFloat(a.cells[3].textContent) || 0;
                const pb = parseFloat(b.cells[3].textContent) || 0;
                return pb - pa;
            },
            "sweden-price-desc": (a, b) => {
                const pa = parseFloat(a.cells[4].textContent) || 0;
                const pb = parseFloat(b.cells[4].textContent) || 0;
                return pb - pa;
            },
        };
        const cmp = comparator[sortSelect.value] || comparator["gap-desc"];

        const visible = Array.from(rows).filter((tr) => !tr.hidden);
        visible.sort(cmp);

        // Re-append in sorted order
        const fragment = document.createDocumentFragment();
        visible.forEach((tr) => fragment.appendChild(tr));
        tbody.appendChild(fragment);
    }

    // Attach inputs
    [document.getElementById("products-search"), document.getElementById("products-category"), document.getElementById("products-sort")].forEach((el) =>
        el.addEventListener("input", filterTable)
    );
}

// ----- 4. Mobile navigation -----
function setupMobileNav() {
    const toggle = document.querySelector(".nav-toggle");
    const nav = document.getElementById("main-nav");
    const overlay = document.querySelector(".mobile-nav-overlay");

    if (!toggle || !nav) return;

    function openNav() {
        nav.classList.add("is-mobile-open");
        overlay.classList.add("is-visible");
        toggle.setAttribute("aria-expanded", "true");
        document.body.style.overflow = "hidden";
    }
    function closeNav() {
        nav.classList.remove("is-mobile-open");
        overlay.classList.remove("is-visible");
        toggle.setAttribute("aria-expanded", "false");
        document.body.style.overflow = "";
    }

    toggle.addEventListener("click", () => nav.classList.contains("is-mobile-open") ? closeNav() : openNav());
    overlay.addEventListener("click", closeNav);

    // Close on ESC key
    document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && nav.classList.contains("is-mobile-open")) closeNav();
    });

    // Close when resizing to desktop width so the nav never sticks open
    window.addEventListener("resize", () => {
        if (window.innerWidth >= 769 && nav.classList.contains("is-mobile-open")) closeNav();
    });
}

// ----- 5. Run on DOM load -----
document.addEventListener("DOMContentLoaded", () => {
    loadPrices();
    setupMobileNav();
});