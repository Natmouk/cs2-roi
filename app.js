/**
 * app.js
 *
 * Loads data/cases.json and data/prices.json, calculates EV and ROI
 * for every case, and renders the UI.
 *
 * All calculations happen in the browser — no backend required.
 */

'use strict';

// ── Constants ─────────────────────────────────────────────────────────────────

const KEY_PRICE = 2.49;

const RARITY_RATES = {
  'Mil-Spec Grade': 0.7992,
  'Restricted':     0.1598,
  'Classified':     0.0320,
  'Covert':         0.0064,
};

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Failed to load ${path}: ${res.status}`);
  return res.json();
}

// ── EV / ROI calculation ──────────────────────────────────────────────────────

/**
 * Calculate expected value and ROI for a single case.
 *
 * @param {object} caseData   - one entry from cases.json
 * @param {object} prices     - the prices{} dict from prices.json
 * @returns {{ ev, totalCost, roi, itemRows }}
 */
function calculateCase(caseData, prices) {
  const casePrice = prices[caseData.market_hash_name];

  // Case has no market listing — skip
  if (casePrice == null) return null;

  const totalCost = casePrice + KEY_PRICE;

  // Group items by rarity so we can divide the rarity rate equally
  const byRarity = {};
  for (const item of caseData.items) {
    const rate = RARITY_RATES[item.rarity];
    if (rate == null) continue; // unknown rarity (e.g. knives) — skip
    if (!byRarity[item.rarity]) byRarity[item.rarity] = [];
    byRarity[item.rarity].push(item);
  }

  let ev = 0;
  const itemRows = [];

  for (const [rarity, items] of Object.entries(byRarity)) {
    const rarityRate  = RARITY_RATES[rarity];
    const perItemRate = rarityRate / items.length;

    for (const item of items) {
      // Normal version
      const normalPrice = prices[item.name];
      if (normalPrice != null) {
        const contrib = perItemRate * normalPrice;
        ev += contrib;
        itemRows.push({
          name:       item.name,
          rarity,
          stattrak:   false,
          price:      normalPrice,
          dropChance: perItemRate,
          contrib,
        });
      }

      // StatTrak version — drops at 1/10th the per-item rate
      if (item.stattrak) {
        const stKey   = `StatTrak™ ${item.name}`;
        const stPrice = prices[stKey];
        if (stPrice != null) {
          const stRate   = perItemRate / 10;
          const stContrib = stRate * stPrice;
          ev += stContrib;
          itemRows.push({
            name:       stKey,
            rarity,
            stattrak:   true,
            price:      stPrice,
            dropChance: stRate,
            contrib:    stContrib,
          });
        }
      }
    }
  }

  const roi = ((ev - totalCost) / totalCost) * 100;

  return { ev, totalCost, roi, casePrice, itemRows };
}

// ── Rendering helpers ─────────────────────────────────────────────────────────

function fmt(value, decimals = 2) {
  return `$${value.toFixed(decimals)}`;
}

function fmtROI(roi) {
  return `${roi >= 0 ? '+' : ''}${roi.toFixed(2)}%`;
}

function rarityClass(rarity) {
  const map = {
    'Mil-Spec Grade': 'mil-spec',
    'Restricted':     'restricted',
    'Classified':     'classified',
    'Covert':         'covert',
  };
  return `rarity-${map[rarity] || 'mil-spec'}`;
}

// ROI bar: map roi range [-100, +50] onto [0, 100]%
function roiBarWidth(roi) {
  return Math.min(100, Math.max(0, ((roi + 100) / 150) * 100));
}

// ── Card rendering ────────────────────────────────────────────────────────────

function renderCard(caseData, result, isActive) {
  const { ev, casePrice, roi } = result;
  const totalCost = casePrice + KEY_PRICE;
  const roiPositive = roi >= 0;

  const card = document.createElement('div');
  card.className = `case-card${isActive ? ' active' : ''}`;
  card.dataset.caseId = caseData.id;

  card.innerHTML = `
    <div class="case-card-name" title="${caseData.name}">${caseData.name}</div>
    <div class="case-card-prices">
      <span>Case: ${fmt(casePrice)}</span>
      <span>Total: ${fmt(totalCost)}</span>
    </div>
    <div class="roi-bar-track">
      <div class="roi-bar-fill" style="
        width: ${roiBarWidth(roi).toFixed(1)}%;
        background: ${roiPositive ? 'var(--positive)' : 'var(--negative)'};
      "></div>
    </div>
    <div class="case-card-footer">
      <span class="roi-value ${roiPositive ? 'positive' : 'negative'}">${fmtROI(roi)}</span>
      <span class="ev-value">EV ${fmt(ev)}</span>
    </div>
  `;

  return card;
}

// ── Detail table rendering ────────────────────────────────────────────────────

function renderDetail(caseData, result) {
  const { ev, casePrice, totalCost, roi, itemRows } = result;

  // Header
  document.getElementById('detail-title').textContent = caseData.name;
  document.getElementById('detail-meta').textContent =
    `Case: ${fmt(casePrice)}  ·  Key: ${fmt(KEY_PRICE)}  ·  Total cost: ${fmt(totalCost)}`;

  document.getElementById('detail-ev').textContent   = fmt(ev, 4);
  document.getElementById('detail-cost').textContent = fmt(totalCost);

  const roiEl = document.getElementById('detail-roi');
  roiEl.textContent  = fmtROI(roi);
  roiEl.className    = `detail-stat-value ${roi >= 0 ? 'positive' : 'negative'}`;

  // Sort rows by EV contribution descending
  const sorted = [...itemRows].sort((a, b) => b.contrib - a.contrib);
  const maxContrib = sorted[0]?.contrib ?? 1;

  const tbody = document.getElementById('detail-tbody');
  tbody.innerHTML = '';

  for (const row of sorted) {
    const tr = document.createElement('tr');
    const barPct = ((row.contrib / maxContrib) * 100).toFixed(1);

    const nameDisplay = row.stattrak
      ? `<span class="stattrak-label">StatTrak™</span> ${row.name.replace('StatTrak™ ', '')}`
      : row.name;

    tr.innerHTML = `
      <td class="item-name">${nameDisplay}</td>
      <td><span class="rarity-pill ${rarityClass(row.rarity)}">${row.rarity}</span></td>
      <td class="align-right">${fmt(row.price, 4)}</td>
      <td class="align-right">${(row.dropChance * 100).toFixed(4)}%</td>
      <td class="align-right">
        <div class="ev-contrib-cell">
          <span>${fmt(row.contrib, 5)}</span>
          <div class="ev-contrib-bar-track">
            <div class="ev-contrib-bar-fill" style="width:${barPct}%"></div>
          </div>
        </div>
      </td>
    `;

    tbody.appendChild(tr);
  }

  // Show the section and scroll to it
  const section = document.getElementById('detail-section');
  section.classList.remove('hidden');
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Summary metrics ───────────────────────────────────────────────────────────

function renderMetrics(results) {
  const valid = results.filter(r => r.result !== null);

  document.getElementById('metric-cases').textContent = valid.length;

  const best  = valid.reduce((a, b) => a.result.roi > b.result.roi ? a : b);
  const worst = valid.reduce((a, b) => a.result.roi < b.result.roi ? a : b);

  document.getElementById('metric-best-roi').textContent  = fmtROI(best.result.roi);
  document.getElementById('metric-best-name').textContent = best.caseData.name;
  document.getElementById('metric-worst-roi').textContent = fmtROI(worst.result.roi);
  document.getElementById('metric-worst-name').textContent = worst.caseData.name;
}

// ── Sort ──────────────────────────────────────────────────────────────────────

function sortResults(results, mode) {
  const copy = [...results];
  switch (mode) {
    case 'roi':   return copy.sort((a, b) => b.result.roi       - a.result.roi);
    case 'ev':    return copy.sort((a, b) => b.result.ev        - a.result.ev);
    case 'price': return copy.sort((a, b) => a.result.casePrice - b.result.casePrice);
    case 'alpha': return copy.sort((a, b) => a.caseData.name.localeCompare(b.caseData.name));
    default:      return copy;
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────

async function main() {
  const statusEl      = document.getElementById('status-text');
  const lastUpdatedEl = document.getElementById('last-updated');

  try {
    // Load both JSON files in parallel
    const [casesData, pricesData] = await Promise.all([
      loadJSON('../data/cases.json'),
      loadJSON('../data/prices.json'),
    ]);

    const prices = pricesData.prices;

    // Show last updated timestamp
    if (pricesData.last_updated) {
      const date = new Date(pricesData.last_updated);
      lastUpdatedEl.textContent = `Prices as of ${date.toLocaleString()}`;
    }

    // Calculate results for every case
    const results = casesData.cases
      .map(caseData => ({ caseData, result: calculateCase(caseData, prices) }))
      .filter(({ result }) => result !== null);

    if (results.length === 0) {
      statusEl.textContent = 'No case data available.';
      statusEl.classList.add('error');
      return;
    }

    statusEl.textContent = `${results.length} cases loaded`;
    renderMetrics(results);

    // Track active case
    let activeId = null;

    // Render cards
    const grid = document.getElementById('cards-grid');
    const sortSelect = document.getElementById('sort-select');

    function renderCards() {
      const sorted = sortResults(results, sortSelect.value);
      grid.innerHTML = '';
      for (const { caseData, result } of sorted) {
        const card = renderCard(caseData, result, caseData.id === activeId);
        card.addEventListener('click', () => {
          activeId = caseData.id;
          renderCards(); // re-render cards to update active state
          renderDetail(caseData, result);
        });
        grid.appendChild(card);
      }
    }

    sortSelect.addEventListener('change', renderCards);
    renderCards();

  } catch (err) {
    statusEl.textContent = `Error loading data: ${err.message}`;
    statusEl.classList.add('error');
    console.error(err);
  }
}

main();
