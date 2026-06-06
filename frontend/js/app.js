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
  if (name === 'game') requestAnimationFrame(() => { resizeCanvas(); syncUI(); });
}

// ── Navigation ────────────────────────────────────────────────────────────
document.getElementById('btn-new-game').addEventListener('click', () => {
  // Auto-populate seed so the user can see and replay the exact map
  document.getElementById('input-seed').value =
    Math.floor(Math.random() * 2147483647);
  show('newGame');
});
document.getElementById('btn-load-game').addEventListener('click', () => { loadSaveList(); show('load'); });
document.getElementById('btn-back-home').addEventListener('click', () => show('home'));
document.getElementById('btn-back-home-2').addEventListener('click', () => show('home'));
document.getElementById('btn-menu').addEventListener('click', () => show('home'));

// ── New game form ─────────────────────────────────────────────────────────
document.getElementById('form-new-game').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    player_name: document.getElementById('input-name').value.trim(),
    map_width:   parseInt(document.getElementById('input-width').value, 10),
    map_height:  parseInt(document.getElementById('input-height').value, 10),
    world: {
      climate:       document.getElementById('input-climate').value,
      precipitation: document.getElementById('input-precipitation').value,
      age:           document.getElementById('input-age').value,
      fragmentation: document.getElementById('input-fragmentation').value,
    },
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

// ── DOM refs ──────────────────────────────────────────────────────────────
const canvas  = document.getElementById('map-canvas');
const ctx     = canvas.getContext('2d');
const wrapper = document.getElementById('map-wrapper');
const tooltip = document.getElementById('tile-tooltip');

// ── Game / camera state ───────────────────────────────────────────────────
let G        = null;
let tileGrid = null;
let mapMode  = 'terrain';
const camera = { zoom: 1.0 };

// Hover state
let hoveredTile   = null;
let hoverPath     = null;   // path tiles (only when reachable)
let hoverCost     = null;   // cost if reachable, else null
let hoverFullCost = null;   // always the minimum path cost (for tooltip even if OOR)
let tooltipTimer  = null;

// Pan state
let isPanning = false;
let panStart  = null;

function startGame(state) {
  G = state;
  camera.zoom = 1.0;
  buildTileGrid();
  show('game');
}

function buildTileGrid() {
  tileGrid = new Map();
  G?.tiles.forEach(t => tileGrid.set(`${t.x},${t.y}`, t));
}

function getTile(x, y) { return tileGrid?.get(`${x},${y}`) ?? null; }

// ── Canvas sizing ─────────────────────────────────────────────────────────
// Fixed base tile size keeps maps legibly zoomed out; zoom scales on top.
const BASE_TILE_PX = 14;

function baseTileSize() {
  return [BASE_TILE_PX, BASE_TILE_PX];
}

function tileSize() {
  const [bw, bh] = baseTileSize();
  return [bw * camera.zoom, bh * camera.zoom];
}

function resizeCanvas() {
  if (!G) return;
  const [tw, th] = tileSize();
  canvas.width  = Math.round(G.map_width  * tw);
  canvas.height = Math.round(G.map_height * th);
  renderMap();
}

// Re-render on scroll (camera position = wrapper.scrollLeft/scrollTop)
wrapper.addEventListener('scroll', () => renderMap());

// ── Mouse wheel zoom ──────────────────────────────────────────────────────
canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  if (!G) return;

  // World tile coordinate under mouse before zoom
  const rect = canvas.getBoundingClientRect();
  const pixX  = e.clientX - rect.left;   // canvas pixel under cursor
  const pixY  = e.clientY - rect.top;
  const [tw0] = tileSize();
  const tileX = (pixX) / (canvas.width  / G.map_width);
  const tileY = (pixY) / (canvas.height / G.map_height);

  const factor    = e.deltaY < 0 ? 1.2 : 1 / 1.2;
  camera.zoom     = Math.max(1.0, Math.min(6.0, camera.zoom * factor));

  resizeCanvas();  // resizes canvas element; renderMap called inside

  // Adjust scroll so the tile under the cursor stays under the cursor
  const [tw1, th1] = tileSize();
  const wRect = wrapper.getBoundingClientRect();
  wrapper.scrollLeft = tileX * tw1 - (e.clientX - wRect.left);
  wrapper.scrollTop  = tileY * th1 - (e.clientY - wRect.top);
}, { passive: false });

