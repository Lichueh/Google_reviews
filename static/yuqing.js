/* ═══════════ Yuqing Analysis Dashboard JS ═══════════ */

const API = '';
const COMMUNITY_COLORS = [
  '#4285f4', '#ea4335', '#34a853', '#fbbc04', '#ff6d01',
  '#46bdc6', '#7b1fa2', '#c2185b', '#00838f', '#558b2f',
  '#6d4c41', '#78909c',
];
const PRESET_KEYWORDS = ['巨蛋', '座位', '停車', '音響', '演唱會', '視野', '動線', '服務', '交通', '冷氣', '遠雄', '票價'];

let state = {
  venues: [],
  selectedVenues: new Set(),
  networkInstances: {},
  vocabLoaded: {},
};

// ── Init ─────────────────────────────────────────────��───────────

document.addEventListener('DOMContentLoaded', async () => {
  setupTabs();
  setupParamSliders();
  setupButtons();
  await loadVenues();
  setupPresetKeywords();
  setupNetCompare();
});

async function loadVenues() {
  try {
    const res = await fetch(`${API}/api/yuqing/venues`);
    const venues = await res.json();
    state.venues = venues;
    renderVenueChecks(venues);
  } catch (e) {
    console.error('Failed to load venues:', e);
  }
}

function renderVenueChecks(venues) {
  const container = document.getElementById('venue-checks');
  container.innerHTML = '';
  venues.forEach(v => {
    const label = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = v.place_name;
    cb.addEventListener('change', () => {
      if (cb.checked) {
        state.selectedVenues.add(v.place_name);
        label.classList.add('active');
        preloadVenue(v.place_name);
      } else {
        state.selectedVenues.delete(v.place_name);
        label.classList.remove('active');
      }
      updateButtonStates();
      loadVocabulary();
    });
    label.appendChild(cb);
    label.append(` ${v.place_name} `);
    const span = document.createElement('span');
    span.className = 'review-count';
    span.textContent = `(${v.total_reviews}則)`;
    label.appendChild(span);
    container.appendChild(label);
  });
}

// ── Tabs ─────────────────────────────────────────────────────────

function setupTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    });
  });
}

// ── Param sliders ────────────────────────────────────────────────

function setupParamSliders() {
  ['min-freq', 'min-score', 'top-n'].forEach(name => {
    const slider = document.getElementById(`param-${name}`);
    const display = document.getElementById(`val-${name}`);
    slider.addEventListener('input', () => { display.textContent = slider.value; });
  });
}

function getParams() {
  let window = document.getElementById('param-window').value;
  if (window !== 'sentence') window = parseInt(window);
  return {
    window,
    measure: document.getElementById('param-measure').value,
    min_freq: parseInt(document.getElementById('param-min-freq').value),
    min_score: parseFloat(document.getElementById('param-min-score').value),
    top_n: parseInt(document.getElementById('param-top-n').value),
  };
}

// ── Buttons ──────────────────────────────────────────────────────

function setupButtons() {
  document.getElementById('btn-collocation').addEventListener('click', runCollocation);
  document.getElementById('btn-network').addEventListener('click', runNetwork);
  document.getElementById('btn-export-png').addEventListener('click', exportNetworkPNG);
  document.getElementById('btn-kwic').addEventListener('click', runKWIC);
  document.getElementById('btn-pos-analysis').addEventListener('click', runPOSAnalysis);
  document.getElementById('btn-compare').addEventListener('click', runCompare);

  // Concordance window slider
  const concSlider = document.getElementById('conc-window');
  const concVal = document.getElementById('conc-window-val');
  concSlider.addEventListener('input', () => { concVal.textContent = concSlider.value; });

  // Enter key in concordance inputs
  document.getElementById('conc-term1').addEventListener('keydown', e => { if (e.key === 'Enter') runKWIC(); });
  document.getElementById('conc-term2').addEventListener('keydown', e => { if (e.key === 'Enter') runKWIC(); });
}

function updateButtonStates() {
  const hasSelection = state.selectedVenues.size > 0;
  document.getElementById('btn-collocation').disabled = !hasSelection;
  document.getElementById('btn-network').disabled = !hasSelection;
  document.getElementById('btn-kwic').disabled = !hasSelection;
  document.getElementById('btn-pos-analysis').disabled = !hasSelection;
  document.getElementById('btn-compare').disabled = state.selectedVenues.size < 2;
  document.getElementById('btn-netcompare').disabled = !hasSelection;
}

// Preload tokenization in background when venue is selected
async function preloadVenue(venue) {
  if (state.preloaded && state.preloaded[venue]) return;
  if (!state.preloaded) state.preloaded = {};
  state.preloaded[venue] = 'loading';
  try {
    await apiPost('/api/yuqing/tokenize', { venue });
    state.preloaded[venue] = 'done';
    console.log(`Preloaded: ${venue}`);
  } catch (e) {
    state.preloaded[venue] = null;
    console.warn(`Preload failed: ${venue}`, e);
  }
}

