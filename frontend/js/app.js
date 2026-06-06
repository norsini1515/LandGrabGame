'use strict';

// ── Screen router ──────────────────────────────────────────────────────────
const screens = {
  home:    document.getElementById('screen-home'),
  newGame: document.getElementById('screen-new-game'),
  load:    document.getElementById('screen-load-game'),
  game:    document.getElementById('screen-game'),
};

function show(name) {
  Object.values(screens).forEach(s => s.classList.remove('active'));
  screens[name].classList.add('active');
  if (name === 'game') requestAnimationFrame(renderMap);
}

// ── Home ──────────────────────────────────────────────────────────────────
document.getElementById('btn-new-game').addEventListener('click', () => show('newGame'));
document.getElementById('btn-load-game').addEventListener('click', () => { loadSaveList(); show('load'); });
document.getElementById('btn-back-home').addEventListener('click', () => show('home'));
document.getElementById('btn-back-home-2').addEventListener('click', () => show('home'));

// ── New game form ─────────────────────────────────────────────────────────
document.getElementById('form-new-game').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    player_name: document.getElementById('input-name').value.trim(),
    map_width:   parseInt(document.getElementById('input-width').value, 10),
    map_height:  parseInt(document.getElementById('input-height').value, 10),
  };
  const seedRaw = document.getElementById('input-seed').value.trim();
  if (seedRaw) body.seed = parseInt(seedRaw, 10);
  const state = await api('POST', '/api/games', body);
  if (state) startGame(state);
});

// ── Load game list ────────────────────────────────────────────────────────
async function loadSaveList() {
  const el = document.getElementById('save-list');
  el.innerHTML = '<p class="no-saves">Loading…</p>';
  const res = await api('GET', '/api/games');
  if (!res || !res.saves.length) { el.innerHTML = '<p class="no-saves">No saved games found.</p>'; return; }
  el.innerHTML = '';
  res.saves.forEach(save => {
    const div = document.createElement('div');
    div.className = 'save-entry';
    div.innerHTML = `<div class="save-name">${esc(save.player_name)}</div>
      <div class="save-meta">Turn ${save.turn} · ${new Date(save.saved_at).toLocaleDateString()} · ${save.game_id}</div>`;
    div.addEventListener('click', async () => {
      const state = await api('GET', `/api/games/${save.game_id}`);
      if (state) startGame(state);
    });
    el.appendChild(div);
  });
}

// ── Game state ────────────────────────────────────────────────────────────
let G        = null;   // GameState
let mapMode  = 'terrain';
let tileGrid = null;   // Map<string, tile> for fast lookup

function startGame(state) {
  G = state;
  buildTileGrid();
  show('game');
  syncUI();
}

function buildTileGrid() {
  tileGrid = new Map();
  if (!G) return;
  G.tiles.forEach(t => tileGrid.set(`${t.x},${t.y}`, t));
}

function getTile(x, y) { return tileGrid?.get(`${x},${y}`) ?? null; }

// ── Movement costs (mirrors backend TERRAIN_MOVE_COST) ────────────────────
const MOVE_COST = {
  ocean: null, coast: 1, plains: 1, forest: 2, hills: 2, mountains: 3, river: 1,
};

// ── Client-side Dijkstra ─────────────────────────────────────────────────
// Returns {cost, path:[{x,y},...]} or null if unreachable / exceeds budget.
function dijkstra(sx, sy, tx, ty, maxCost = Infinity) {
  if (!G) return null;
  const W = G.map_width, H = G.map_height;
  const dist = new Map();
  const prev = new Map();
  dist.set(`${sx},${sy}`, 0);

  // Min-heap: [cost, x, y]
  const heap = [[0, sx, sy]];

  while (heap.length) {
    heap.sort((a, b) => a[0] - b[0]); // tiny map, simple sort is fine
    const [cost, x, y] = heap.shift();
    const key = `${x},${y}`;

    if (x === tx && y === ty) break;
    if (cost > (dist.get(key) ?? Infinity)) continue;

    for (const [dx, dy] of [[-1,0],[1,0],[0,-1],[0,1],[-1,-1],[1,-1],[-1,1],[1,1]]) {
      const nx = x + dx, ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= W || ny >= H) continue;
      const tile = getTile(nx, ny);
      if (!tile) continue;
      const stepCost = MOVE_COST[tile.terrain];
      if (stepCost == null) continue; // impassable
      const newCost = cost + stepCost;
      if (newCost > maxCost) continue;
      const nk = `${nx},${ny}`;
      if (newCost < (dist.get(nk) ?? Infinity)) {
        dist.set(nk, newCost);
        prev.set(nk, `${x},${y}`);
        heap.push([newCost, nx, ny]);
      }
    }
  }

  const targetKey = `${tx},${ty}`;
  if (!dist.has(targetKey)) return null;

  // Reconstruct path
  const path = [];
  let cur = targetKey;
  while (cur) {
    const [cx, cy] = cur.split(',').map(Number);
    path.unshift({ x: cx, y: cy });
    cur = prev.get(cur) ?? null;
  }
  return { cost: dist.get(targetKey), path };
}