// ── Middle-mouse drag to pan ───────────────────────────────────────────────
canvas.addEventListener('mousedown', (e) => {
  if (e.button === 1) {
    isPanning = true;
    panStart  = { mx: e.clientX, my: e.clientY, sx: wrapper.scrollLeft, sy: wrapper.scrollTop };
    e.preventDefault();
    canvas.style.cursor = 'grabbing';
  }
});

window.addEventListener('mousemove', (e) => {
  if (isPanning && panStart) {
    wrapper.scrollLeft = panStart.sx - (e.clientX - panStart.mx);
    wrapper.scrollTop  = panStart.sy - (e.clientY - panStart.my);
  }
});

window.addEventListener('mouseup', (e) => {
  if (e.button === 1) { isPanning = false; panStart = null; canvas.style.cursor = ''; }
});

window.addEventListener('resize', () => {
  if (!G) return;
  // Preserve relative scroll position when viewport resizes
  const rx = canvas.width  ? wrapper.scrollLeft / canvas.width  : 0;
  const ry = canvas.height ? wrapper.scrollTop  / canvas.height : 0;
  resizeCanvas();
  wrapper.scrollLeft = rx * canvas.width;
  wrapper.scrollTop  = ry * canvas.height;
});

// ── Coordinate helpers ────────────────────────────────────────────────────
// canvas.getBoundingClientRect() accounts for parent scroll, so this
// correctly converts viewport mouse coords to canvas pixel coords.
function clientToTile(clientX, clientY) {
  if (!G) return null;
  const rect = canvas.getBoundingClientRect();
  const cx   = clientX - rect.left;
  const cy   = clientY - rect.top;
  const tw   = canvas.width  / G.map_width;
  const th   = canvas.height / G.map_height;
  const x = Math.floor(cx / tw);
  const y = Math.floor(cy / th);
  if (x < 0 || y < 0 || x >= G.map_width || y >= G.map_height) return null;
  return { x, y };
}

// ── Client-side Dijkstra ──────────────────────────────────────────────────
// Uses tile.move_cost from server.
// Diagonal cost formula (terrain.config): round(a/2 + (b/2) * sqrt(b))
//   where a = origin tile move_cost, b = destination tile move_cost.
// Cardinal cost: b (destination only).
const DIE_SIDES = 10;  // matches terrain.config [constants] die

function stepCost(originTile, destTile, dx, dy) {
  const b = destTile.move_cost;
  if (b == null) return null;
  if (dx !== 0 && dy !== 0) {
    const a = originTile?.move_cost ?? b;
    const c = Math.round(a / 2 + (b / 2) * Math.sqrt(b));
    return c >= DIE_SIDES ? null : c;  // ≥ ceiling = impassable
  }
  return b;
}

function dijkstra(sx, sy, tx, ty, maxCost = Infinity) {
  if (!G) return null;
  const dist = new Map();
  const prev = new Map();
  dist.set(`${sx},${sy}`, 0);

  const heap = [[0, sx, sy]];
  while (heap.length) {
    heap.sort((a, b) => a[0] - b[0]);
    const [cost, x, y] = heap.shift();
    const key = `${x},${y}`;
    if (x === tx && y === ty) break;
    if (cost > (dist.get(key) ?? Infinity)) continue;
    const originTile = getTile(x, y);
    for (const [dx, dy] of [[-1,0],[1,0],[0,-1],[0,1],[-1,-1],[1,-1],[-1,1],[1,1]]) {
      const nx = x + dx, ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= G.map_width || ny >= G.map_height) continue;
      const tile = getTile(nx, ny);
      if (!tile) continue;
      const step = stepCost(originTile, tile, dx, dy);
      if (step == null) continue;
      const nc = cost + step;
      if (nc > maxCost) continue;
      const nk = `${nx},${ny}`;
      if (nc < (dist.get(nk) ?? Infinity)) {
        dist.set(nk, nc);
        prev.set(nk, `${x},${y}`);
        heap.push([nc, nx, ny]);
      }
    }
  }
  const tk = `${tx},${ty}`;
  if (!dist.has(tk)) return null;
  const path = [];
  let cur = tk;
  while (cur) {
    const [cx, cy] = cur.split(',').map(Number);
    path.unshift({x: cx, y: cy});
    cur = prev.get(cur) ?? null;
  }
  return { cost: dist.get(tk), path };
}

