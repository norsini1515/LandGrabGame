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
let G = null;
let mapMode = 'terrain';

function startGame(state) {
  G = state;
  show('game');
  syncUI();
}

function syncUI() {
  if (!G) return;
  const p = G.player;

  document.getElementById('hud-name').textContent = p.name;
  document.getElementById('hud-turn').textContent = G.turn;
  document.getElementById('hud-pos').textContent  = `${p.position[0]}, ${p.position[1]}`;
  document.getElementById('hud-gold').textContent = p.gold;

  const isRoll = G.phase === 'roll';
  const isMove = G.phase === 'move';
  const noMoves = isMove && p.movement_remaining <= 0;

  // Dice area visibility
  document.getElementById('dice-roll-area').style.display = isRoll ? 'flex' : 'none';
  const moveInfo = document.getElementById('move-info');
  moveInfo.classList.toggle('hidden', isRoll);

  if (isMove) {
    document.getElementById('move-remaining').textContent = p.movement_remaining;
    document.getElementById('move-total').textContent     = p.movement_total;
    const pct = p.movement_total > 0 ? (p.movement_remaining / p.movement_total) * 100 : 0;
    document.getElementById('move-bar-fill').style.width = `${pct}%`;
  }

  // Direction buttons: enabled only when in move phase with points left
  document.querySelectorAll('.dir-btn').forEach(btn => {
    btn.disabled = !isMove || noMoves;
  });

  // End turn: available once dice have been rolled
  document.getElementById('btn-end-turn').disabled = isRoll;

  renderMap();
}

// ── Dice roll ─────────────────────────────────────────────────────────────
document.getElementById('btn-roll-die').addEventListener('click', async () => {
  if (!G || G.phase !== 'roll') return;

  const btn = document.getElementById('btn-roll-die');
  const face = document.getElementById('die-face');
  btn.disabled = true;
  btn.classList.add('rolling');

  // Show random numbers while spinning
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

// ── Movement ──────────────────────────────────────────────────────────────
document.getElementById('movement-pad').addEventListener('click', async (e) => {
  const btn = e.target.closest('.dir-btn');
  if (!btn || btn.disabled || !G) return;
  const dx = parseInt(btn.dataset.dx, 10);
  const dy = parseInt(btn.dataset.dy, 10);
  await doMove(dx, dy);
});

window.addEventListener('keydown', (e) => {
  const KEY_MAP = {
    ArrowUp: [0,-1], ArrowDown: [0,1], ArrowLeft: [-1,0], ArrowRight: [1,0],
    Numpad7: [-1,-1], Numpad8: [0,-1], Numpad9: [1,-1],
    Numpad4: [-1, 0], Numpad5: [0, 0], Numpad6: [1, 0],
    Numpad1: [-1, 1], Numpad2: [0, 1], Numpad3: [1, 1],
  };
  const move = KEY_MAP[e.code];
  if (move && G && G.phase === 'move' && G.player.movement_remaining > 0) {
    e.preventDefault();
    doMove(move[0], move[1]);
  }
});

async function doMove(dx, dy) {
  const result = await api('POST', `/api/games/${G.game_id}/move`, { game_id: G.game_id, dx, dy });
  if (!result) return;
  G = result.game_state;
  syncUI();
  const cls = result.move_cost === 0 ? 'warn' : 'highlight';
  logMessage(result.message, cls);

  if (G.player.movement_remaining <= 0) {
    logMessage('No movement remaining — end your turn or wait.', 'warn');
  }
}

// ── End turn ──────────────────────────────────────────────────────────────
document.getElementById('btn-end-turn').addEventListener('click', async () => {
  if (!G) return;
  const result = await api('POST', `/api/games/${G.game_id}/end-turn`);
  if (!result) return;
  G = result.game_state;
  document.getElementById('die-face').textContent = 'd8';
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

// ── Canvas rendering ──────────────────────────────────────────────────────
const canvas = document.getElementById('map-canvas');
const ctx    = canvas.getContext('2d');

const TERRAIN_COLORS = {
  ocean:     '#1a3a5c',
  coast:     '#c2b280',
  plains:    '#6b8c42',
  forest:    '#2d5a27',
  hills:     '#8c7340',
  mountains: '#6e6e6e',
  river:     '#2a6496',
};

function elevationColor(e) {
  const v = Math.round(e * 255);
  return `rgb(${v},${v},${v})`;
}

function renderMap() {
  if (!G) return;
  const W = canvas.parentElement.clientWidth;
  const H = canvas.parentElement.clientHeight - 110; // subtract log height
  canvas.width  = Math.max(1, W);
  canvas.height = Math.max(1, H);

  const tw = W / G.map_width;
  const th = H / G.map_height;

  G.tiles.forEach(tile => {
    ctx.fillStyle = mapMode === 'elevation'
      ? elevationColor(tile.elevation)
      : (TERRAIN_COLORS[tile.terrain] || '#333');
    ctx.fillRect(tile.x * tw, tile.y * th, Math.ceil(tw), Math.ceil(th));
  });

  // Player marker
  const [px, py] = G.player.position;
  const cx = px * tw + tw / 2;
  const cy = py * th + th / 2;
  const r  = Math.max(2, Math.min(tw, th) * 0.38);

  ctx.beginPath();
  ctx.arc(cx, cy, r + 2, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(0,0,0,0.5)';
  ctx.fill();

  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = '#e8c84a';
  ctx.fill();
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