// ── Sync UI ───────────────────────────────────────────────────────────────
function syncUI() {
  if (!G) return;
  const p = G.player;

  document.getElementById('hud-name').textContent = p.name;
  document.getElementById('hud-turn').textContent  = G.turn;
  document.getElementById('hud-pos').textContent   = `${p.position[0]}, ${p.position[1]}`;
  document.getElementById('hud-gold').textContent  = p.gold;

  const isRoll = G.phase === 'roll';
  document.getElementById('dice-roll-area').style.display = isRoll ? 'flex' : 'none';
  document.getElementById('move-info').classList.toggle('hidden', isRoll);

  if (!isRoll) {
    document.getElementById('move-remaining').textContent = p.movement_remaining;
    document.getElementById('move-total').textContent     = p.movement_total;
    const pct = p.movement_total > 0 ? (p.movement_remaining / p.movement_total) * 100 : 0;
    document.getElementById('move-bar-fill').style.width = `${pct}%`;
  }

  document.getElementById('btn-end-turn').disabled = isRoll;
  renderMap();
}

// ── Dice roll ─────────────────────────────────────────────────────────────
document.getElementById('btn-roll-die').addEventListener('click', async () => {
  if (!G || G.phase !== 'roll') return;
  const btn  = document.getElementById('btn-roll-die');
  const face = document.getElementById('die-face');
  btn.disabled = true;
  btn.classList.add('rolling');

  let frames = 0;
  const flicker = setInterval(() => {
    face.textContent = Math.ceil(Math.random() * 8);
    if (++frames > 8) clearInterval(flicker);
  }, 50);

  setTimeout(async () => {
    const result = await api('POST', `/api/games/${G.game_id}/roll`);
    btn.classList.remove('rolling');
    btn.disabled = false;
    clearInterval(flicker);
    if (!result) return;
    face.textContent = result.roll;
    G = result.game_state;
    syncUI();
    logMessage(`🎲 Rolled a ${result.roll} — ${result.movement_total} movement points.`, 'highlight');
  }, 450);
});

// ── End turn ──────────────────────────────────────────────────────────────
document.getElementById('btn-end-turn').addEventListener('click', async () => {
  if (!G) return;
  const result = await api('POST', `/api/games/${G.game_id}/end-turn`);
  if (!result) return;
  G = result.game_state;
  document.getElementById('die-face').textContent = 'd8';
  clearHover();
  syncUI();
  logMessage(`— ${result.message} —`, 'highlight');
});

// ── Map modes ─────────────────────────────────────────────────────────────
document.getElementById('map-mode-btns').addEventListener('click', (e) => {
  const btn = e.target.closest('.mode-btn');
  if (!btn) return;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  mapMode = btn.dataset.mode;
  renderMap();
});

// ── Keyboard fallback (one step) ──────────────────────────────────────────
window.addEventListener('keydown', (e) => {
  const KEY_MAP = {
    ArrowUp: [0,-1], ArrowDown: [0,1], ArrowLeft: [-1,0], ArrowRight: [1,0],
    Numpad7: [-1,-1], Numpad8: [0,-1], Numpad9: [1,-1],
    Numpad4: [-1, 0],                  Numpad6: [1, 0],
    Numpad1: [-1, 1], Numpad2: [0, 1], Numpad3: [1, 1],
  };
  const d = KEY_MAP[e.code];
  if (d && G && G.phase === 'move' && G.player.movement_remaining > 0) {
    e.preventDefault();
    const [px, py] = G.player.position;
    doMoveTo(px + d[0], py + d[1]);
  }
});

// ── Canvas ────────────────────────────────────────────────────────────────
const canvas  = document.getElementById('map-canvas');
const ctx     = canvas.getContext('2d');
const tooltip = document.getElementById('tile-tooltip');