// ── API helpers ──────────────────────────────────────────────────

async function apiPost(path, body, timeoutMs = 60000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${API}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('請求逾時，請稍後再試');
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

function getFirstVenue() {
  return [...state.selectedVenues][0] || '';
}

// ── Collocation ──────────────────────────────────────────────────

async function runCollocation() {
  const venue = getFirstVenue();
  if (!venue) return;

  const btn = document.getElementById('btn-collocation');
  btn.disabled = true;
  btn.textContent = '分析中...';

  try {
    const params = getParams();
    const data = await apiPost('/api/yuqing/collocation', { venue, ...params });
    renderCollocationStats(data.stats);
    renderCollocationTable(data.collocations);
  } catch (e) {
    alert('分析失敗: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '分析搭配詞';
  }
}

function renderCollocationStats(stats) {
  const grid = document.getElementById('coll-stats');
  grid.style.display = 'grid';
  grid.innerHTML = `
    <div class="stat-card"><div class="label">總 Token 數</div><div class="value">${stats.total_tokens.toLocaleString()}</div></div>
    <div class="stat-card"><div class="label">詞彙量</div><div class="value">${stats.vocab_size.toLocaleString()}</div></div>
    <div class="stat-card"><div class="label">詞對數</div><div class="value">${stats.unique_pairs.toLocaleString()}</div></div>
    <div class="stat-card"><div class="label">窗口</div><div class="value">${stats.window === 'sentence' ? '句內' : '±' + stats.window}</div></div>
  `;
}

function renderCollocationTable(collocations) {
  const container = document.getElementById('coll-result');
  container.style.display = 'block';
  document.getElementById('coll-count').textContent = `(${collocations.length} 筆)`;
  const tbody = document.getElementById('coll-tbody');
  tbody.innerHTML = '';
  collocations.forEach((c, i) => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${i + 1}</td><td>${esc(c.w1)}</td><td>${esc(c.w2)}</td><td>${c.freq}</td><td>${c.score}</td>`;
    tbody.appendChild(tr);
  });
}

// ── Network ──────────────────────────────────────────────────────

async function runNetwork() {
  const venue = getFirstVenue();
  if (!venue) return;

  const btn = document.getElementById('btn-network');
  btn.disabled = true;
  btn.textContent = '建構中...';
  document.getElementById('network-graph').innerHTML = '<div class="loading">正在建構語意網絡...</div>';

  try {
    const params = getParams();
    const data = await apiPost('/api/yuqing/network', { venue, ...params });
    renderNetwork('network-graph', data, venue);
    renderMetrics(data.metrics);
  } catch (e) {
    document.getElementById('network-graph').innerHTML = `<div class="empty-msg">建構失敗: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '生成網絡';
  }
}

function renderNetwork(containerId, data, label) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';

  if (!data.nodes || data.nodes.length === 0) {
    container.innerHTML = '<div class="empty-msg">無足夠資料生成網絡</div>';
    return null;
  }

  // Ensure container has explicit dimensions for vis.js canvas
  const rect = container.getBoundingClientRect();
  container.style.width = rect.width + 'px';
  container.style.height = Math.max(rect.height, 500) + 'px';
  console.log(`[Network] Rendering ${data.nodes.length} nodes, ${data.edges.length} edges in ${rect.width}x${rect.height}`);

  // Find max values for scaling
  const maxFreq = Math.max(...data.nodes.map(n => n.value), 1);
  const maxWeight = Math.max(...data.edges.map(e => e.value), 1);

  const nodes = new vis.DataSet(data.nodes.map(n => ({
    id: n.id,
    label: n.label,
    size: 8 + (n.value / maxFreq) * 30,
    color: {
      background: COMMUNITY_COLORS[n.community % COMMUNITY_COLORS.length],
      border: '#fff',
      highlight: { background: '#ff6d01', border: '#fff' },
    },
    font: { size: Math.max(10, 10 + (n.value / maxFreq) * 6), color: '#202124', strokeWidth: 2, strokeColor: '#fff' },
    title: `${n.label}\n頻率: ${n.value}\nDegree: ${n.degree_centrality}\nBetweenness: ${n.betweenness_centrality}`,
  })));

  const edges = new vis.DataSet(data.edges.map(e => ({
    from: e.from,
    to: e.to,
    width: 0.5 + (e.value / maxWeight) * 4,
    title: e.title,
    color: { color: 'rgba(150,150,150,0.5)', highlight: '#ff6d01' },
  })));

  const nodeCount = data.nodes.length;
  const options = {
    physics: {
      barnesHut: {
        gravitationalConstant: nodeCount > 60 ? -8000 : -3000,
        centralGravity: 0.3,
        springLength: nodeCount > 60 ? 200 : 120,
        springConstant: 0.04,
        damping: 0.09,
      },
      solver: 'barnesHut',
      stabilization: { iterations: 200, fit: true },
      maxVelocity: 50,
    },
    interaction: {
      hover: true,
      tooltipDelay: 200,
      dragNodes: true,
      zoomView: true,
    },
    nodes: {
      shape: 'dot',
      borderWidth: 2,
      shadow: false,
    },
    edges: {
      smooth: { enabled: false },
    },
  };

  const network = new vis.Network(container, { nodes, edges }, options);
  state.networkInstances[containerId] = { network, data };

  // Fit view and stop physics after stabilization
  network.on('stabilized', () => {
    network.fit({ animation: { duration: 300 } });
    setTimeout(() => network.setOptions({ physics: { enabled: false } }), 500);
  });

  // Click: highlight neighborhood
  network.on('click', params => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      const connected = network.getConnectedNodes(nodeId);
      network.selectNodes([nodeId, ...connected]);
    }
  });

  return network;
}

