'use strict';
// Interfaccia principale: giocatori, club, impostazioni. Usa common.js.

// ================================================================ impostazioni
const SETTINGS = { factor: 'fm07.factor', auto: 'fm07.autofactor', adv: 'fm07.adv' };
let gameRate = null; // cambio letto dal gioco (valuta scelta nelle preferenze)
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* ignora */ } },
};
function factor() {
  if (store.get(SETTINGS.auto, '1') === '1' && gameRate) return gameRate;
  const f = Number(parseNum(store.get(SETTINGS.factor, '1'), 'double'));
  return f > 0 ? f : 1;
}
// valore in memoria -> cifra mostrata dal gioco
function moneyMult(kind) {
  if (kind === 'money') return factor();
  if (kind === 'wage' || kind === 'weekly') return factor() * 52; // settimanale, il gioco lo mostra all'anno
  return 1;
}
function applyAdvanced() {
  $('nav-advanced').classList.toggle('hidden', store.get(SETTINGS.adv, '0') !== '1');
}
$('btn-settings').addEventListener('click', () => {
  $('set-factor').value = store.get(SETTINGS.factor, '1');
  $('set-auto').checked = store.get(SETTINGS.auto, '1') === '1';
  $('set-game-rate').textContent = gameRate ? `Il gioco ora usa il cambio ×${gameRate}.` : 'Cambio del gioco non disponibile (non agganciato).';
  $('set-adv').checked = store.get(SETTINGS.adv, '0') === '1';
  $('settings').classList.remove('hidden');
});
$('set-close').addEventListener('click', () => {
  store.set(SETTINGS.factor, $('set-factor').value || '1');
  store.set(SETTINGS.auto, $('set-auto').checked ? '1' : '0');
  store.set(SETTINGS.adv, $('set-adv').checked ? '1' : '0');
  $('settings').classList.add('hidden');
  applyAdvanced();
  if (player) renderPlayer(player.data);
  if (club && club.fin) renderFinances();
});
$('settings').addEventListener('click', (ev) => { if (ev.target.id === 'settings') $('set-close').click(); });

// =================================================================== navigazione
function showTab(name) {
  document.querySelectorAll('.sidebar .tab').forEach((x) => x.classList.toggle('active', x.dataset.tab === name));
  document.querySelectorAll('main > .panel').forEach((p) => p.classList.toggle('active', p.id === 'tab-' + name));
}
document.querySelectorAll('.sidebar .tab').forEach((b) => b.addEventListener('click', () => showTab(b.dataset.tab)));

function wireSubtabs(tabsId, container) {
  $(tabsId).querySelectorAll('.subtab').forEach((b) => b.addEventListener('click', () => {
    $(tabsId).querySelectorAll('.subtab').forEach((x) => x.classList.toggle('active', x === b));
    container.querySelectorAll('.subpanel').forEach((p) => p.classList.toggle('active', p.dataset.sub === b.dataset.sub));
  }));
}
wireSubtabs('d-tabs', $('pl-detail'));
wireSubtabs('c-tabs', $('cl-detail'));

// ====================================================================== aggancio
let attached = false;
function setAttached(on, pid) {
  const s = $('status');
  s.className = 'pill ' + (on ? 'on' : 'off');
  s.textContent = on ? `Collegato al gioco (PID ${pid})` : 'Non agganciato';
  $('btn-attach').classList.toggle('hidden', on);
  if (on && !attached) { attached = true; loadHumanClubs(); loadPlayers(true); loadClubNames(); loadClubs(); loadTactics(); }
  if (!on) attached = false;
}
// scorciatoie alle squadre allenate da un utente (oggetti allenatore umano, vedi clubs.human_clubs)
let humanClubs = [];
async function loadHumanClubs() {
  const box = $('human-clubs');
  if (!box.childElementCount) {  // primo caricamento: mostra la sezione con "Ricerca…"
    box.append(el('div', { class: 'tab muted' }, el('i', { class: 'spinner' }), 'Ricerca…'));
    $('nav-human').classList.remove('hidden');
  }
  const r = await api('clubs/human');
  box.innerHTML = '';
  const items = r.ok ? r.items : [];
  humanClubs = items;
  if (items.length && !$('t-club').value) $('t-club').value = items[0].name;
  for (const c of items) {
    const b = el('button', { class: 'tab', title: `Allenatore: ${c.manager}` }, el('span', { class: 'ico' }, '★'), c.name);
    b.addEventListener('click', () => { showTab('clubs'); openClub(c); });
    box.append(b);
  }
  $('nav-human').classList.toggle('hidden', !items.length);
}
$('btn-attach').addEventListener('click', async () => {
  const r = await call('attach', { name: 'fm.exe' });
  if (r) setAttached(true, r.pid); else setAttached(false);
});