const TERRAIN_COLORS = {
  ocean: '#1a3a5c', coast: '#c2b280', plains: '#6b8c42',
  forest: '#2d5a27', hills: '#8c7340', mountains: '#6e6e6e', river: '#2a6496',
};

let hoveredTile  = null;  // {x, y}
let hoverPath    = null;  // [{x,y},...] or null
let hoverCost    = null;
let tooltipTimer = null;

function tileSize() {
  if (!G) return [1, 1];
  return [canvas.width / G.map_width, canvas.height / G.map_height];
}

function canvasToTile(cx, cy) {
  if (!G) return null;
  const [tw, th] = tileSize();
  const x = Math.floor(cx / tw);
  const y = Math.floor(cy / th);
  if (x < 0 || y < 0 || x >= G.map_width || y >= G.map_height) return null;
  return { x, y };
}

// ── Hover ─────────────────────────────────────────────────────────────────
canvas.addEventListener('mousemove', (e) => {
  const rect = canvas.getBoundingClientRect();
  const tile = canvasToTile(e.clientX - rect.left, e.clientY - rect.top);

  if (!tile || !G) { clearHover(); return; }

  const changed = !hoveredTile || hoveredTile.x !== tile.x || hoveredTile.y !== tile.y;
  if (changed) {
    clearHover();
    hoveredTile = tile;

    // Compute path if in move phase
    if (G.phase === 'move' && G.player.movement_remaining > 0) {
      const [px, py] = G.player.position;
      if (tile.x !== px || tile.y !== py) {
        const result = dijkstra(px, py, tile.x, tile.y, G.player.movement_remaining);
        hoverPath = result?.path ?? null;
        hoverCost = result?.cost ?? null;
      }
    }

    renderMap();

    // Delay tooltip
    tooltipTimer = setTimeout(() => showTooltip(tile, e.clientX, e.clientY), 500);
  }

  // Move tooltip with mouse
  positionTooltip(e.clientX, e.clientY);
});

canvas.addEventListener('mouseleave', clearHover);

function clearHover() {
  clearTimeout(tooltipTimer);
  tooltipTimer = null;
  hoveredTile  = null;
  hoverPath    = null;
  hoverCost    = null;
  tooltip.classList.add('hidden');
  renderMap();
}

function showTooltip(tile, mx, my) {
  const t = getTile(tile.x, tile.y);
  if (!t) return;

  document.getElementById('tt-terrain').textContent = t.terrain;
  document.getElementById('tt-owner').textContent   = 'Unclaimed';

  const costEl = document.getElementById('tt-cost');
  const mc = MOVE_COST[t.terrain];
  if (mc == null) {
    costEl.textContent  = 'Impassable';
    costEl.className    = 'impassable';
  } else if (G?.phase === 'move') {
    const mp = G.player.movement_remaining;
    if (hoverCost != null) {
      costEl.textContent = `Cost: ${hoverCost} MP (${mp - hoverCost} remaining)`;
      costEl.className   = 'reachable';
    } else if (hoverCost === null && hoveredTile) {
      costEl.textContent = 'Out of reach';
      costEl.className   = 'unreachable';
    } else {
      costEl.textContent = `Enter cost: ${mc} MP`;
      costEl.className   = '';
    }
  } else {
    costEl.textContent = `Enter cost: ${mc} MP`;
    costEl.className   = '';
  }

  tooltip.classList.remove('hidden');
  positionTooltip(mx, my);
}

function positionTooltip(mx, my) {
  const pad = 14;
  const tw  = tooltip.offsetWidth  || 130;
  const th  = tooltip.offsetHeight || 70;
  let left = mx + pad;
  let top  = my + pad;
  if (left + tw > window.innerWidth)  left = mx - tw - pad;
  if (top  + th > window.innerHeight) top  = my - th - pad;
  tooltip.style.left = `${left}px`;
  tooltip.style.top  = `${top}px`;
}

// ── Click to move ─────────────────────────────────────────────────────────
canvas.addEventListener('click', (e) => {
  if (!G || G.phase !== 'move' || G.player.movement_remaining <= 0) return;
  const rect = canvas.getBoundingClientRect();
  const tile = canvasToTile(e.clientX - rect.left, e.clientY - rect.top);
  if (!tile) return;
  const [px, py] = G.player.position;
  if (tile.x === px && tile.y === py) return;
  doMoveTo(tile.x, tile.y);
});