// ── Sync UI ───────────────────────────────────────────────────────────────
function syncUI() {
  if (!G) return;
  const p    = G.player;
  const roll = G.phase === 'move' ? p.movement_total : null;

  document.getElementById('hud-name').textContent = p.name;
  document.getElementById('hud-turn').textContent  = G.turn;
  document.getElementById('hud-pos').textContent   = `${p.position[0]}, ${p.position[1]}`;
  document.getElementById('hud-gold').textContent  = p.gold;

  // Ribbon
  document.getElementById('ribbon-gold').textContent = p.gold;
  document.getElementById('ribbon-val').textContent  = p.gold; // placeholder until economy exists

  const isRoll = G.phase === 'roll';

  // Big die vs mini die
  document.getElementById('dice-roll-area').style.display = isRoll ? 'flex' : 'none';
  const mini = document.getElementById('die-result-mini');
  mini.classList.toggle('hidden', isRoll);
  if (!isRoll && roll != null) {
    document.getElementById('die-mini-face').textContent = roll;
  }

  // Move info
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

  // Fire API call and minimum animation delay in parallel so there's
  // no gap between animation settling and the real result appearing.
  const [result] = await Promise.all([
    api('POST', `/api/games/${G.game_id}/roll`),
    new Promise(r => setTimeout(r, 520)),  // minimum spin duration
  ]);

  // Flicker until we have the result, then land on the real number
  let flicker = setInterval(() => { face.textContent = Math.ceil(Math.random() * 10); }, 55);
  setTimeout(() => {
    clearInterval(flicker);
    btn.classList.remove('rolling');
    btn.disabled = false;
    if (!result) return;
    // Show real value in big die briefly before transitioning to mini
    face.textContent = result.roll;
    setTimeout(() => {
      G = result.game_state;
      syncUI();
      logMessage(`🎲 Rolled a ${result.roll} — ${result.movement_total} movement points.`, 'highlight');
    }, 350);  // let player read the landed value
  }, 30);
});

// ── End turn ──────────────────────────────────────────────────────────────
document.getElementById('btn-end-turn').addEventListener('click', async () => {
  if (!G) return;
  const result = await api('POST', `/api/games/${G.game_id}/end-turn`);
  if (!result) return;
  G = result.game_state;
  document.getElementById('die-face').textContent = 'd10';
  clearHover();
  syncUI();
  logMessage(`— ${result.message} —`, 'highlight');
});