function renderMetrics(m) {
  document.getElementById('m-nodes').textContent = m.node_count;
  document.getElementById('m-edges').textContent = m.edge_count;
  document.getElementById('m-density').textContent = m.density;
  document.getElementById('m-clustering').textContent = m.avg_clustering;
  document.getElementById('m-components').textContent = m.components;

  renderCentralityList('top-degree', m.top_degree);
  renderCentralityList('top-betweenness', m.top_betweenness);
}

function renderCentralityList(elementId, items) {
  const ol = document.getElementById(elementId);
  ol.innerHTML = '';
  (items || []).forEach((item, i) => {
    const li = document.createElement('li');
    li.innerHTML = `<span><span class="rank">${i + 1}.</span> ${esc(item.word)}</span><span>${item.centrality}</span>`;
    ol.appendChild(li);
  });
}

function exportNetworkPNG() {
  const inst = state.networkInstances['network-graph'];
  if (!inst) return alert('請先生成網絡');
  const canvas = document.querySelector('#network-graph canvas');
  if (!canvas) return;
  const link = document.createElement('a');
  link.download = 'semantic_network.png';
  link.href = canvas.toDataURL('image/png');
  link.click();
}

// ── KWIC ─────────────────────────────────────────────────────────

async function loadVocabulary() {
  const venue = getFirstVenue();
  if (!venue || state.vocabLoaded[venue]) return;
  try {
    const data = await apiPost('/api/yuqing/vocabulary', { venue, min_freq: 3 });
    const datalist = document.getElementById('vocab-list');
    datalist.innerHTML = '';
    data.vocabulary.forEach(w => {
      const opt = document.createElement('option');
      opt.value = w;
      datalist.appendChild(opt);
    });
    state.vocabLoaded[venue] = true;
  } catch (e) {
    console.warn('Vocab load failed:', e);
  }
}

function setupPresetKeywords() {
  const container = document.getElementById('kwic-presets');
  PRESET_KEYWORDS.forEach(kw => {
    const btn = document.createElement('button');
    btn.textContent = kw;
    btn.addEventListener('click', () => {
      document.getElementById('conc-term1').value = kw;
      document.getElementById('conc-term2').value = '';
      runKWIC();
    });
    container.appendChild(btn);
  });
}

async function runKWIC() {
  const venue = getFirstVenue();
  const term1 = document.getElementById('conc-term1').value.trim();
  const term2 = document.getElementById('conc-term2').value.trim();
  const windowSize = parseInt(document.getElementById('conc-window').value);
  if (!venue || !term1) return;

  const resultDiv = document.getElementById('kwic-result');
  resultDiv.innerHTML = '<div class="loading">搜尋中...</div>';

  try {
    const data = await apiPost('/api/yuqing/kwic', { venue, term1, term2, window: windowSize });
    renderConcordanceResults(data, resultDiv);
  } catch (e) {
    resultDiv.innerHTML = `<div class="empty-msg">搜尋失敗: ${esc(e.message)}</div>`;
  }
}