// ===================================================================== utilità
// cifra in memoria -> testo breve nella valuta del gioco (es. 6,75 M · 950 k)
function fmtMoney(raw) {
  const v = raw * factor();
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toLocaleString('it-IT', { maximumFractionDigits: 2 })} M`;
  if (Math.abs(v) >= 1e3) return `${Math.round(v / 1e3).toLocaleString('it-IT')} k`;
  return Math.round(v).toLocaleString('it-IT');
}
const fmtDate = (d) => (d ? d.split('-').reverse().join('/') : '');
function debounce(fn, ms = 250) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
function moraleLabel(v) {
  if (v >= 19) return 'Ottimo?';
  if (v >= 16) return 'Molto buono';
  if (v >= 13) return 'Buono';
  if (v >= 9) return 'Ok';
  if (v >= 5) return 'Basso';
  return 'Molto basso?';
}
const attrLevel = (v) => (v >= 16 ? 'lv5' : v >= 13 ? 'lv4' : v >= 10 ? 'lv3' : v >= 6 ? 'lv2' : 'lv1');
const roleLevel = (v) => (v >= 18 ? 'r5' : v >= 15 ? 'r4' : v >= 11 ? 'r3' : v >= 6 ? 'r2' : 'r1');

// ================================================================= elenco giocatori
const listState = { sort: 'ca', desc: true };
function loadPlayers(refresh = false) {
  if (!attached && !refresh) return Promise.resolve();
  const btn = $('pl-search');
  btn.disabled = true; btn.classList.add('working'); btn.textContent = 'Ricerca…';
  return withLoading('pl-wrap', () => loadPlayersNow(refresh)).finally(() => {
    btn.disabled = false; btn.classList.remove('working'); btn.textContent = 'Cerca';
  });
}
async function loadPlayersNow(refresh) {
  $('pl-info').textContent = refresh ? 'Lettura dei giocatori dal gioco…' : 'Ricerca…';
  const r = await call('players', {
    query: $('pl-q').value, club: $('pl-club').value, club_contains: true, role: $('pl-role').value,
    ca_min: Number($('pl-ca').value) || 0, injured: $('pl-inj').checked, nation: $('pl-nation').value,
    asking_min: askingRaw('pl-ask-min'), asking_max: askingRaw('pl-ask-max'),
    age_min: Number($('pl-age-min').value) || 0, age_max: Number($('pl-age-max').value) || 0,
    sort: listState.sort, desc: listState.desc, refresh, limit: 400,
  });
  if (!r) { $('pl-info').textContent = 'Lettura non riuscita.'; return; }
  const dl = $('nation-names');
  if (r.nations && dl.childElementCount !== r.nations.length) {
    dl.innerHTML = '';
    r.nations.forEach((n) => dl.append(el('option', { value: n })));
  }
  $('pl-info').textContent = `${r.count.toLocaleString('it-IT')} giocatori` +
    (r.count > r.items.length ? ` (mostro i primi ${r.items.length})` : '');
  const body = $('pl-body');
  body.innerHTML = '';
  for (const x of r.items) {
    const name = el('td', { title: x.name }, x.name);
    if (x.injured) name.append(el('span', { class: 'inj-tag' }, 'INF'));
    const ask = x.asking === -1 ? el('td', { class: 'num muted', title: 'Giocatore del tuo club' }, 'tuo')
      : x.asking === 0 ? el('td', { class: 'num muted', title: 'Non ancora calcolato dal club' }, '?')
        : el('td', { class: 'num', title: Math.round(x.asking * factor()).toLocaleString('it-IT') }, fmtMoney(x.asking));
    const tr = el('tr', {}, name, el('td', { class: 'club', title: x.club_label }, x.club_label || '—'),
      el('td', { class: 'club', title: x.nation }, x.nation || '–'), el('td', {}, x.role),
      el('td', { class: 'num' }, x.age ?? '–'),
      el('td', { class: 'num', title: Math.round(x.value * factor()).toLocaleString('it-IT') }, fmtMoney(x.value)), ask,
      el('td', { class: 'num' }, x.ca), el('td', { class: 'num' }, x.pa));
    tr.dataset.address = x.address;
    if (player && player.address === x.address) tr.classList.add('sel');
    tr.addEventListener('click', () => openPlayer(x));
    body.append(tr);
  }
  document.querySelectorAll('#tab-players th[data-sort]').forEach((th) => {
    th.classList.toggle('sorted', th.dataset.sort === listState.sort);
    th.classList.toggle('asc', th.dataset.sort === listState.sort && !listState.desc);
  });
}
// la ricerca parte solo con il pulsante Cerca o con Invio in un campo dei filtri
$('pl-search').addEventListener('click', () => loadPlayers());
document.querySelectorAll('#tab-players .filters input').forEach((inp) => inp.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); loadPlayers(); }
}));
// prezzo in milioni nella valuta del gioco -> sterline come in memoria (null = nessun limite)
function askingRaw(id) {
  const t = $(id).value.trim().replace(',', '.');
  if (!t) return null;
  const v = Number(t);
  return Number.isFinite(v) && v >= 0 ? Math.round((v * 1e6) / factor()) : null;
}
$('pl-refresh').addEventListener('click', () => { loadHumanClubs(); loadPlayers(true); });
document.querySelectorAll('#tab-players th[data-sort]').forEach((th) => th.addEventListener('click', () => {
  if (listState.sort === th.dataset.sort) listState.desc = !listState.desc;
  else { listState.sort = th.dataset.sort; listState.desc = ['ca', 'pa', 'value', 'asking'].includes(th.dataset.sort); }
  loadPlayers();
}));

// ================================================================ scheda giocatore
let player = null; // { address, info, data }
let returnTo = null; // 'clubs' se il giocatore è stato aperto dalla rosa di un club

function makeInput(a) {
  const kind = a.kind || 'number';
  const money = kind === 'wage' || kind === 'money';
  const shown = money ? Math.round(a.value * moneyMult(kind)) : a.value;
  const inp = kind === 'number'
    ? el('input', { type: 'number', min: a.min, max: a.max, value: shown })
    : el('input', { type: 'text', value: money ? shown.toLocaleString('it-IT') : shown });
  inp.title = `in memoria: ${a.raw}`;
  if (a.field) inp.dataset.field = a.field; else inp.dataset.offset = a.offset;
  Object.assign(inp.dataset, { kind, orig: String(shown), min: a.min, max: a.max });
  inp.addEventListener('input', () => {
    const v = kind === 'date' ? inp.value.trim() : String(Number(money ? parseNum(inp.value, 'int32') : inp.value));
    inp.classList.toggle('dirty', v !== inp.dataset.orig);
    if (inp.dataset.attr) { inp.className = inp.className.replace(/lv\d/, '') ; inp.classList.add(attrLevel(Number(inp.value))); }
    if (inp.dataset.role) { inp.className = inp.className.replace(/r\d/, ''); inp.classList.add(roleLevel(Number(inp.value))); }
    updateDirty();
  });
  return inp;
}

function formRow(a, label) {
  const inp = makeInput(a);
  return el('div', { class: 'frow' }, el('label', {}, label || a.name), inp);
}

// posizioni sul campo disegnato (alto = attacco)
const PITCH = {
  'pos:50': [11, 50, 'Punta'],
  'pos:47': [27, 17, 'TS'], 'pos:48': [27, 50, 'TC'], 'pos:49': [27, 83, 'TD'],
  'pos:44': [45, 17, 'CS'], 'pos:45': [45, 50, 'CC'], 'pos:46': [45, 83, 'CD'],
  'pos:51': [62, 12, 'Esterno S'], 'pos:43': [62, 50, 'Mediano'], 'pos:52': [62, 88, 'Esterno D'],
  'pos:40': [78, 17, 'DS'], 'pos:41': [78, 50, 'DC'], 'pos:42': [78, 83, 'DD'],
  'pos:28': [93, 50, 'Portiere'],
};

function renderPlayer(data) {
  const by = new Map();
  for (const a of data.attributes) { if (!by.has(a.group)) by.set(a.group, []); by.get(a.group).push(a); }
  const get = (f) => data.attributes.find((a) => a.field === f);

  // intestazione
  const ca = get('ca'), pa = get('pa'), cond = get('cond'), mor = get('morale');
  $('d-ca').textContent = ca ? ca.value : '–';
  $('d-pa').textContent = pa ? pa.value : '–';
  $('d-cond').textContent = cond ? cond.value + '%' : '–';
  $('d-mor').textContent = mor ? moraleLabel(mor.value) : '–';

  // attributi
  const attr = $('d-attr'); attr.innerHTML = '';
  for (const g of ['Tecniche', 'Mentali', 'Fisiche', 'Portiere', 'Nascosti e piedi']) {
    if (!by.has(g)) continue;
    const box = el('div', { class: 'group' }, el('h3', {}, g));
    for (const a of [...by.get(g)].sort((x, y) => x.name.localeCompare(y.name, 'it'))) {
      const inp = makeInput(a);
      inp.dataset.attr = '1';
      inp.classList.add(attrLevel(a.value));
      box.append(el('div', { class: 'arow' }, el('span', {}, a.name), inp));
    }
    attr.append(box);
  }

  // generale: abilità, stato, infortuni
  const gen = $('d-gen'); gen.innerHTML = '';
  const col = (title, items, labels = {}) => {
    const box = el('div', { class: 'group' }, el('h3', {}, title));
    items.forEach((a) => box.append(formRow(a, labels[a.field])));
    return box;
  };
  gen.append(col('Abilità', by.get('Abilità') || []));
  gen.append(col('Stato', by.get('Stato') || [], {
    cond: 'Condizione %', fitness: el('span', {}, 'Ritmo partita %', el('small', {}, 'serve per arrivare al 100%')), morale: el('span', {}, 'Morale (0-20)', el('small', {}, 'Basso 5-8 · Ok 9-12 · Buono 13-15 · Molto buono 16-18')),
  }));
  if (by.has('Infortuni')) gen.append(col('Infortuni', by.get('Infortuni')));
  $('d-heal').classList.toggle('hidden', !by.has('Infortuni'));

  // ruoli: campo + elenco posizioni generiche
  const pitch = $('d-pitch'); pitch.innerHTML = '';
  for (const a of [...(by.get('Ruoli in campo') || []), ...(by.get('Ruoli') || []).filter((r) => r.field === 'pos:28')]) {
    const spot = PITCH[a.field];
    if (!spot) continue;
    const inp = makeInput(a);
    inp.dataset.role = '1';
    inp.classList.add(roleLevel(a.value));
    const s = el('div', { class: 'spot' }, inp, el('small', {}, spot[2]));
    s.style.top = spot[0] + '%'; s.style.left = spot[1] + '%';
    pitch.append(s);
  }
  const roles = $('d-roles'); roles.innerHTML = '';
  roles.append(col('Ruoli (database: 20 = naturale)', (by.get('Ruoli') || []).filter((r) => r.field !== 'pos:28')));

  // contratto
  const ctr = $('d-contract'); ctr.innerHTML = '';
  if (by.has('Contratto')) {
    ctr.append(col('Contratto', by.get('Contratto'), {
      wage: el('span', {}, 'Stipendio annuo', el('small', {}, `in memoria a settimana · cambio ×${factor()}`)),
      start: el('span', {}, 'Inizio', el('small', {}, 'gg/mm/aaaa')),
      expiry: el('span', {}, 'Scadenza', el('small', {}, 'gg/mm/aaaa')),
    }));
  } else {
    ctr.append(el('p', { class: 'muted' }, 'Nessun contratto (svincolato o giocatore senza club).'));
  }
  if (by.has('Mercato')) {
    ctr.append(col('Mercato', by.get('Mercato'), {
      value: el('span', {}, 'Valore', el('small', {}, `cambio ×${factor()}`)),
      asking: el('span', {}, 'Prezzo richiesto dal club', el('small', {}, '-1 = tuo club · 0 = non calcolato')),
    }));
  }
  updateDirty();
}

function updateDirty() {
  const n = document.querySelectorAll('#pl-detail input.dirty').length;
  $('d-save').disabled = n === 0;
  $('d-dirty').textContent = n ? `${n} modifiche` : '';
}

async function openPlayer(info) {
  if (player && document.querySelectorAll('#pl-detail input.dirty').length &&
      !confirm('Ci sono modifiche non salvate. Le perdi?')) return;
  const r = await withLoading(player ? 'pl-detail' : 'pl-wrap', () => call('player/get', { address: info.address }));
  if (!r) return;
  player = { address: info.address, info, data: r };
  returnTo = null; // la rosa del club lo reimposta subito dopo, se il giocatore è stato aperto da lì
  $('pl-detail').classList.remove('empty');
  $('d-name').textContent = info.name;
  const sub = [info.club_label || info.club || 'Senza club', info.role,
    info.age != null ? `${info.age} anni` : '', info.birth ? `nato il ${fmtDate(info.birth)}` : ''].filter(Boolean);
  $('d-sub').textContent = sub.join(' · ');
  document.querySelectorAll('#pl-body tr').forEach((tr) => tr.classList.toggle('sel', tr.dataset.address === info.address));
  renderPlayer(r);
}

function closePlayer() {
  if (!player) return true;
  if (document.querySelectorAll('#pl-detail input.dirty').length && !confirm('Ci sono modifiche non salvate. Chiudere lo stesso?')) return false;
  player = null;
  $('pl-detail').classList.add('empty');
  document.querySelectorAll('#pl-body tr.sel').forEach((tr) => tr.classList.remove('sel'));
  if (returnTo === 'clubs') { returnTo = null; showTab('clubs'); }
  return true;
}
$('d-close').addEventListener('click', closePlayer);
$('d-back').addEventListener('click', closePlayer);

function closeClub() {
  if (!club) return;
  if (document.querySelector('#cl-detail .dirty') && !confirm('Ci sono modifiche non salvate. Chiudere lo stesso?')) return;
  club = null;
  $('cl-detail').classList.add('empty');
  document.querySelectorAll('#cl-body tr.sel').forEach((tr) => tr.classList.remove('sel'));
}
$('c-close').addEventListener('click', closeClub);
$('c-back').addEventListener('click', closeClub);

document.addEventListener('keydown', (ev) => {
  if (ev.key !== 'Escape') return;
  if (!$('settings').classList.contains('hidden')) { $('set-close').click(); return; }
  if ($('tab-players').classList.contains('active')) closePlayer();
  else if ($('tab-clubs').classList.contains('active')) closeClub();
});

$('d-reload').addEventListener('click', async () => {
  if (!player) return;
  const r = await call('player/get', { address: player.address });
  if (r) { player.data = r; renderPlayer(r); }
});
$('d-save').addEventListener('click', async () => {
  if (!player) return;
  const changes = [];
  for (const inp of document.querySelectorAll('#pl-detail input.dirty')) {
    const kind = inp.dataset.kind || 'number';
    if (kind === 'date') { changes.push({ field: inp.dataset.field, value: inp.value.trim() }); continue; }
    if (kind === 'wage' || kind === 'money') {
      const v = Number(parseNum(inp.value, 'int32'));
      if (!Number.isFinite(v) || v < 0) return toast(`Valore non valido: ${inp.value}`, true);
      changes.push({ field: inp.dataset.field, value: Math.round(v / moneyMult(kind)) });
      continue;
    }
    const v = Number(inp.value);
    const lo = Number(inp.dataset.min), hi = Number(inp.dataset.max);
    if (!Number.isInteger(v) || v < lo || v > hi || (v === 0 && lo > 0)) return toast(`Valori ammessi: da ${lo} a ${hi}`, true);
    changes.push(inp.dataset.field ? { field: inp.dataset.field, value: v } : { offset: Number(inp.dataset.offset), value: v });
  }
  const ca = document.querySelector('#pl-detail input[data-field="ca"]');
  const pa = document.querySelector('#pl-detail input[data-field="pa"]');
  if (ca && pa && Number(pa.value) > 0 && Number(ca.value) > Number(pa.value) &&
      !confirm('La CA è più alta della PA: il gioco potrebbe riportarla giù. Salvare lo stesso?')) return;
  const r = await call('player/set', { address: player.address, changes });
  if (!r) return;
  toast(`Salvate ${r.written} modifiche.\nNel gioco cambia schermata per vederle.`);
  player.data = r;
  renderPlayer(r);
});
$('d-heal').addEventListener('click', async () => {
  if (!player || !confirm('Togliere tutti gli infortuni e portare la condizione al 100%?')) return;
  const r = await call('player/heal', { address: player.address });
  if (!r) return;
  toast(`Guarito (${r.healed} infortuni tolti).`);
  player.data = r;
  renderPlayer(r);
  loadPlayers();
});

// ========================================================================= club
let club = null; // { info, fin }
async function loadClubNames() {
  const r = await call('clubs', { query: '', limit: 20000 });
  if (!r) return;
  const dl = $('club-names');
  dl.innerHTML = '';
  for (const c of r.items) dl.append(el('option', { value: c.name }));
}
async function loadClubs() {
  const r = await withLoading('cl-wrap', () => call('clubs', { query: $('cl-q').value, limit: 300 }));
  if (!r) return;
  $('cl-info').textContent = `${r.count.toLocaleString('it-IT')} club` + (r.count > r.items.length ? ` (primi ${r.items.length})` : '');
  const body = $('cl-body');
  body.innerHTML = '';
  for (const c of r.items) {
    const tr = el('tr', {}, el('td', {}, c.name));
    tr.dataset.address = c.address;
    if (club && club.info.address === c.address) tr.classList.add('sel');
    tr.addEventListener('click', () => openClub(c));
    body.append(tr);
  }
}
$('cl-search').addEventListener('click', () => loadClubs());
$('cl-q').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); loadClubs(); } });

function renderFinances() {
  const box = $('c-fin'); box.innerHTML = '';
  if (!club.fin) return;
  const labels = {
    balance: 'Saldo (Bilancio)', budget_remaining: 'Fondo trasferimenti rimanente', budget_season: 'Fondo trasferimenti stagione',
    transfer_pct: '% entrate dal mercato disponibili', wage_budget: 'Budget ingaggi annuo', youth_budget: 'Finanziamento settore giovanile',
    wage_spend: 'Spesa ingaggi attuale (calcolata)',
  };
  const g = el('div', { class: 'group' }, el('h3', {}, `Finanze · cambio ×${factor()}`));
  for (const f of club.fin.fields) {
    const a = { field: f.key, kind: f.kind === 'number' ? 'number' : (f.kind === 'weekly' ? 'wage' : 'money'),
      value: f.value, raw: f.value, min: 0, max: f.kind === 'number' ? 100 : 2e9 };
    const row = formRow(a, labels[f.key] || f.name);
    if (!f.editable) row.querySelector('input').disabled = true;
    g.append(row);
  }
  box.append(g);
  box.querySelectorAll('input').forEach((i) => i.addEventListener('input', clubSaveState));
  clubSaveState();
}

// ------------------------------------------------------------ informazioni club
const CLUB_STATUS = { 1: 'Professionisti', 2: 'Semi-professionisti', 3: 'Dilettanti' };
const TEAM_LABEL = { first: 'prima squadra', reserves: 'riserve', youth: 'giovanili' };

function clubSaveState() {
  $('c-save').disabled = !document.querySelector('#cl-detail .dirty');
}
// input/select/checkbox generico: segna "dirty" quando cambia rispetto al valore letto
function trackDirty(inp, orig, read) {
  inp.dataset.orig = String(orig);
  const upd = () => { inp.classList.toggle('dirty', String(read()) !== inp.dataset.orig); clubSaveState(); };
  inp.addEventListener('input', upd);
  inp.addEventListener('change', upd);
  return inp;
}
function infoRow(label, inp, hint) {
  return el('div', { class: 'frow' }, el('label', {}, label, ...(hint ? [el('small', {}, hint)] : [])), inp);
}

function renderInfo() {
  const box = $('c-info'); box.innerHTML = '';
  if (!club.data) return;
  const f = Object.fromEntries(club.data.fields.map((x) => [x.key, x]));
  const num = (k, hint) => {
    const x = f[k];
    const inp = el('input', { type: 'number', min: x.min, max: x.max, value: x.value });
    inp.dataset.info = k;
    return infoRow(x.name, trackDirty(inp, x.value, () => Number(inp.value)), hint);
  };

  const gen = el('div', { class: 'group' }, el('h3', {}, 'Panoramica'));
  gen.append(num('founded'));
  const st = el('select', {});
  for (const [v, t] of Object.entries(CLUB_STATUS)) st.append(el('option', { value: v }, t));
  if (!CLUB_STATUS[f.status.value]) st.append(el('option', { value: f.status.value }, `? (${f.status.value})`));
  st.value = String(f.status.value);
  st.dataset.info = 'status';
  gen.append(infoRow('Stato', trackDirty(st, f.status.value, () => st.value)));
  for (const t of club.data.teams) {
    const inp = el('input', { type: 'number', min: 0, max: 10000, step: 50, value: t.reputation });
    inp.dataset.team = t.address;
    gen.append(infoRow(`Reputazione ${TEAM_LABEL[t.kind] || ''}`.trim(),
      trackDirty(inp, t.reputation, () => Number(inp.value)), '0-10000'));
  }

  const str = el('div', { class: 'group' }, el('h3', {}, 'Strutture'));
  str.append(num('training', '1-20'), num('youth', '1-20'));
  const ac = el('input', { type: 'checkbox' });
  ac.checked = !!f.academy.value;
  ac.dataset.info = 'academy';
  str.append(infoRow(f.academy.name, trackDirty(ac, f.academy.value ? 1 : 0, () => (ac.checked ? 1 : 0))));

  const att = el('div', { class: 'group' }, el('h3', {}, 'Spettatori'));
  att.append(num('attendance'), num('min_attendance'), num('max_attendance'), num('season_tickets'));

  box.append(gen, str, att);

  if (club.data.colors.length) {
    const col = el('div', { class: 'group' }, el('h3', {}, 'Colori sociali'));
    club.data.colors.forEach((c, i) => {
      const inp = el('input', { type: 'color', value: c.toLowerCase() });
      inp.dataset.color = i;
      col.append(infoRow(`Colore ${i + 1}`, trackDirty(inp, c.toLowerCase(), () => inp.value.toLowerCase()), c));
    });
    box.append(col);
  }
  clubSaveState();
}

async function saveClubInfo() {
  const changes = {}, reputation = {}, colors = {};
  for (const inp of document.querySelectorAll('#c-info .dirty')) {
    if (inp.dataset.color !== undefined) { colors[inp.dataset.color] = inp.value; continue; }
    const v = inp.type === 'checkbox' ? (inp.checked ? 1 : 0) : Number(inp.value);
    if (!Number.isInteger(v)) { toast(`Valore non valido: ${inp.value}`, true); return false; }
    if (inp.dataset.team) reputation[inp.dataset.team] = v; else changes[inp.dataset.info] = v;
  }
  const r = await call('club/info/set', { address: club.info.address, changes, reputation, colors });
  if (!r) return false;
  club.data = r;
  renderInfo();
  return r.written;
}

async function openClub(c) {
  club = { info: c, fin: null, data: null };
  $('cl-detail').classList.remove('empty');
  $('c-name').textContent = c.name;
  $('c-sub').textContent = `ID ${c.id}`;
  document.querySelectorAll('#cl-body tr').forEach((tr) => tr.classList.toggle('sel', tr.dataset.address === c.address));
  const [ri, r] = await withLoading('cl-detail', () => Promise.all([api('club/info', { address: c.address }), api('club/finances', { address: c.address })]));
  if (!club || club.info !== c) return; // nel frattempo è stato aperto un altro club
  club.data = ri.ok ? ri : null;
  if (!ri.ok) toast(ri.error || 'Errore', true);
  renderInfo();
  club.fin = r.ok ? r : null;
  $('c-nofin').classList.toggle('hidden', !!club.fin);
  $('c-fin').innerHTML = '';
  $('c-save').disabled = true;
  if (club.fin) renderFinances();
  loadSquad();
}

const squadState = { sort: 'ca', desc: true };
document.querySelectorAll('#c-squad-table th[data-sort]').forEach((th) => th.addEventListener('click', () => {
  if (squadState.sort === th.dataset.sort) squadState.desc = !squadState.desc;
  else { squadState.sort = th.dataset.sort; squadState.desc = ['ca', 'pa'].includes(th.dataset.sort); }
  loadSquad();
}));

async function loadSquad() {
  if (!club) return;
  const s = await withLoading('c-squad-wrap', () => call('players', { club: club.info.name, team: $('c-team').value, limit: 300,
    sort: squadState.sort, desc: squadState.desc }));
  document.querySelectorAll('#c-squad-table th[data-sort]').forEach((th) => {
    th.classList.toggle('sorted', th.dataset.sort === squadState.sort);
    th.classList.toggle('asc', th.dataset.sort === squadState.sort && !squadState.desc);
  });
  const body = $('c-squad'); body.innerHTML = '';
  if (!s) return;
  for (const x of s.items) {
    const name = el('td', { title: x.name }, x.name);
    if (x.injured) name.append(el('span', { class: 'inj-tag' }, 'INF'));
    const other = (x.squads || []).filter((q) => q.club !== club.info.name).map((q) => q.club).join(', ');
    if (x.loan === 'in') name.append(el('span', { class: 'loan-tag', title: `in prestito da ${other}` }, 'IN PRESTITO'));
    if (x.loan === 'out') name.append(el('span', { class: 'loan-tag out', title: `in prestito a ${other}` }, `PRESTATO · ${other}`));
    if (x.loan === 'co') name.append(el('span', { class: 'loan-tag co', title: `comproprietà con ${other}` }, 'COMPROPRIETÀ'));
    const tr = el('tr', {}, name, el('td', {}, x.role), el('td', { class: 'num' }, x.age ?? '–'),
      el('td', { class: 'num' }, x.ca), el('td', { class: 'num' }, x.pa));
    tr.addEventListener('click', async () => {
      showTab('players');
      await openPlayer(x);
      if (player && player.address === x.address) returnTo = 'clubs';
    });
    body.append(tr);
  }
  if (!s.items.length) body.append(el('tr', {}, el('td', { colspan: 5, class: 'muted' }, 'Nessun giocatore in questa squadra.')));
}
$('c-team').addEventListener('change', loadSquad);
async function boostSquad(what) {
  if (!club) return;
  const teamSel = $('c-team');
  const teamName = teamSel.options[teamSel.selectedIndex].text.toLowerCase();
  const target = `${club.info.name} (${teamName})`;
  const spec = {
    heal: [`Togliere tutti gli infortuni a ${target}?`, { heal: true }, (r) => `Guariti ${r.healed} giocatori su ${r.players}`],
    morale: [`Portare il morale al massimo per ${target}?`, { morale: 20 }, (r) => `Morale al massimo per ${r.morale} giocatori su ${r.players}`],
    cond: [`Portare condizione e ritmo partita al 100% per ${target}?`, { condition: true }, (r) => `Condizione e ritmo al 100% per ${r.condition} giocatori su ${r.players}`],
  }[what];
  if (!confirm(spec[0])) return;
  const r = await withLoading('c-squad-wrap', () => call('squad/boost', { club: club.info.name, team: teamSel.value, ...spec[1] }));
  if (!r) return;
  toast(spec[2](r) + (r.errors ? ` (${r.errors} non modificati)` : ''));
  loadSquad();
  if (player) { const g = await call('player/get', { address: player.address }); if (g) { player.data = g; renderPlayer(g); } }
}
$('c-morale').addEventListener('click', () => boostSquad('morale'));
$('c-heal').addEventListener('click', () => boostSquad('heal'));
$('c-cond').addEventListener('click', () => boostSquad('cond'));
$('c-reload').addEventListener('click', () => club && openClub(club.info));
$('c-save').addEventListener('click', async () => {
  if (!club) return;
  let saved = 0;
  if (document.querySelector('#c-info .dirty')) {
    const n = await saveClubInfo();
    if (n === false) return;
    saved += n;
  }
  if (!club.fin || !document.querySelector('#c-fin input.dirty')) {
    if (saved) toast(`Salvati ${saved} valori.\nNel gioco riapri la schermata del club per vederli.`);
    return;
  }
  const changes = {};
  for (const inp of document.querySelectorAll('#c-fin input.dirty')) {
    const kind = inp.dataset.kind;
    const v = Number(parseNum(inp.value, 'int32'));
    if (!Number.isFinite(v)) return toast(`Valore non valido: ${inp.value}`, true);
    changes[inp.dataset.field] = kind === 'number' ? v : Math.round(v / moneyMult(kind));
  }
  const r = await call('club/finances/set', { address: club.info.address, changes });
  if (!r) return;
  toast(`Salvati ${saved + r.written} valori.\nNel gioco riapri la schermata del club per vederli.`);
  club.fin = r;
  renderFinances();
});

// ===================================================================== tattica
// La tattica si legge dal file .tac salvato (backend/tactics.py); posizioni su una griglia 5 colonne x 6 file.
const T_COL = { L: 10, CL: 30, C: 50, CR: 70, R: 90 };
const T_ROW = { ST: 11, AM: 29, M: 47, DM: 63, D: 78, GK: 93 };
const T_ROW_NAME = { ST: 'attacco', AM: 'trequarti', M: 'centrocampo', DM: 'mediani', D: 'difesa', GK: 'porta' };
let tactic = null;
let tacticSel = 0;

async function loadTactics() {
  const r = await call('tactics');
  if (!r) return;
  const sel = $('t-file');
  const prev = sel.value;
  sel.innerHTML = '';
  for (const t of r.items) sel.append(el('option', { value: t.file }, t.name));
  if (!r.items.length) sel.append(el('option', { value: '' }, 'Nessuna tattica salvata'));
  if (prev && r.items.some((t) => t.file === prev)) sel.value = prev;
  $('t-info').innerHTML = '';
  $('t-info').append(`Tattiche salvate in ${r.dir}. Si legge la tattica `, el('b', {}, 'salvata'),
    ': se la cambi nel gioco, salvala (Tattica → Salva) e premi Calcola.');
}

async function calcTactic() {
  if (!$('t-file').value) return toast('Nessuna tattica da leggere', true);
  const btn = $('t-go');
  btn.disabled = true; btn.textContent = 'Calcolo…';
  const r = await withLoading('t-pitch', () => call('tactic', {
    file: $('t-file').value, club: $('t-club').value,
    asking_max: askingRaw('t-ask'), age_max: Number($('t-age').value) || 0, ca_min: Number($('t-ca').value) || 0,
  })).finally(() => { btn.disabled = false; btn.textContent = 'Calcola'; });
  if (!r) return;
  tactic = r;
  renderTactic();
  renderSlot(tacticSel < r.slots.length ? tacticSel : 0);
}

function renderTactic() {
  const pitch = $('t-pitch');
  pitch.innerHTML = '';
  pitch.append(el('div', { class: 'box top' }), el('div', { class: 'box bottom' }));
  // frecce dei movimenti in attacco
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 100 100');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.innerHTML = '<defs><marker id="t-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#f0d24a"/></marker></defs>';
  for (const s of tactic.slots) {
    if (!s.run) continue;
    const line = document.createElementNS(NS, 'line');
    const x1 = T_COL[s.base.col], y1 = T_ROW[s.base.row], x2 = T_COL[s.dest.col], y2 = T_ROW[s.dest.row];
    // parte e arriva fuori dai cerchi
    const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1;
    line.setAttribute('x1', x1 + (dx / len) * 5); line.setAttribute('y1', y1 + (dy / len) * 5);
    line.setAttribute('x2', x2 - (dx / len) * 3); line.setAttribute('y2', y2 - (dy / len) * 3);
    line.setAttribute('stroke', '#f0d24a'); line.setAttribute('stroke-width', '2');
    line.setAttribute('vector-effect', 'non-scaling-stroke');
    line.setAttribute('marker-end', 'url(#t-arrow)');
    svg.append(line);
  }
  pitch.append(svg);
  tactic.slots.forEach((s, i) => {
    const p = s.pick;
    const dot = el('div', { class: 'dot ' + (p ? scoreLevel(p.score) : 'r1') }, p ? fmt1(p.score) : '–');
    const tip = p ? `${s.role} · ${p.name} · punteggio ${fmt1(p.score)} (attributi ${fmt1(p.fit)}, voto ruolo ${p.rating})` : s.role;
    const spot = el('div', { class: 'tspot' + (i === tacticSel ? ' sel' : ''), title: tip },
      dot, el('span', { class: 'lbl' }, p ? p.short || p.name : 'nessuno'), el('span', { class: 'ab' }, s.abbr));
    spot.style.left = T_COL[s.base.col] + '%';
    spot.style.top = T_ROW[s.base.row] + '%';
    spot.addEventListener('click', () => renderSlot(i));
    pitch.append(spot);
  });
}

const fmt1 = (v) => Number(v).toLocaleString('it-IT', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
// punteggio nel ruolo (scala 1-20) -> colore come i voti di ruolo
const scoreLevel = (v) => (v >= 16 ? 'r5' : v >= 14 ? 'r4' : v >= 12 ? 'r3' : v >= 10 ? 'r2' : 'r1');

function slotTable(items, market) {
  const table = el('table', { class: 'grid fit' });
  const cols = market ? ['c-name', 'c-club', 'c-n', 'c-n', 'c-n', 'c-n', 'c-money'] : ['c-name', 'c-n', 'c-n', 'c-n', 'c-n', 'c-n'];
  table.append(el('colgroup', {}, ...cols.map((c) => el('col', { class: c }))));
  const head = market ? ['Nome', 'Club', 'Età', 'Punt.', 'Attr.', 'Voto', 'Prezzo rich.'] : ['Nome', 'Età', 'Punt.', 'Attr.', 'Voto', 'CA'];
  const tips = { 'Punt.': 'Punteggio nel ruolo: attributi del ruolo corretti per quanto conosce il ruolo',
    'Attr.': 'Media pesata degli attributi che contano nel ruolo (1-20)', Voto: 'Quanto conosce il ruolo (20 naturale)' };
  const firstNum = market ? 2 : 1;
  table.append(el('thead', {}, el('tr', {}, ...head.map((h, k) => el('th', { class: k >= firstNum ? 'num' : '', title: tips[h] || '' }, h)))));
  const body = el('tbody');
  for (const x of items) {
    const name = el('td', { title: x.name }, x.name);
    if (x.injured) name.append(el('span', { class: 'inj-tag' }, 'INF'));
    const sc = [el('td', { class: 'num' }, el('b', {}, fmt1(x.score))), el('td', { class: 'num' }, fmt1(x.fit)),
      el('td', { class: 'num' }, x.rating)];
    const cells = market
      ? [name, el('td', { class: 'club', title: x.club_label }, x.club_label), el('td', { class: 'num' }, x.age ?? '–'), ...sc,
        el('td', { class: 'num', title: Math.round(x.asking * factor()).toLocaleString('it-IT') }, fmtMoney(x.asking))]
      : [name, el('td', { class: 'num' }, x.age ?? '–'), ...sc, el('td', { class: 'num' }, x.ca)];
    const tr = el('tr', {}, ...cells);
    tr.addEventListener('click', () => { showTab('players'); openPlayer(x); });
    body.append(tr);
  }
  if (!items.length) body.append(el('tr', {}, el('td', { colspan: head.length, class: 'muted' }, 'Nessun giocatore.')));
  table.append(body);
  return el('div', { class: 'table-wrap' }, table);
}

function renderSlot(i) {
  tacticSel = i;
  document.querySelectorAll('#t-pitch .tspot').forEach((s, k) => s.classList.toggle('sel', k === i));
  const s = tactic.slots[i];
  const box = $('t-slot');
  box.className = 't-slot';
  box.innerHTML = '';
  const runTxt = s.run ? ` · in attacco si sposta verso ${T_ROW_NAME[s.dest.row]}` : '';
  box.append(el('h3', {}, `${s.abbr} · ${s.role}`), el('p', { class: 'muted' },
    (s.pick ? `Consigliato: ${s.pick.name} (punteggio ${fmt1(s.pick.score)} · attributi ${fmt1(s.pick.fit)} · voto ruolo ${s.pick.rating})`
      : 'Nessun giocatore disponibile in rosa') + runTxt));
  box.append(el('h4', {}, `Migliori in rosa · ${$('t-club').value || 'nessun club scelto'}`), slotTable(s.squad, false));
  box.append(el('h4', {}, 'Migliori da acquistare (voto almeno 15, prezzo richiesto noto)'), slotTable(s.market, true));
}

$('t-go').addEventListener('click', calcTactic);
document.querySelectorAll('#tab-tactic .filters input').forEach((inp) => inp.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); calcTactic(); }
}));
document.querySelector('.sidebar .tab[data-tab="tactic"]').addEventListener('click', () => { if (attached) loadTactics(); });

// ======================================================================= avvio
setInterval(async () => {
  const st = await api('status');
  if (st.ok) setAttached(st.attached, st.pid);
  if (st.ok && st.currency && st.currency.rate !== gameRate) {
    gameRate = st.currency.rate;
    // valuta cambiata nel gioco: ridisegna le cifre, ma non se ci sono modifiche non salvate
    if (store.get(SETTINGS.auto, '1') === '1' && !document.querySelector('input.dirty')) {
      if (player) renderPlayer(player.data);
      if (club && club.fin) renderFinances();
      if (attached) loadPlayers();
    }
  }
  if (st.ok && st.attached && store.get(SETTINGS.adv, '0') === '1') toolsTick();
}, 1000);

(async () => {
  applyAdvanced();
  const st = await api('status');
  toolsInit(st.ok ? st.scan : null);
  if (st.ok) setAttached(st.attached, st.pid);
  else setAttached(false);
})();