// ── Log collapse ──────────────────────────────────────────────────────────
document.getElementById('btn-toggle-log').addEventListener('click', () => {
  const log = document.getElementById('message-log');
  const btn = document.getElementById('btn-toggle-log');
  const nowCollapsed = log.classList.toggle('collapsed');
  btn.textContent = nowCollapsed ? '▶' : '▼';
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

// ── Keyboard fallback ─────────────────────────────────────────────────────
window.addEventListener('keydown', (e) => {
  const KEY_MAP = {
    ArrowUp:[0,-1], ArrowDown:[0,1], ArrowLeft:[-1,0], ArrowRight:[1,0],
    Numpad7:[-1,-1], Numpad8:[0,-1], Numpad9:[1,-1],
    Numpad4:[-1,0],                  Numpad6:[1,0],
    Numpad1:[-1,1],  Numpad2:[0,1],  Numpad3:[1,1],
  };
  const d = KEY_MAP[e.code];
  if (d && G && G.phase === 'move' && G.player.movement_remaining > 0) {
    e.preventDefault();
    const [px, py] = G.player.position;
    doMoveTo(px + d[0], py + d[1]);
  }
});

// ── Center panel ──────────────────────────────────────────────────────────
function updateCenterPanel(tile) {
  if (!tile || !G) return;
  const t = getTile(tile.x, tile.y);
  if (!t) return;
  const modLabel = t.modifier && t.modifier !== 'flat' ? ` · ${t.modifier}` : '';
  const riverLabel = t.is_river ? ' · river' : '';
  document.getElementById('cp-terrain').textContent = t.terrain + modLabel + riverLabel;
  document.getElementById('cp-coords').textContent  = `(${tile.x}, ${tile.y})`;
  const mc = t.move_cost;
  if (mc == null) {
    document.getElementById('cp-cost').textContent = 'Impassable';
  } else {
    document.getElementById('cp-cost').textContent = `Entry: ${mc} MP`;
  }
}

// ── Hover ─────────────────────────────────────────────────────────────────
canvas.addEventListener('mousemove', (e) => {
  if (isPanning) return;
  const tile = clientToTile(e.clientX, e.clientY);
  if (!tile || !G) { clearHover(); return; }

  const changed = !hoveredTile || hoveredTile.x !== tile.x || hoveredTile.y !== tile.y;
  if (changed) {
    clearHover();
    hoveredTile = tile;
    if (G.phase === 'move') {
      const [px, py] = G.player.position;
      if (tile.x !== px || tile.y !== py) {
        const r = dijkstra(px, py, tile.x, tile.y);
        hoverFullCost = r?.cost ?? null;
        if (r && r.cost <= G.player.movement_remaining) {
          hoverPath = r.path;
          hoverCost = r.cost;
        }
      }
    }
    updateCenterPanel(tile);
    renderMap();
    tooltipTimer = setTimeout(() => showTooltip(tile, e.clientX, e.clientY), 500);
  }
  positionTooltip(e.clientX, e.clientY);
});

canvas.addEventListener('mouseleave', clearHover);

function clearHover() {
  clearTimeout(tooltipTimer);
  tooltipTimer  = null;
  hoveredTile   = null;
  hoverPath     = null;
  hoverCost     = null;
  hoverFullCost = null;
  tooltip.classList.add('hidden');
  if (G) renderMap();
}

function showTooltip(tile, mx, my) {
  const t = getTile(tile.x, tile.y);
  if (!t) return;
  const modLabel = t.modifier && t.modifier !== 'flat' ? ` · ${t.modifier}` : '';
  const riverLabel = t.is_river ? ' · river' : '';
  document.getElementById('tt-terrain').textContent =
    `${t.terrain}${modLabel}${riverLabel}  (${tile.x}, ${tile.y})`;
  document.getElementById('tt-scalar').textContent =
    t.hills_scalar > 0 ? `Ruggedness: ${t.hills_scalar.toFixed(2)}` : '';
  document.getElementById('tt-owner').textContent   = 'Unclaimed';
  const costEl = document.getElementById('tt-cost');
  const mc = t.move_cost;
  if (mc == null) {
    costEl.textContent = 'Impassable';
    costEl.className   = 'impassable';
  } else if (G?.phase === 'move') {
    const mp = G.player.movement_remaining;
    const [px, py] = G.player.position;
    if (tile.x === px && tile.y === py) {
      costEl.textContent = 'Current position';
      costEl.className   = '';
    } else if (hoverFullCost != null) {
      if (hoverFullCost <= mp) {
        costEl.textContent = `Path: ${hoverFullCost} MP  (${mp - hoverFullCost} left)`;
        costEl.className   = 'reachable';
      } else {
        costEl.textContent = `Needs ${hoverFullCost} MP  (have ${mp})`;
        costEl.className   = 'unreachable';
      }
    } else {
      costEl.textContent = 'No path';
      costEl.className   = 'impassable';
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
  const tw  = tooltip.offsetWidth  || 140;
  const th  = tooltip.offsetHeight || 75;
  let left = mx + pad;
  let top  = my + pad;
  if (left + tw > window.innerWidth)  left = mx - tw - pad;
  if (top  + th > window.innerHeight) top  = my - th - pad;
  tooltip.style.left = `${left}px`;
  tooltip.style.top  = `${top}px`;
}

// ── Click to move ─────────────────────────────────────────────────────────
canvas.addEventListener('click', (e) => {
  if (e.button !== 0 || !G || G.phase !== 'move' || G.player.movement_remaining <= 0) return;
  const tile = clientToTile(e.clientX, e.clientY);
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
  // Recompute hover from new position
  hoverPath = null; hoverCost = null; hoverFullCost = null;
  if (hoveredTile && G.phase === 'move') {
    const [px, py] = G.player.position;
    if (hoveredTile.x !== px || hoveredTile.y !== py) {
      const r = dijkstra(px, py, hoveredTile.x, hoveredTile.y);
      hoverFullCost = r?.cost ?? null;
      if (r && r.cost <= G.player.movement_remaining) {
        hoverPath = r.path;
        hoverCost = r.cost;
      }
    }
  }
  syncUI();
  logMessage(result.message, 'highlight');
  if (G.player.movement_remaining <= 0) logMessage('No movement remaining — end your turn.', 'warn');
}

// ── Rendering ─────────────────────────────────────────────────────────────
const TERRAIN_COLORS = {
  // Water
  ocean:         '#1a3a5c',
  // Coastal
  coastal:       '#c2b280',
  floodplain:    '#8fb560',
  cliff_coast:   '#7a6a4a',
  // Land
  plain:         '#a3b86c',
  grassland:     '#6b8c42',
  forest:        '#2d5a27',
  thick_forest:  '#1e3d1a',
  jungle:        '#1a5c2a',
  marsh:         '#5a7a4a',
  desert:        '#c8a84b',
  deep_desert:   '#b8863a',
  tundra:        '#9aaa8a',
  frozen_tundra: '#d0dce4',
  // Overlay
  river:         '#2a6496',
};

function darkenHex(hex, amount) {
  const n = parseInt(hex.slice(1), 16);
  const r = Math.max(0, (n >> 16) - amount);
  const g = Math.max(0, ((n >> 8) & 0xff) - amount);
  const b = Math.max(0, (n & 0xff) - amount);
  return `rgb(${r},${g},${b})`;
}

function tileColor(tile) {
  const base = TERRAIN_COLORS[tile.terrain] ?? '#333';
  if (tile.modifier === 'hills')    return darkenHex(base, 30);
  if (tile.modifier === 'mountain') return darkenHex(base, 60);
  return base;
}

function renderMap() {
  if (!G || canvas.width === 0 || canvas.height === 0) return;

  const tw  = canvas.width  / G.map_width;
  const th  = canvas.height / G.map_height;
  const sx  = wrapper.scrollLeft;
  const sy  = wrapper.scrollTop;
  const vw  = wrapper.clientWidth;
  const vh  = wrapper.clientHeight;

  // Cull to only visible tiles
  const x0 = Math.max(0, Math.floor(sx / tw));
  const y0 = Math.max(0, Math.floor(sy / th));
  const x1 = Math.min(G.map_width  - 1, Math.ceil((sx + vw) / tw));
  const y1 = Math.min(G.map_height - 1, Math.ceil((sy + vh) / th));

  ctx.clearRect(sx, sy, vw, vh);

  // Draw terrain tiles (river tiles show their underlying terrain color)
  G.tiles.forEach(tile => {
    if (tile.x < x0 || tile.x > x1 || tile.y < y0 || tile.y > y1) return;
    ctx.fillStyle = mapMode === 'elevation'
      ? `rgb(${Math.round(tile.elevation*255)},${Math.round(tile.elevation*255)},${Math.round(tile.elevation*255)})`
      : tileColor(tile);
    ctx.fillRect(tile.x * tw, tile.y * th, Math.ceil(tw), Math.ceil(th));
  });

  // Draw rivers as lines (separate pass so they render on top of terrain fills)
  if (mapMode === 'terrain') {
    const riverSet = new Set();
    G.tiles.forEach(t => { if (t.is_river || t.terrain === 'river') riverSet.add(`${t.x},${t.y}`); });

    if (riverSet.size > 0) {
      ctx.strokeStyle = '#3a7fc1';
      ctx.lineWidth   = Math.max(1.5, Math.min(tw, th) * 0.32);
      ctx.lineCap     = 'round';
      ctx.lineJoin    = 'round';

      G.tiles.forEach(tile => {
        if (!tile.is_river && tile.terrain !== 'river') return;
        if (tile.x < x0 - 1 || tile.x > x1 + 1 || tile.y < y0 - 1 || tile.y > y1 + 1) return;

        const cx2 = tile.x * tw + tw / 2;
        const cy2 = tile.y * th + th / 2;

        for (const [dx, dy] of [[-1,0],[1,0],[0,-1],[0,1]]) {
          const nx = tile.x + dx, ny = tile.y + dy;
          if (!riverSet.has(`${nx},${ny}`)) continue;
          // Draw only in one direction to avoid duplicate strokes
          if (nx < tile.x || (nx === tile.x && ny < tile.y)) continue;
          ctx.beginPath();
          ctx.moveTo(cx2, cy2);
          ctx.lineTo(nx * tw + tw / 2, ny * th + th / 2);
          ctx.stroke();
        }

        // Draw a small dot for isolated river tiles or river mouths
        const hasRiverNeighbor = [[-1,0],[1,0],[0,-1],[0,1]].some(
          ([dx, dy]) => riverSet.has(`${tile.x+dx},${tile.y+dy}`)
        );
        if (!hasRiverNeighbor) {
          ctx.beginPath();
          ctx.arc(cx2, cy2, Math.max(1.5, tw * 0.18), 0, Math.PI * 2);
          ctx.fillStyle = '#3a7fc1';
          ctx.fill();
        }
      });
    }
  }

  // Path
  if (hoverPath && hoverPath.length > 1) {
    ctx.strokeStyle = 'rgba(240,100,180,0.6)';
    ctx.lineWidth   = Math.max(1.5, tw * 0.25);
    ctx.lineCap     = 'round';
    ctx.lineJoin    = 'round';
    ctx.setLineDash([Math.max(2, tw * 0.35), Math.max(2, tw * 0.2)]);
    ctx.beginPath();
    hoverPath.forEach((p, i) => {
      const cx = p.x * tw + tw / 2, cy = p.y * th + th / 2;
      i === 0 ? ctx.moveTo(cx, cy) : ctx.lineTo(cx, cy);
    });
    ctx.stroke();
    ctx.setLineDash([]);
  }

  // Hover outline
  if (hoveredTile) {
    const t   = getTile(hoveredTile.x, hoveredTile.y);
    const lw  = Math.max(1.5, tw * 0.1);
    const imp = t && t.move_cost == null;
    const oor = G?.phase === 'move' && !imp && hoverCost == null;
    ctx.lineWidth   = lw;
    ctx.strokeStyle = (imp || oor) ? 'rgba(180,50,50,0.75)' : 'rgba(240,100,180,0.95)';
    ctx.strokeRect(hoveredTile.x * tw + lw/2, hoveredTile.y * th + lw/2, tw - lw, th - lw);

    // Cost badge
    if (G?.phase === 'move' && hoverCost != null) {
      const bx = hoveredTile.x * tw + tw / 2;
      const by = hoveredTile.y * th + th / 2;
      const fs = Math.max(9, Math.min(14, tw * 0.52));
      ctx.font         = `bold ${fs}px sans-serif`;
      ctx.textAlign    = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'rgba(0,0,0,0.8)';
      ctx.fillText(`${hoverCost}`, bx + 1, by + 1);
      ctx.fillStyle = '#f064b4';
      ctx.fillText(`${hoverCost}`, bx, by);
    }
  }

  // Player marker
  const [px, py] = G.player.position;
  const cx = px * tw + tw / 2;
  const cy = py * th + th / 2;
  const r  = Math.max(2, Math.min(tw, th) * 0.38);
  ctx.beginPath(); ctx.arc(cx, cy, r + 2, 0, Math.PI*2);
  ctx.fillStyle = 'rgba(0,0,0,0.55)'; ctx.fill();
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI*2);
  ctx.fillStyle = '#e8c84a'; ctx.fill();
}

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

function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