function renderConcordanceResults(data, container) {
  container.innerHTML = '';

  // Summary
  const summary = document.createElement('div');
  summary.className = 'conc-summary';
  if (data.term2) {
    summary.innerHTML = `找到 <strong>${data.total}</strong> 筆含有「<strong>${esc(data.term1)}</strong>」與「<strong>${esc(data.term2)}</strong>」的共現語境`;
  } else {
    summary.innerHTML = `找到 <strong>${data.total}</strong> 筆含有「<strong>${esc(data.term1)}</strong>」的語境`;
  }
  container.appendChild(summary);

  if (data.total === 0) {
    container.innerHTML += '<div class="conc-empty">未找到共現結果，可嘗試放大前後範圍</div>';
    return;
  }

  // Match cards
  data.matches.forEach((m, i) => {
    const div = document.createElement('div');
    div.className = 'conc-match';
    const ratingClass = m.rating >= 4 ? 'rating-high' : m.rating === 3 ? 'rating-mid' : 'rating-low';
    const highlighted = buildHighlightHtml(m.context, m.term1_positions, m.term2_positions);
    div.innerHTML =
      `<div class="conc-match-num"><span class="rating-badge ${ratingClass}">${m.rating}</span> #${i + 1}</div>` +
      `${m.has_prefix ? '<span class="conc-ellipsis">…</span>' : ''}${highlighted}${m.has_suffix ? '<span class="conc-ellipsis">…</span>' : ''}`;
    container.appendChild(div);
  });
}

function buildHighlightHtml(text, t1Pos, t2Pos) {
  const annotations = [
    ...(t1Pos || []).map(([s, e]) => ({ start: s, end: e, cls: 't1' })),
    ...(t2Pos || []).map(([s, e]) => ({ start: s, end: e, cls: 't2' })),
  ].sort((a, b) => a.start - b.start);

  let html = '';
  let cursor = 0;
  for (const ann of annotations) {
    if (ann.start > cursor) html += esc(text.slice(cursor, ann.start));
    html += `<mark class="${ann.cls}">${esc(text.slice(ann.start, ann.end))}</mark>`;
    cursor = ann.end;
  }
  if (cursor < text.length) html += esc(text.slice(cursor));
  return html;
}

async function runPOSAnalysis() {
  const venue = getFirstVenue();
  const keyword = document.getElementById('conc-term1').value.trim();
  if (!venue || !keyword) return;

  const container = document.getElementById('pos-result');
  container.style.display = 'block';
  document.getElementById('pos-keyword').textContent = keyword;
  const charts = document.getElementById('pos-charts');
  charts.innerHTML = '<div class="loading">分析中...</div>';
  container.scrollIntoView({ behavior: 'smooth', block: 'start' });

  try {
    const data = await apiPost('/api/yuqing/pos-collocates', { venue, keyword, window: 5 });
    charts.innerHTML = '';

    const groups = data.pos_collocates;
    const barClasses = { n: 'noun', v: 'verb', a: 'adj', other: 'other' };

    for (const [key, group] of Object.entries(groups)) {
      if (!group.collocates || group.collocates.length === 0) continue;
      const div = document.createElement('div');
      div.className = 'pos-group';
      div.innerHTML = `<h4>${group.label} (${key})</h4>`;

      const maxCount = group.collocates[0][1];
      group.collocates.slice(0, 15).forEach(([word, count]) => {
        const row = document.createElement('div');
        row.className = 'pos-bar-row';
        const pct = (count / maxCount * 100).toFixed(0);
        row.innerHTML =
          `<span class="pos-bar-label">${esc(word)}</span>` +
          `<div class="pos-bar ${barClasses[key] || 'other'}" style="width:${pct}%"></div>` +
          `<span class="pos-bar-count">${count}</span>`;
        div.appendChild(row);
      });
      charts.appendChild(div);
    }
  } catch (e) {
    charts.innerHTML = `<div class="empty-msg">分析失敗: ${esc(e.message)}</div>`;
  }
}

// ── Compare ──────────────────────────────────────────────────────

