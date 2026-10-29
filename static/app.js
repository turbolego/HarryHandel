// HarryHandel - Food Price Comparison Dashboard
// Data: /data/prices.json

let allPrices = { norway: [], sweden: [] };
let chart = null;

// Exchange rates (approximate, should be updated in workflow)
const FX_RATES = {
    NOK: 1,
    SEK: 0.90,
    USD: 0.09,
    EUR: 0.085
};

async function loadPrices() {
    try {
        const response = await fetch('/data/prices.json');
        allPrices = await response.json();
        updateDisplay();
        initCategories();
    } catch (error) {
        console.error('Failed to load prices:', error);
        document.getElementById('last-updated').textContent = 'Failed to load data';
    }
}

function updateDisplay() {
    // Update last updated
    if (allPrices.last_updated) {
        const date = new Date(allPrices.last_updated);
        document.getElementById('last-updated').textContent = `Last updated: ${date.toLocaleDateString()}`;
        document.getElementById('footer-date').textContent = date.toLocaleDateString();
    }

    // Calculate stats
    const nokPrices = allPrices.norway.map(p => p.price).filter(p => p != null);
    const sekPrices = allPrices.sweden.map(p => p.price).filter(p => p != null);

    const avgNOK = nokPrices.length ? nokPrices.reduce((a, b) => a + b, 0) / nokPrices.length : 0;
    const avgSEK = sekPrices.length ? sekPrices.reduce((a, b) => a + b, 0) / sekPrices.length : 0;

    // Normalize to SEK for comparison
    const avgNOK_in_SEK = avgNOK * FX_RATES.SEK;
    const priceGap = avgSEK > 0 ? ((avgNOK_in_SEK - avgSEK) / avgSEK) * 100 : 0;

    document.getElementById('norway-avg').textContent = `Average: ${avgNOK.toFixed(1)} NOK`;
    document.getElementById('norway-count').textContent = `Products: ${allPrices.norway.length}`;
    document.getElementById('sweden-avg').textContent = `Average: ${avgSEK.toFixed(1)} SEK`;
    document.getElementById('sweden-count').textContent = `Products: ${allPrices.sweden.length}`;
    document.getElementById('price-gap').textContent = priceGap >= 0 
        ? `Norway is ${priceGap.toFixed(1)}% more expensive`
        : `Sweden is ${Math.abs(priceGap).toFixed(1)}% more expensive`;

    // Populate table
    const tbody = document.querySelector('#price-table tbody');
    tbody.innerHTML = '';

    // Build map of products by name (lowercase) for matching
    const norwayMap = {};
    allPrices.norway.forEach(p => {
        if (p.price) {
            const key = p.name.toLowerCase().replace(/\s+/g, ' ').trim();
            if (!norwayMap[key] || p.price < norwayMap[key].price) {
                norwayMap[key] = p;
            }
        }
    });

    const swedenMap = {};
    allPrices.sweden.forEach(p => {
        if (p.price) {
            const key = p.name.toLowerCase().replace(/\s+/g, ' ').trim();
            if (!swedenMap[key] || p.price < swedenMap[key].price) {
                swedenMap[key] = p;
            }
        }
    });

    // Show only matched products
    Object.keys(norwayMap).forEach(key => {
        if (swedenMap[key]) {
            const no = norwayMap[key];
            const se = swedenMap[key];
            const no_in_sek = no.price * FX_RATES.SEK;
            const diff = no_in_sek - se.price;
            const diff_pct = ((no_in_sek - se.price) / se.price) * 100;

            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${no.name}</td>
                <td>${no.category || '-'}</td>
                <td>${(no.stores || []).join(', ')}</td>
                <td>${no.price.toFixed(1)}</td>
                <td>${se.price.toFixed(1)}</td>
                <td class="${diff >= 0 ? 'more-expensive' : 'cheaper'}">${diff >= 0 ? '+' : ''}${diff.toFixed(1)} SEK (${diff_pct >= 0 ? '+' : ''}${diff_pct.toFixed(1)}%)</td>
            `;
            tbody.appendChild(tr);
        }
    });

    // Update chart
    updateChart();
}

function initCategories() {
    const categories = new Set();
    [...allPrices.norway, ...allPrices.sweden].forEach(p => {
        if (p.category && p.category !== 'Unknown') {
            categories.add(p.category);
        }
    });

    const select = document.getElementById('category');
    select.innerHTML = '<option value="all">All Categories</option>';
    [...categories].sort().forEach(cat => {
        const opt = document.createElement('option');
        opt.value = cat;
        opt.textContent = cat;
        select.appendChild(opt);
    });
}

function filterByCategory() {
    // Simple filter - just updates chart display
    updateChart();
}

function updateCurrency() {
    // Would update display currency here
    updateDisplay();
}

function updateChart() {
    const ctx = document.getElementById('comparisonChart');
    
    // Build comparison data (top 10 by volume/availability)
    const norwayMap = {};
    allPrices.norway.forEach(p => {
        if (p.price) {
            const key = p.name.toLowerCase().replace(/\s+/g, ' ').trim();
            if (!norwayMap[key] || p.price < norwayMap[key].price) {
                norwayMap[key] = p;
            }
        }
    });

    const swedenMap = {};
    allPrices.sweden.forEach(p => {
        if (p.price) {
            const key = p.name.toLowerCase().replace(/\s+/g, ' ').trim();
            if (!swedenMap[key] || p.price < swedenMap[key].price) {
                swedenMap[key] = p;
            }
        }
    });

    const labels = [];
    const norwayData = [];
    const swedenData = [];

    Object.keys(norwayMap).forEach(key => {
        if (swedenMap[key]) {
            labels.push(norwayMap[key].name);
            norwayData.push(norwayMap[key].price * FX_RATES.SEK); // Normalize to SEK
            swedenData.push(swedenMap[key].price);
        }
    });

    // Sort by Norway price descending
    const sorted = labels.map((label, i) => ({
        label: label,
        no: norwayData[i],
        se: swedenData[i]
    })).sort((a, b) => b.no - a.no);

    const chartLabels = sorted.slice(0, 15).map(x => x.label);
    const chartNorway = sorted.slice(0, 15).map(x => x.no);
    const chartSweden = sorted.slice(0, 15).map(x => x.se);

    if (chart) {
        chart.destroy();
    }

    chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: chartLabels,
            datasets: [
                {
                    label: 'Norway (SEK equivalent)',
                    data: chartNorway,
                    backgroundColor: 'rgba(220, 50, 50, 0.7)',
                    borderColor: 'rgba(220, 50, 50, 1)',
                    borderWidth: 1
                },
                {
                    label: 'Sweden (SEK)',
                    data: chartSweden,
                    backgroundColor: 'rgba(50, 100, 220, 0.7)',
                    borderColor: 'rgba(50, 100, 220, 1)',
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Price (SEK)'
                    }
                }
            },
            plugins: {
                title: {
                    display: true,
                    text: 'Top 15 Most Expensive Products (in SEK)'
                }
            }
        }
    });
}

// Load data when page loads
document.addEventListener('DOMContentLoaded', () => {
    loadPrices();
});