async function doMoveTo(tx, ty) {
  if (!G) return;
  tooltip.classList.add('hidden');
  const result = await api('POST', `/api/games/${G.game_id}/move-to`, { tx, ty });
  if (!result) return;
  G = result.game_state;
  hoverPath = null;
  hoverCost = null;
  hoveredTile = null;
  syncUI();
  const cls = 'highlight';
  logMessage(result.message, cls);
  if (G.player.movement_remaining <= 0) {
    logMessage('No movement remaining — end your turn.', 'warn');
  }
}

// ── Canvas rendering ──────────────────────────────────────────────────────
function renderMap() {
  if (!G) return;
  const parent = canvas.parentElement;
  const W = parent.clientWidth;
  const H = Math.max(100, parent.clientHeight - 110);
  if (canvas.width !== W || canvas.height !== H) {
    canvas.width  = W;
    canvas.height = H;
  }

  const [tw, th] = tileSize();

  // Base terrain / elevation
  G.tiles.forEach(tile => {
    ctx.fillStyle = mapMode === 'elevation'
      ? elevationColor(tile.elevation)
      : (TERRAIN_COLORS[tile.terrain] || '#333');
    ctx.fillRect(tile.x * tw, tile.y * th, Math.ceil(tw), Math.ceil(th));
  });

  // Path highlight
  if (hoverPath && hoverPath.length > 1) {
    ctx.strokeStyle = 'rgba(240,100,180,0.55)';
    ctx.lineWidth   = Math.max(1.5, tw * 0.25);
    ctx.lineCap     = 'round';
    ctx.lineJoin    = 'round';
    ctx.setLineDash([Math.max(2, tw * 0.35), Math.max(2, tw * 0.2)]);
    ctx.beginPath();
    hoverPath.forEach((p, i) => {
      const cx = p.x * tw + tw / 2;
      const cy = p.y * th + th / 2;
      i === 0 ? ctx.moveTo(cx, cy) : ctx.lineTo(cx, cy);
    });
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // Hover tile outline
  if (hoveredTile) {
    const t = getTile(hoveredTile.x, hoveredTile.y);
    const canMove = G?.phase === 'move' && G.player.movement_remaining > 0;
    const reachable = hoverPath != null;
    const impassable = t && MOVE_COST[t.terrain] == null;

    ctx.lineWidth = Math.max(1.5, tw * 0.12);
    if (impassable || (canMove && !reachable)) {
      ctx.strokeStyle = 'rgba(180,50,50,0.7)';
    } else {
      ctx.strokeStyle = 'rgba(240,100,180,0.9)';
    }
    ctx.strokeRect(
      hoveredTile.x * tw + ctx.lineWidth / 2,
      hoveredTile.y * th + ctx.lineWidth / 2,
      tw - ctx.lineWidth,
      th - ctx.lineWidth,
    );

    // Cost badge on hovered tile
    if (canMove && hoverCost != null) {
      const bx = hoveredTile.x * tw + tw / 2;
      const by = hoveredTile.y * th + th / 2;
      const label = `${hoverCost}`;
      const fontSize = Math.max(9, Math.min(13, tw * 0.55));
      ctx.font = `bold ${fontSize}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      // Shadow
      ctx.fillStyle = 'rgba(0,0,0,0.75)';
      ctx.fillText(label, bx + 1, by + 1);
      // Text
      ctx.fillStyle = '#f064b4';
      ctx.fillText(label, bx, by);
    }
  }

  // Player marker
  const [px, py] = G.player.position;
  const cx = px * tw + tw / 2;
  const cy = py * th + th / 2;
  const r  = Math.max(2, Math.min(tw, th) * 0.38);

  ctx.beginPath();
  ctx.arc(cx, cy, r + 2, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(0,0,0,0.55)';
  ctx.fill();

  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = '#e8c84a';
  ctx.fill();
}

function elevationColor(e) {
  const v = Math.round(e * 255);
  return `rgb(${v},${v},${v})`;
}

window.addEventListener('resize', () => { if (G) renderMap(); });

// ── Message log ───────────────────────────────────────────────────────────
function logMessage(msg, type = '') {
  const log   = document.getElementById('message-log');
  const entry = document.createElement('div');
  entry.className = 'log-entry' + (type ? ` ${type}` : '');
  entry.textContent = msg;
  log.prepend(entry);
}

// ── API helper ────────────────────────────────────────────────────────────
async function api(method, path, body = null) {
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      logMessage(`Error: ${err.detail || res.statusText}`, 'warn');
      return null;
    }
    return res.json();
  } catch (err) {
    logMessage(`Network error: ${err.message}`, 'warn');
    return null;
  }
}

function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