async function runCompare() {
  const venues = [...state.selectedVenues];
  if (venues.length < 2) return alert('請選擇至少 2 個場館');

  const btn = document.getElementById('btn-compare');
  btn.disabled = true;
  btn.textContent = '比較中...';
  const resultDiv = document.getElementById('compare-result');
  resultDiv.innerHTML = '<div class="loading">正在比較場館...</div>';

  try {
    const params = getParams();
    const data = await apiPost('/api/yuqing/compare', { venues, ...params });
    renderComparison(data.comparison, resultDiv);
  } catch (e) {
    resultDiv.innerHTML = `<div class="empty-msg">比較失敗: ${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '開始比較';
  }
}

function renderComparison(results, container) {
  container.innerHTML = '';

  if (results.length === 0) {
    container.innerHTML = '<div class="empty-msg">無足夠資料進行比較</div>';
    return;
  }

  // Metrics comparison table
  const tableCard = document.createElement('div');
  tableCard.className = 'card';
  tableCard.innerHTML = '<h3>網絡指標比較</h3>';
  const table = document.createElement('table');
  table.className = 'compare-metrics-table';

  const metricLabels = {
    node_count: '節點數', edge_count: '邊數',
    density: '密度', avg_clustering: '平均群集係數',
    components: '連通分量',
  };

  let thead = '<tr><th>指標</th>';
  results.forEach(r => { thead += `<th>${esc(r.venue)}</th>`; });
  thead += '</tr>';
  table.innerHTML = thead;

  for (const [key, label] of Object.entries(metricLabels)) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td style="font-weight:600;text-align:left">${label}</td>`;
    results.forEach(r => {
      tr.innerHTML += `<td>${r.metrics[key]}</td>`;
    });
    table.appendChild(tr);
  }

  // Top degree centrality comparison
  const trDeg = document.createElement('tr');
  trDeg.innerHTML = '<td style="font-weight:600;text-align:left">Degree Top 5</td>';
  results.forEach(r => {
    const top5 = (r.metrics.top_degree || []).slice(0, 5).map(d => d.word).join(', ');
    trDeg.innerHTML += `<td style="font-size:0.8rem">${esc(top5)}</td>`;
  });
  table.appendChild(trDeg);

  const trBet = document.createElement('tr');
  trBet.innerHTML = '<td style="font-weight:600;text-align:left">Betweenness Top 5</td>';
  results.forEach(r => {
    const top5 = (r.metrics.top_betweenness || []).slice(0, 5).map(d => d.word).join(', ');
    trBet.innerHTML += `<td style="font-size:0.8rem">${esc(top5)}</td>`;
  });
  table.appendChild(trBet);

  tableCard.appendChild(table);
  container.appendChild(tableCard);

  // Side-by-side networks
  const networkGrid = document.createElement('div');
  networkGrid.className = 'compare-grid';
  results.forEach((r, i) => {
    const col = document.createElement('div');
    col.innerHTML = `<h3 style="margin-bottom:8px;font-size:0.9rem">${esc(r.venue)}</h3>`;
    const graphDiv = document.createElement('div');
    graphDiv.className = 'network-graph';
    graphDiv.id = `compare-graph-${i}`;
    col.appendChild(graphDiv);
    networkGrid.appendChild(col);
  });
  container.appendChild(networkGrid);

  // Render each network after DOM is ready
  requestAnimationFrame(() => {
    results.forEach((r, i) => {
      renderNetwork(`compare-graph-${i}`, r, r.venue);
    });
  });

  // Radar chart
  const radarCard = document.createElement('div');
  radarCard.className = 'card';
  radarCard.innerHTML = '<h3>雷達圖比較</h3><canvas id="radar-chart" style="max-height:400px"></canvas>';
  container.appendChild(radarCard);

  requestAnimationFrame(() => {
    renderRadarChart(results);
  });
}

function renderRadarChart(results) {
  const canvas = document.getElementById('radar-chart');
  if (!canvas) return;

  // Normalize metrics for radar
  const metrics = ['node_count', 'edge_count', 'density', 'avg_clustering'];
  const labels = ['節點數', '邊數', '密度', '群集係數'];

  // Find max per metric for normalization
  const maxVals = metrics.map(m => Math.max(...results.map(r => r.metrics[m] || 0), 0.001));

  const datasets = results.map((r, i) => ({
    label: r.venue,
    data: metrics.map((m, j) => ((r.metrics[m] || 0) / maxVals[j]) * 100),
    borderColor: COMMUNITY_COLORS[i],
    backgroundColor: COMMUNITY_COLORS[i] + '30',
    pointBackgroundColor: COMMUNITY_COLORS[i],
  }));

  new Chart(canvas, {
    type: 'radar',
    data: { labels, datasets },
    options: {
      scales: { r: { beginAtZero: true, max: 100, ticks: { display: false } } },
      plugins: { legend: { position: 'bottom' } },
    },
  });
}

// ── Network Compare ──────────────────────────────────────────────

function setupNetCompare() {
  document.getElementById('btn-netcompare').addEventListener('click', runNetCompare);
  document.getElementById('nc-type').addEventListener('change', updateNCPreview);
  updateNCPreview();
}

function getNCConfigs() {
  const type = document.getElementById('nc-type').value;
  const base = { min_freq: 3, top_n: 80, min_score: 0 };
  if (type === 'measure') return [
    { label: 'Log-Likelihood Ratio（LLR）', tag: 'LLR 推薦', color: '#1a73e8', params: { ...base, window: 5, measure: 'llr' } },
    { label: 'PMI（點互資訊）',             tag: 'PMI',      color: '#ea4335', params: { ...base, window: 5, measure: 'pmi' } },
    { label: 't-score（頻率型）',           tag: 't-score',  color: '#34a853', params: { ...base, window: 5, measure: 'tscore' } },
  ];
  if (type === 'window') return [
    { label: '窗口 ±2（窄，句法鄰近）',    tag: '±2 窄',    color: '#1a73e8', params: { ...base, window: 2,          measure: 'llr' } },
    { label: '窗口 ±5（預設，文獻建議）',  tag: '±5 預設',  color: '#ea4335', params: { ...base, window: 5,          measure: 'llr' } },
    { label: '句內窗口（寬，語意涵蓋）',   tag: '句內 寬',  color: '#34a853', params: { ...base, window: 'sentence', measure: 'llr' } },
  ];
  return [
    { label: '寬鬆：min_freq=2，top_n=150', tag: '寬鬆', color: '#1a73e8', params: { window: 5, measure: 'llr', min_freq: 2, top_n: 150, min_score: 0 } },
    { label: '預設：min_freq=3，top_n=80',  tag: '預設', color: '#ea4335', params: { window: 5, measure: 'llr', min_freq: 3, top_n: 80,  min_score: 0 } },
    { label: '嚴格：min_freq=5，top_n=50',  tag: '嚴格', color: '#34a853', params: { window: 5, measure: 'llr', min_freq: 5, top_n: 50,  min_score: 0 } },
  ];
}

