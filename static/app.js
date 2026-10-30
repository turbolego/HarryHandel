let allPrices = { norway: [], sweden: [] };
let chart = null;

// Exchange rates (approximate, updated in workflow)
const FX_RATES = {
    NOK: 1,
    SEK: 0.90,
    USD: 0.09,
    EUR: 0.085
};

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

    // Build lookup maps: name (normalized) → product
    const norwayMap = {};
    allPrices.norway.forEach((p) => {
        if (p.price) {
            const key = p.name.toLowerCase().replace(/\s+/g, " ").trim();
            if (!norwayMap[key] || p.price < norwayMap[key].price) norwayMap[key] = p;
        }
    });
    const swedenMap = {};
    allPrices.sweden.forEach((p) => {
        if (p.price) {
            const key = p.name.toLowerCase().replace(/\s+/g, " ").trim();
            if (!swedenMap[key] || p.price < swedenMap[key].price) swedenMap[key] = p;
        }
    });

    const matchedKeys = Object.keys(norwayMap).filter((k) => swedenMap[k]);

    if (matchedKeys.length === 0) {
        document.getElementById("products-empty").hidden = false;
        document.getElementById("products-count").textContent = "0 products matched";
    } else {
        document.getElementById("products-empty").hidden = true;
        document.getElementById("products-count").textContent = `${matchedKeys.length} products matched`;

        // Sort matched keys: default by gap magnitude (descending)
        const comparator = {
            "gap-desc": (a, b) => {
                const aGap = (norwayMap[a].price * FX_RATES.SEK) - swedenMap[a].price;
                const bGap = (norwayMap[b].price * FX_RATES.SEK) - swedenMap[b].price;
                return Math.abs(bGap) - Math.abs(aGap);
            },
            "gap-asc": (a, b) => {
                const aGap = (norwayMap[a].price * FX_RATES.SEK) - swedenMap[a].price;
                const bGap = (norwayMap[b].price * FX_RATES.SEK) - swedenMap[b].price;
                return Math.abs(aGap) - Math.abs(bGap);
            },
            "name-asc": (a, b) => a.localeCompare(b),
            "name-desc": (a, b) => b.localeCompare(a),
            "norway-price-desc": (a, b) => {
                const pa = norwayMap[a].price * FX_RATES.SEK;
                const pb = norwayMap[b].price * FX_RATES.SEK;
                return pb - pa;
            },
            "sweden-price-desc": (a, b) => {
                const pa = swedenMap[a].price;
                const pb = swedenMap[b].price;
                return pb - pa;
            },
        };
        const sortBy = document.getElementById("products-sort").value;
        matchedKeys.sort(comparator[comparator] || comparator["gap-desc"]);

        matchedKeys.forEach((key) => {
            const no = norwayMap[key];
            const se = swedenMap[key];
            const noInSEK = no.price * FX_RATES.SEK;
            const diff = noInSEK - se.price;
            const diffPct = se.price ? ((noInSEK - se.price) / se.price) * 100 : 0;

            const tr = document.createElement("tr");
            const sparkline = generateSparkline(no.history);
            tr.innerHTML = `
        <td>${no.name}</td>
        <td>${no.category || "-"}</td>
        <td>${(no.stores || []).join(", ")}</td>
        <td class="numeric">${no.price.toFixed(1)}</td>
        <td class="numeric">${se.price.toFixed(1)}</td>
        <td class="numeric">${diff >= 0 ? "+" : ""}${diff.toFixed(1)}</td>
        <td class="${diff >= 0 ? "more-expensive" : "cheaper"}">${diffPct >= 0 ? "+" : ""}${diffPct.toFixed(1)}%</td>
        <td class="sparkline-cell">${sparkline}</td>`;
            tbody.appendChild(tr);
        });
    }

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

    // Build comparison data: top N by normalized price (descending)
    const norwayMap = {};
    allPrices.norway.forEach((p) => {
        if (p.price) {
            const key = p.name.toLowerCase().replace(/\s+/g, " ").trim();
            if (!norwayMap[key] || p.price < norwayMap[key].price) norwayMap[key] = p;
        }
    });
    const swedenMap = {};
    allPrices.sweden.forEach((p) => {
        if (p.price) {
            const key = p.name.toLowerCase().replace(/\s+/g, " ").trim();
            if (!swedenMap[key] || p.price < swedenMap[key].price) swedenMap[key] = p;
        }
    });

    const matchedKeys = Object.keys(norwayMap).filter((k) => swedenMap[k]);
    const chartCount = parseInt(document.getElementById("chart-count").value, 10);
    const limit = Math.min(chartCount, matchedKeys.length);

    // Build data objects and sort by Norway price descending (or other sort chosen in UI)
    const sortBy = document.getElementById("chart-sort").value;
    let sortedData = matchedKeys
        .map((k) => ({
            label: norwayMap[k].name,
            no: norwayMap[k].price * FX_RATES.SEK, // normalize to SEK
            se: swedenMap[k].price,
        }));

    if (sortBy === "gap-desc") {
        sortedData.sort((a, b) => Math.abs(b.no - b.se) - Math.abs(a.no - a.se));
    } else if (sortBy === "gap-asc") {
        sortedData.sort((a, b) => Math.abs(a.no - a.se) - Math.abs(b.no - b.se));
    } else if (sortBy === "price-asc") {
        sortedData.sort((a, b) => a.no - b.no);
    } else if (sortBy === "name-asc") {
        sortedData.sort((a, b) => a.label.localeCompare(b.label));
    } else {
        sortedData.sort((a, b) => b.no - a.no); // price-desc default
    }

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
        chart = new Chart(ctx, { data: chartData, options: chartOptions });
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
}

// ----- 5. Run on DOM load -----
document.addEventListener("DOMContentLoaded", () => {
    loadPrices();
    setupMobileNav();
});