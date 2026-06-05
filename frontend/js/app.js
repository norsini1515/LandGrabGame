/* LandGrab — frontend app */
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
}

// ── Home screen ───────────────────────────────────────────────────────────
document.getElementById('btn-new-game').addEventListener('click', () => show('newGame'));
document.getElementById('btn-load-game').addEventListener('click', () => {
  loadSaveList();
  show('load');
});
document.getElementById('btn-back-home').addEventListener('click', () => show('home'));
document.getElementById('btn-back-home-2').addEventListener('click', () => show('home'));

// ── New game form ─────────────────────────────────────────────────────────
document.getElementById('form-new-game').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name  = document.getElementById('input-name').value.trim();
  const width = parseInt(document.getElementById('input-width').value, 10);
  const height= parseInt(document.getElementById('input-height').value, 10);
  const seedRaw = document.getElementById('input-seed').value.trim();
  const seed  = seedRaw ? parseInt(seedRaw, 10) : null;

  const body = { player_name: name, map_width: width, map_height: height };
  if (seed !== null) body.seed = seed;

  const state = await api('POST', '/api/games', body);
  if (state) startGame(state);
});

// ── Load game list ────────────────────────────────────────────────────────
async function loadSaveList() {
  const el = document.getElementById('save-list');
  el.innerHTML = '<p class="no-saves">Loading…</p>';
  const res = await api('GET', '/api/games');
  if (!res || !res.saves.length) {
    el.innerHTML = '<p class="no-saves">No saved games found.</p>';
    return;
  }
  el.innerHTML = '';
  res.saves.forEach(save => {
    const div = document.createElement('div');
    div.className = 'save-entry';
    const date = new Date(save.saved_at).toLocaleDateString();
    div.innerHTML = `
      <div class="save-name">${esc(save.player_name)}</div>
      <div class="save-meta">Turn ${save.turn} · ${date} · ID: ${save.game_id}</div>
    `;
    div.addEventListener('click', async () => {
      const state = await api('GET', `/api/games/${save.game_id}`);
      if (state) startGame(state);
    });
    el.appendChild(div);
  });
}

// ── Game state & canvas ───────────────────────────────────────────────────
let G = null;  // current GameState
const canvas = document.getElementById('map-canvas');
const ctx = canvas.getContext('2d');

const TERRAIN_COLORS = {
  ocean:     '#1a3a5c',
  coast:     '#c2b280',
  plains:    '#6b8c42',
  forest:    '#2d5a27',
  hills:     '#8c7340',
  mountains: '#6e6e6e',
  river:     '#2a6496',
};

function startGame(state) {
  G = state;
  show('game');
  updateHUD();
  renderMap();
}

function updateHUD() {
  if (!G) return;
  document.getElementById('hud-name').textContent = G.player.name;
  document.getElementById('hud-turn').textContent = `Turn ${G.turn}`;
  const [px, py] = G.player.position;
  document.getElementById('hud-pos').textContent = `(${px}, ${py})`;
  document.getElementById('hud-gold').textContent = `💰 ${G.player.gold}`;
}

function renderMap() {
  if (!G) return;
  const parent = canvas.parentElement;
  const W = parent.clientWidth;
  // Footer ~130px, header ~40px
  const H = Math.max(200, window.innerHeight - 170);
  canvas.width = W;
  canvas.height = H;

  const tileW = W / G.map_width;
  const tileH = H / G.map_height;

  G.tiles.forEach(tile => {
    ctx.fillStyle = TERRAIN_COLORS[tile.terrain] || '#333';
    ctx.fillRect(tile.x * tileW, tile.y * tileH, Math.ceil(tileW), Math.ceil(tileH));
  });

  // Draw player
  const [px, py] = G.player.position;
  ctx.fillStyle = '#e8c84a';
  const cx = px * tileW + tileW / 2;
  const cy = py * tileH + tileH / 2;
  const r  = Math.max(2, Math.min(tileW, tileH) * 0.4);
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
}

window.addEventListener('resize', () => { if (G) renderMap(); });

// ── Movement ──────────────────────────────────────────────────────────────
document.getElementById('movement-pad').addEventListener('click', async (e) => {
  const btn = e.target.closest('.dir-btn');
  if (!btn || !G) return;
  const dx = parseInt(btn.dataset.dx, 10);
  const dy = parseInt(btn.dataset.dy, 10);

  const result = await api('POST', `/api/games/${G.game_id}/move`, { game_id: G.game_id, dx, dy });
  if (!result) return;

  G = result.game_state;
  updateHUD();
  renderMap();
  logMessage(result.message, true);
});

// Keyboard arrows / numpad
window.addEventListener('keydown', (e) => {
  const MAP = {
    ArrowUp: [0,-1], ArrowDown: [0,1], ArrowLeft: [-1,0], ArrowRight: [1,0],
    // Numpad diagonals
    Numpad7: [-1,-1], Numpad8: [0,-1], Numpad9: [1,-1],
    Numpad4: [-1, 0], Numpad5: [0, 0], Numpad6: [1, 0],
    Numpad1: [-1, 1], Numpad2: [0, 1], Numpad3: [1, 1],
  };
  const move = MAP[e.code];
  if (move && G) {
    e.preventDefault();
    const [dx, dy] = move;
    api('POST', `/api/games/${G.game_id}/move`, { game_id: G.game_id, dx, dy }).then(result => {
      if (!result) return;
      G = result.game_state;
      updateHUD();
      renderMap();
      logMessage(result.message, true);
    });
  }
});

// ── Message log ───────────────────────────────────────────────────────────
function logMessage(msg, highlight = false) {
  const log = document.getElementById('message-log');
  const entry = document.createElement('div');
  entry.className = 'log-entry' + (highlight ? ' highlight' : '');
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
      logMessage(`Error: ${err.detail || res.statusText}`);
      return null;
    }
    return res.json();
  } catch (err) {
    logMessage(`Network error: ${err.message}`);
    return null;
  }
}

function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