function updateNCPreview() {
  const configs = getNCConfigs();
  const type = document.getElementById('nc-type').value;
  const fixedDesc = { measure: '窗口 ±5、min_freq=3、top_n=80', window: '指標 LLR、min_freq=3、top_n=80', threshold: '指標 LLR、窗口 ±5' };
  const dimLabel  = { measure: '關聯指標', window: '窗口大小', threshold: '閾值設定' };

  document.getElementById('nc-config-preview').innerHTML = `
    <div class="nc-config-cards">
      ${configs.map((c, i) => `
        <div class="nc-config-card" style="border-top:3px solid ${c.color}">
          <span class="nc-config-badge" style="background:${c.color}">網絡 ${String.fromCharCode(65+i)}</span>
          <div class="nc-config-label">${c.label}</div>
          <div class="nc-config-params">${fmtP(c.params)}</div>
        </div>`).join('')}
    </div>
    <p style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:12px">
      固定參數：${fixedDesc[type]}　／　比較維度：${dimLabel[type]}
    </p>`;
}

function fmtP(p) {
  const parts = [];
  if (p.measure) parts.push(`指標: ${p.measure.toUpperCase()}`);
  parts.push(`窗口: ${p.window === 'sentence' ? '句內' : '±' + p.window}`);
  parts.push(`min_freq: ${p.min_freq}`);
  parts.push(`top_n: ${p.top_n}`);
  return parts.join(' · ');
}

async function runNetCompare() {
  const venue = getFirstVenue();
  if (!venue) return alert('請先選擇場館');
  const btn = document.getElementById('btn-netcompare');
  btn.disabled = true; btn.textContent = '建構中...';

  const resultDiv = document.getElementById('nc-result');
  resultDiv.innerHTML = '<div class="loading">正在建構三個語意網絡，請稍候…</div>';

  const configs = getNCConfigs();
  const results = await Promise.all(
    configs.map(c =>
      apiPost('/api/yuqing/network', { venue, ...c.params }, 90000)
        .then(data => ({ ...c, data }))
        .catch(e  => ({ ...c, error: e.message }))
    )
  );

  renderNetCompare(results, resultDiv);
  btn.disabled = false; btn.textContent = '生成比較';
}

function renderNetCompare(results, container) {
  container.innerHTML = '';

  // ── Networks ──
  const netSection = document.createElement('div');
  netSection.className = 'card';
  netSection.innerHTML = '<h3>三網絡視覺化（可拖拉節點）</h3>';
  const grid = document.createElement('div');
  grid.className = 'compare-grid';

  results.forEach((r, i) => {
    const col = document.createElement('div');
    col.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
        <span style="background:${r.color};color:#fff;padding:2px 8px;border-radius:10px;font-size:0.72rem;font-weight:700">網絡 ${String.fromCharCode(65+i)}</span>
        <span style="font-size:0.88rem;font-weight:600">${esc(r.tag)}</span>
      </div>`;
    const g = document.createElement('div');
    g.className = 'network-graph';
    g.id = `nc-graph-${i}`;
    col.appendChild(g);
    grid.appendChild(col);
  });
  netSection.appendChild(grid);
  container.appendChild(netSection);

  requestAnimationFrame(() => {
    results.forEach((r, i) => {
      const el = document.getElementById(`nc-graph-${i}`);
      if (r.data) renderNetwork(`nc-graph-${i}`, r.data, r.tag);
      else el.innerHTML = `<div class="empty-msg" style="font-size:0.8rem">建構失敗：${esc(r.error || '')}</div>`;
    });
  });

  // ── Metrics table ──
  container.appendChild(buildNCMetricsTable(results));

  // ── Interpretation ──
  const type = document.getElementById('nc-type').value;
  container.appendChild(buildNCInterpretation(results, type));
}

function buildNCMetricsTable(results) {
  const card = document.createElement('div');
  card.className = 'card';
  const defs = [
    { key: 'node_count',      label: '節點數',      desc: '進入網絡的詞彙量' },
    { key: 'edge_count',      label: '邊數',        desc: '顯著搭配詞對數' },
    { key: 'density',         label: '密度',        desc: '實際邊 / 可能邊' },
    { key: 'avg_clustering',  label: '平均群集係數', desc: '局部群聚程度' },
    { key: 'components',      label: '連通分量',    desc: '獨立子網絡數' },
  ];

  // Per-metric max/min
  const hl = {};
  defs.forEach(d => {
    const vals = results.filter(r => r.data).map(r => parseFloat(r.data.metrics[d.key]) || 0);
    if (vals.length > 1) hl[d.key] = { max: Math.max(...vals), min: Math.min(...vals) };
  });

  let html = `<h3>網絡結構指標比較</h3>
    <table class="nc-metrics-table"><thead><tr>
      <th>指標</th><th>說明</th>
      ${results.map((r, i) => `<th><span class="nc-col-badge" style="background:${r.color}">網絡 ${String.fromCharCode(65+i)}</span><br><small>${esc(r.tag)}</small></th>`).join('')}
    </tr></thead><tbody>`;

  defs.forEach(d => {
    html += `<tr><td class="metric-name">${d.label}</td><td class="metric-desc">${d.desc}</td>`;
    results.forEach(r => {
      const raw = r.data ? r.data.metrics[d.key] : '—';
      const fval = parseFloat(raw) || 0;
      const h = hl[d.key];
      const cls = h && fval === h.max && h.max !== h.min ? ' nc-val-max'
                : h && fval === h.min && h.max !== h.min ? ' nc-val-min' : '';
      html += `<td class="nc-metric-val${cls}">${raw}</td>`;
    });
    html += '</tr>';
  });

  // Top degree words row
  html += `<tr><td class="metric-name">Degree Top 5</td><td class="metric-desc">最高連結度詞彙</td>`;
  results.forEach(r => {
    const top5 = r.data ? (r.data.metrics.top_degree || []).slice(0, 5).map(d => d.word).join('、') : '—';
    html += `<td class="nc-metric-words">${esc(top5)}</td>`;
  });
  html += '</tr></tbody></table>';
  card.innerHTML = html;
  return card;
}

function buildNCInterpretation(results, type) {
  const card = document.createElement('div');
  card.className = 'card nc-interpretation';

  const valid = results.filter(r => r.data);
  if (valid.length === 0) {
    card.innerHTML = '<h3>語意結構解釋</h3><p style="color:var(--text-secondary)">無有效網絡資料可解釋。</p>';
    return card;
  }

  const mx = valid.map(r => ({
    tag: r.tag, color: r.color,
    nodes:      r.data.metrics.node_count,
    edges:      r.data.metrics.edge_count,
    density:    parseFloat(r.data.metrics.density),
    clustering: parseFloat(r.data.metrics.avg_clustering),
    components: r.data.metrics.components,
    top5:       (r.data.metrics.top_degree || []).slice(0, 5).map(d => d.word),
  }));

  const maxNodes = mx.reduce((a, b) => a.nodes > b.nodes ? a : b);
  const minNodes = mx.reduce((a, b) => a.nodes < b.nodes ? a : b);
  const maxDens  = mx.reduce((a, b) => a.density  > b.density  ? a : b);
  const maxClust = mx.reduce((a, b) => a.clustering > b.clustering ? a : b);

  let struct = '', semantic = '', recommend = '';

  if (type === 'measure') {
    struct = `
      <p>三種指標在網絡規模上存在明顯差異：「${maxNodes.tag}」納入最多詞彙（${maxNodes.nodes} 個節點），
      「${minNodes.tag}」最為精簡（${minNodes.nodes} 個節點）。
      密度最高者為「${maxDens.tag}」（${maxDens.density}），代表其詞彙間連結最為緊密。
      群集係數最高者為「${maxClust.tag}」（${maxClust.clustering}），顯示局部語意群的凝聚程度最強。</p>
      <p>PMI 對低頻共現詞對賦予高分，傾向保留「稀有但精準」的搭配，易使節點較少但高度相關；
      t-score 強調頻率穩定性，保留常見搭配；
      LLR 對語料大小不敏感，統計顯著性最穩健，適合評論類短文本。</p>`;
    semantic = `
      <p>比較各網絡的核心詞：${mx.map(m => `「${m.tag}」核心詞為「${m.top5.slice(0,3).join('、')}」`).join('；')}。
      頻率型指標（t-score）突顯高頻主題詞（如停車、服務、演唱會），
      資訊量型指標（PMI）可能揭露特殊但語意緊密的搭配（如特定藝人名稱與場館的強關聯），
      LLR 則在兩者間取得平衡，核心詞兼具高頻與統計顯著性。</p>`;
    recommend = `本研究以 LLR 為主要指標，因其在小語料下功效穩健（Dunning 1993）。
      建議以 LLR 網絡作為主要分析對象，輔以 PMI 網絡發現特殊語意搭配，
      以 t-score 網絡確認高頻主題詞的穩定性。三網絡核心詞高度重疊者，即為最可靠的評論主題。`;

  } else if (type === 'window') {
    const [narrow, medium, wide] = mx;
    struct = `
      <p>窗口大小直接影響捕捉到的詞對數量與性質：
      窄窗口（${narrow ? narrow.tag : ''}）聚焦句法鄰近性，納入 ${narrow ? narrow.nodes : '—'} 個節點、${narrow ? narrow.edges : '—'} 條邊；
      中等窗口（${medium ? medium.tag : ''}）在句法與語意間取得平衡，節點數 ${medium ? medium.nodes : '—'}；
      寬窗口（${wide ? wide.tag : ''}）涵蓋整句語境，詞彙最豐富（${wide ? wide.nodes : '—'} 個節點）。</p>
      <p>密度變化顯示：窗口越大引入越多非核心搭配，連結趨於分散；
      窄窗口形成更緊密、聚焦的語意核心群集（群集係數：${narrow ? narrow.clustering : '—'} vs ${wide ? wide.clustering : '—'}）。</p>`;
    semantic = `
      <p>±2 窗口捕捉的多為修飾關係（如「非常 好」「停車 方便」等句法搭配）；
      ±5 窗口額外納入主題層次的語意關聯（如「演唱會 停車 動線」等評論情境詞）；
      句內窗口有時引入前後文較鬆散的共現，語意解釋須更謹慎。
      三網絡共同出現的核心詞（如「${narrow ? narrow.top5.slice(0,2).join('、') : ''}」等）
      代表跨窗口皆穩定的評論主題，語意可靠性最高。</p>`;
    recommend = `文獻建議採用 ±5 作為預設窗口（Church & Hanks 1990；Sinclair 1991），
      在句法精確性與語意涵蓋間取得最佳平衡。
      若分析目標為「動詞＋賓語」等句法搭配，可縮小至 ±2；
      若關注評論整體主題共現，可採句內模式並搭配更嚴格的頻率閾值以控制雜訊。`;

  } else {
    const [loose, def, strict] = mx;
    struct = `
      <p>閾值設定決定網絡的廣度與精確度：
      寬鬆設定（${loose ? loose.tag : ''}）保留更多低頻詞對，節點數最多（${loose ? loose.nodes : '—'}），
      但可能包含偶然共現的雜訊；
      嚴格設定（${strict ? strict.tag : ''}）要求更高共現頻率，
      節點數最少（${strict ? strict.nodes : '—'}），每條搭配的可靠性更高。</p>
      <p>群集係數最高者為「${maxClust.tag}」（${maxClust.clustering}），
      代表其核心語意群的內部相互連結最為緊密。
      預設設定（${def ? def.tag : ''}）節點數 ${def ? def.nodes : '—'}，
      在廣度與精確度之間提供實用的平衡點。</p>`;
    semantic = `
      <p>嚴格閾值（min_freq≥5）篩選出的搭配詞組往往是評論中反覆出現的核心議題，
      如「座位 視野」「停車 不便」等穩定的正負向評論主題，語意解釋最清晰。
      寬鬆閾值則可能揭露較少見但仍有意義的語意搭配（如特定活動類型與體驗詞的關聯），
      適合探索性分析與假設生成。
      三網絡共同出現的核心詞為最穩健的評論主題關鍵詞。</p>`;
    recommend = `本研究採用 min_freq=3 排除僅出現 1-2 次的偶然共現，
      top_n=80 確保網絡規模在視覺化與語意解釋上均可管理。
      若語料量小於 500 則，建議降低至 min_freq=2 以保留足夠詞彙；
      語料量超過 2000 則時，可提高至 min_freq=5 以提升搭配可靠性。`;
  }

  card.innerHTML = `
    <h3>語意結構解釋</h3>
    <div class="nc-interp-section nc-blue-s">
      <div class="nc-interp-label nc-blue">網絡結構差異</div>
      <div class="nc-interp-body">${struct}</div>
    </div>
    <div class="nc-interp-section nc-green-s">
      <div class="nc-interp-label nc-green">語意解釋差異</div>
      <div class="nc-interp-body">${semantic}</div>
    </div>
    <div class="nc-interp-section nc-amber-s">
      <div class="nc-interp-label nc-amber">分析建議</div>
      <div class="nc-interp-body"><p>${recommend}</p></div>
    </div>`;

  return card;
}

// ── Utility ──────────────────────────────────────────────────────

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}
