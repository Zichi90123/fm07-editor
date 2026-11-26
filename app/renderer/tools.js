'use strict';
// Strumenti avanzati (scanner, indirizzi salvati, memoria, ricerche): sezione "Avanzate".
// Usa le funzioni di common.js.

// ----------------------------------------------------------------- scanner
const FIRST = [
  ['exact', 'Valore esatto'], ['between', 'Tra due valori'],
  ['greater', 'Maggiore di'], ['less', 'Minore di'], ['unknown', 'Valore sconosciuto'],
];
const NEXT = [
  ['exact', 'Valore esatto'], ['changed', 'Cambiato'], ['unchanged', 'Non cambiato'],
  ['increased', 'Aumentato'], ['decreased', 'Diminuito'],
  ['increased_by', 'Aumentato di…'], ['decreased_by', 'Diminuito di…'],
  ['between', 'Tra due valori'], ['greater', 'Maggiore di'], ['less', 'Minore di'],
  ['ratio', 'Cambiato in proporzione (vecchio → nuovo)'],
];
const NEEDS_VALUE = new Set(['exact', 'between', 'greater', 'less', 'increased_by', 'decreased_by', 'ratio']);
let scanActive = false;

function fillConds(list) {
  const sel = $('s-cond');
  const prev = sel.value;
  sel.innerHTML = '';
  for (const [v, label] of list) sel.append(el('option', { value: v }, label));
  if (list.some(([v]) => v === prev)) sel.value = prev;
  updateValueInputs();
}

function updateValueInputs() {
  const c = $('s-cond').value;
  $('s-v1').disabled = !NEEDS_VALUE.has(c);
  $('s-v2-wrap').classList.toggle('hidden', c !== 'between' && c !== 'ratio');
}
$('s-cond').addEventListener('change', updateValueInputs);

function setScanState(info) {
  scanActive = !!(info && info.active);
  $('btn-next').disabled = !scanActive;
  $('s-type').disabled = scanActive;
  $('s-aligned').disabled = scanActive;
  fillConds(scanActive ? NEXT : FIRST);
  if (!scanActive) { $('scan-info').textContent = 'Nessuna scansione attiva.'; return; }
  const n = info.count.toLocaleString('it-IT');
  $('scan-info').textContent = info.unknown
    ? `Istantanea della memoria salvata (${n} valori possibili). Ora fai cambiare il valore nel gioco.`
    : `Scansione n. ${info.scans}: ${n} risultati.`;
}

function scanBody() {
  const type = $('s-type').value;
  return {
    type,
    cond: $('s-cond').value,
    value: parseNum($('s-v1').value, type),
    value2: parseNum($('s-v2').value, type),
    aligned: $('s-aligned').checked,
  };
}

async function runScan(route) {
  const btns = ['btn-first', 'btn-next', 'btn-reset'].map($);
  btns.forEach((b) => (b.disabled = true));
  $('scan-info').textContent = 'Scansione in corso…';
  const r = await call(route, scanBody());
  btns.forEach((b) => (b.disabled = false));
  if (!r) {
    $('btn-next').disabled = !scanActive;
    $('scan-info').textContent = 'Scansione non riuscita.';
    return;
  }
  setScanState(r);
  await loadResults();
}

$('btn-first').addEventListener('click', () => runScan('scan/first'));
$('btn-next').addEventListener('click', () => runScan('scan/next'));
$('btn-reset').addEventListener('click', async () => {
  const r = await call('scan/reset');
  setScanState(r);
  $('res-body').innerHTML = '';
  $('res-count').textContent = '';
});

async function loadResults() {
  const body = $('res-body');
  body.innerHTML = '';
  if (!scanActive) return;
  const r = await call('scan/results', { limit: 200 });
  if (!r) return;
  $('res-count').textContent = `(${r.count.toLocaleString('it-IT')})`;
  if (r.count > 0 && r.items.length === 0) {
    body.append(el('tr', {}, el('td', { colspan: 5, class: 'muted' }, 'Troppi risultati da mostrare: fai un\'altra scansione per restringere.')));
    return;
  }
  for (const it of r.items) {
    const add = el('button', { class: 'ghost', dataset: { addr: it.address } }, '+ Salva');
    add.addEventListener('click', () => {
      addEntry({ label: '', address: it.address, type: $('s-type').value });
      toast('Aggiunto agli indirizzi salvati');
    });
    const addrCell = el('td', { class: 'mono addr', title: 'Apri nel visore memoria' }, it.address);
    addrCell.addEventListener('click', () => openInMemory(it.address));
    body.append(el('tr', {}, el('td', { class: 'muted' }, it.n), addrCell, el('td', { class: 'mono' }, fmt(it.value)),
      el('td', { class: 'mono muted' }, fmt(it.previous)), el('td', {}, add)));
  }
  if (r.count > r.items.length) {
    body.append(el('tr', {}, el('td', { colspan: 5, class: 'muted' }, `…e altri ${(r.count - r.items.length).toLocaleString('it-IT')}`)));
  }
}

$('btn-wa').addEventListener('click', async () => {
  const v = parseNum($('wa-value').value, $('s-type').value);
  if (v === '' || Number.isNaN(Number(v))) return toast('Scrivi il valore da scrivere', true);
  const start = Number($('wa-from').value) || 1;
  const end = Number($('wa-to').value) || 0;
  const r = await call('scan/write', { value: Number(v), start, end });
  if (r) { toast(`Scritto su ${r.written} risultati (dal n. ${r.from} al n. ${r.to}).
Premi "Ripristina" per rimettere i valori originali.`); loadResults(); }
});
$('btn-wa-restore').addEventListener('click', async () => {
  const r = await call('scan/restore');
  if (r) { toast(`Ripristinati ${r.restored} valori originali`); loadResults(); }
});

// ------------------------------------------------------ indirizzi salvati
const STORE = 'fm07.entries';
let entries = [];
try { entries = JSON.parse(localStorage.getItem(STORE) || '[]'); } catch { entries = []; }
const saveEntries = () => { try { localStorage.setItem(STORE, JSON.stringify(entries)); } catch { /* ignora */ } };

function addEntry(e) {
  entries.push({ label: e.label || 'Senza nome', address: e.address, type: e.type, frozen: false });
  saveEntries();
  renderEntries();
}

$('btn-add').addEventListener('click', () => {
  const a = $('t-addr').value.trim();
  if (!/^(0x)?[0-9a-f]+$/i.test(a)) return toast('Indirizzo non valido', true);
  addEntry({ label: $('t-label').value.trim(), address: a.toLowerCase().startsWith('0x') ? a : '0x' + a, type: $('t-type').value });
  $('t-addr').value = ''; $('t-label').value = '';
});

function renderEntries() {
  const body = $('t-body');
  body.innerHTML = '';
  entries.forEach((e, i) => {
    const label = el('input', { type: 'text', value: e.label, class: 'small' });
    label.addEventListener('change', () => { e.label = label.value; saveEntries(); });
    const newVal = el('input', { type: 'text', class: 'small', placeholder: 'nuovo valore' });
    const set = el('button', {}, 'Scrivi');
    set.addEventListener('click', async () => {
      const v = parseNum(newVal.value, e.type);
      if (v === '' || Number.isNaN(Number(v))) return toast('Valore non valido', true);
      const r = await call('write', { address: e.address, type: e.type, value: Number(v) });
      if (r) { toast(`Scritto ${fmt(r.value)}`); newVal.value = ''; refreshEntries(); }
    });
    newVal.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') set.click(); });
    const freeze = el('input', { type: 'checkbox' });
    freeze.checked = !!e.frozen;
    freeze.addEventListener('change', async () => {
      const r = await call('freeze', { address: e.address, type: e.type, on: freeze.checked });
      if (r) { e.frozen = freeze.checked; saveEntries(); } else freeze.checked = !freeze.checked;
    });
    const del = el('button', { class: 'ghost danger' }, '✕');
    del.addEventListener('click', async () => {
      if (e.frozen) await call('freeze', { address: e.address, type: e.type, on: false });
      entries.splice(i, 1); saveEntries(); renderEntries();
    });
    const addrCell = el('td', { class: 'mono addr' }, e.address);
    addrCell.addEventListener('click', () => openInMemory(e.address));
    body.append(el('tr', {},
      el('td', {}, label), addrCell, el('td', {}, e.type),
      el('td', { class: 'mono', dataset: { idx: i } }, '…'),
      el('td', {}, newVal, ' ', set), el('td', {}, freeze), el('td', {}, del)));
  });
}

async function refreshEntries() {
  if (!entries.length) return;
  const res = await api('read', { items: entries.map((e) => ({ address: e.address, type: e.type })) });
  if (!res.ok) return;
  res.values.forEach((v, i) => {
    const cell = document.querySelector(`td[data-idx="${i}"]`);
    if (cell) cell.textContent = fmt(v);
  });
}

// ---------------------------------------------------------------- memoria
let lastDump = null;

function openInMemory(addr) {
  $('m-addr').value = addr;
  document.querySelector('.tab[data-tab="memory"]').click();
  dump();
}

async function dump(quiet = false) {
  const a = $('m-addr').value.trim();
  if (!a) return;
  const res = await api('dump', { address: a, length: Number($('m-len').value) });
  if (!res.ok) { if (!quiet) toast(res.error, true); return; }
  const body = $('m-body');
  body.innerHTML = '';
  const prev = lastDump && lastDump.start === res.start ? lastDump.rows : null;
  res.rows.forEach((row, ri) => {
    const hexCell = el('td', {});
    row.hex.split(' ').forEach((b, bi) => {
      const changed = prev && prev[ri] && prev[ri].hex.split(' ')[bi] !== b;
      hexCell.append(el('span', changed ? { class: 'chg' } : {}, b), ' ');
    });
    body.append(el('tr', {}, el('td', {}, row.address), hexCell, el('td', {}, row.ascii),
      el('td', {}, row.int32.map((n) => n.toLocaleString('it-IT')).join('   '))));
  });
  lastDump = res;
}

function shiftAddr(delta) {
  const a = $('m-addr').value.trim();
  if (!a) return;
  const n = Math.max(0, parseInt(a, 16) + delta);
  $('m-addr').value = hex(n);
  dump();
}

$('btn-dump').addEventListener('click', () => dump());
$('m-addr').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') dump(); });
$('btn-prev').addEventListener('click', () => shiftAddr(-256));
$('btn-next-page').addEventListener('click', () => shiftAddr(256));

// ------------------------------------------------------------------ cerca
function actionBtn(label, fn, title = '') {
  const b = el('button', { class: 'ghost', title }, label);
  b.addEventListener('click', fn);
  return b;
}

async function searchStrings() {
  const text = $('str-text').value.trim();
  const encodings = [...document.querySelectorAll('.str-enc:checked')].map((c) => c.value);
  const body = $('str-body');
  body.innerHTML = '';
  $('btn-str').disabled = true;
  $('str-info').textContent = 'Ricerca in corso…';
  const r = await call('search/string', { text, encodings, case_sensitive: $('str-case').checked });
  $('btn-str').disabled = false;
  if (!r) { $('str-info').textContent = 'Ricerca non riuscita.'; return; }
  $('str-info').textContent = r.count === 0
    ? 'Nessun risultato. Prova a cercare solo il cognome o ad attivare UTF-8.'
    : `${r.count.toLocaleString('it-IT')} risultati${r.truncated ? ' (troncati: rendi il testo più specifico)' : ''}.`;
  for (const it of r.items) {
    const ctx = el('td', { class: 'ctx', title: it.before + it.match + it.after },
      it.before.slice(-20), el('b', {}, it.match), it.after.slice(0, 30));
    const addrCell = el('td', { class: 'mono addr', title: 'Apri nel visore memoria' }, it.address);
    addrCell.addEventListener('click', () => openInMemory(it.address));
    body.append(el('tr', {}, addrCell, el('td', { class: 'muted' }, it.encoding), ctx,
      el('td', { class: 'actions' },
        actionBtn('Memoria', () => openInMemory(it.address)),
        actionBtn('Puntatori', () => startPointerChain(it.address), 'Chi punta a questa stringa?'),
        actionBtn('Chi lo usa?', () => nameUsers(it), 'Segue stringa → record → oggetto nome → oggetti che usano il nome'))));
  }
}
async function nameUsers(it) {
  $('nu-card').classList.remove('hidden');
  $('nu-title').textContent = `Chi usa "${it.match}" (${it.address})?`;
  $('nu-info').textContent = 'Ricerca in corso (qualche secondo)…';
  const body = $('nu-body');
  body.innerHTML = '';
  $('nu-card').scrollIntoView({ behavior: 'smooth' });
  const r = await call('search/name-users', { address: it.address });
  if (!r) { $('nu-info').textContent = "Non è un nome del database (prova con un'altra riga)."; return; }
  $('nu-info').textContent = `${r.items.length} oggetti usano questo nome (record: ${r.records}, oggetti nome: ${r.name_objects}).`;
  for (const u of r.items) {
    const objCell = el('td', { class: 'mono addr', title: 'Apri nel visore memoria' }, u.object || '?');
    if (u.object) objCell.addEventListener('click', () => openInMemory(u.object));
    body.append(el('tr', {}, objCell,
      el('td', { class: 'mono' }, u.vtable || ''),
      el('td', { class: 'mono' }, u.field !== null ? '+0x' + u.field.toString(16).toUpperCase() : ''),
      el('td', { class: 'mono muted' }, u.name_object),
      el('td', { class: 'actions' },
        actionBtn('Memoria', () => openInMemory(u.object || u.pointer_at)),
        actionBtn('Puntatori', () => startPointerChain(u.object || u.pointer_at), 'Chi punta a questo oggetto?'))));
  }
}

$('btn-str').addEventListener('click', searchStrings);
$('str-text').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') searchStrings(); });

// Catena: [indirizzo di partenza, puntatore 1, puntatore 2, ...].
// Ogni passo è l'indirizzo in cui sta il puntatore al passo precedente.
let chain = [];

function renderChain() {
  const box = $('ptr-chain');
  box.innerHTML = '';
  box.classList.toggle('hidden', chain.length < 2);
  chain.forEach((step, i) => {
    if (i > 0) box.append(el('span', { class: 'arrow' }, step.offset ? `← (+0x${step.offset.toString(16).toUpperCase()})` : '←'));
    const b = el('span', { class: 'step', title: 'Riparti da qui' }, step.module || step.address);
    b.addEventListener('click', () => { chain = chain.slice(0, i + 1); searchPointers(step.address); });
    box.append(b);
  });
}

function startPointerChain(address) {
  chain = [{ address }];
  document.querySelector('.tab[data-tab="search"]').click();
  searchPointers(address);
}

async function searchPointers(address) {
  address = (address || $('ptr-addr').value).trim();
  if (!/^(0x)?[0-9a-f]+$/i.test(address)) return toast('Indirizzo non valido', true);
  if (!chain.length || chain[chain.length - 1].address.toLowerCase() !== address.toLowerCase()) chain = [{ address }];
  $('ptr-addr').value = address;
  renderChain();
  const body = $('ptr-body');
  body.innerHTML = '';
  $('btn-ptr').disabled = true;
  $('ptr-info').textContent = 'Ricerca in corso…';
  const r = await call('search/pointers', { address, max_offset: Number($('ptr-off').value) });
  $('btn-ptr').disabled = false;
  if (!r) { $('ptr-info').textContent = 'Ricerca non riuscita.'; return; }
  $('ptr-info').textContent = r.count === 0
    ? 'Nessun puntatore trovato. Prova con un offset max più grande.'
    : `${r.count.toLocaleString('it-IT')} puntatori, di cui ${r.static} statici${r.truncated ? ' (troncati)' : ''}.`;
  for (const it of r.items) {
    const addrCell = el('td', { class: 'mono addr', title: "Apri nel visore memoria (l'oggetto che contiene il puntatore)" }, it.address);
    addrCell.addEventListener('click', () => openInMemory(it.address));
    const valCell = el('td', { class: 'mono addr', title: "Apri l'oggetto puntato" }, it.value);
    valCell.addEventListener('click', () => openInMemory(it.value));
    body.append(el('tr', {}, addrCell,
      el('td', { class: 'mono static' }, it.module || ''),
      valCell,
      el('td', { class: 'mono' }, '+0x' + it.offset.toString(16).toUpperCase()),
      el('td', { class: 'actions' },
        actionBtn('Puntatori', () => {
          chain.push({ address: it.address, offset: it.offset, module: it.module });
          searchPointers(it.address);
        }, 'Chi punta a questo puntatore? (risale la catena)'),
        actionBtn('+ Salva', () => {
          addEntry({ label: it.module ? `Puntatore ${it.module}` : 'Puntatore', address: it.address, type: 'int32' });
          toast('Aggiunto agli indirizzi salvati');
        }))));
  }
}
$('btn-ptr').addEventListener('click', () => { chain = []; searchPointers(); });
$('ptr-addr').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { chain = []; searchPointers(); } });
$('btn-mem-ptr').addEventListener('click', () => {
  const a = $('m-addr').value.trim();
  if (a) startPointerChain(a);
});

// ------------------------------------------------------- valori vicini
async function searchGroup() {
  const ranges = [];
  for (const line of $('grp-lines').value.split(/\r?\n/)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 3) continue;
    const max = Number(parseNum(parts.pop(), 'int32'));
    const min = Number(parseNum(parts.pop(), 'int32'));
    if (Number.isNaN(min) || Number.isNaN(max)) return toast(`Riga non valida: ${line}`, true);
    ranges.push({ name: parts.join(' '), min, max });
  }
  if (ranges.length < 2) return toast('Servono almeno 2 righe "nome minimo massimo"', true);
  const body = $('grp-body');
  body.innerHTML = '';
  $('btn-grp').disabled = true;
  $('grp-info').textContent = 'Ricerca in corso…';
  const r = await call('search/group', { ranges, distance: Number($('grp-dist').value) });
  $('btn-grp').disabled = false;
  if (!r) { $('grp-info').textContent = 'Ricerca non riuscita.'; return; }
  $('grp-info').textContent = (r.count === 0 ? 'Nessun gruppo trovato.' : `${r.count} gruppi trovati, i più compatti per primi.`) +
    (r.dropped ? ` (Con tutti i valori non c'era nulla: ho escluso "${r.dropped}", forse il gioco lo calcola.)` : '');
  for (const g of r.items) {
    const minOff = Math.min(...g.members.map((m) => m.offset));
    const desc = g.members
      .map((m) => `${m.name} +0x${(m.offset - minOff).toString(16).toUpperCase()} = ${m.value.toLocaleString('it-IT')}`)
      .join('   ·   ');
    const startCell = el('td', { class: 'mono addr', title: 'Apri nel visore memoria' }, g.start);
    startCell.addEventListener('click', () => openInMemory(g.start));
    body.append(el('tr', {}, startCell, el('td', { class: 'mono' }, `${g.span} byte`),
      el('td', { class: 'mono', title: desc }, desc),
      el('td', { class: 'actions' },
        actionBtn('Memoria', () => openInMemory(g.start)),
        actionBtn('Puntatori', () => startPointerChain(g.start), 'Chi punta a questa struttura?'))));
  }
}
$('btn-grp').addEventListener('click', searchGroup);

// ------------------------------------------- valori collegati a un oggetto
async function searchValues() {
  const address = $('val-addr').value.trim();
  const anywhere = address === '';
  if (!anywhere && !/^(0x)?[0-9a-f]+$/i.test(address)) return toast('Indirizzo non valido', true);
  const body = $('val-body');
  body.innerHTML = '';
  $('btn-val').disabled = true;
  $('val-info').textContent = anywhere
    ? 'Ricerca in TUTTA la memoria, formato 1-20 (circa 20-40 secondi)…'
    : 'Ricerca in corso (può richiedere qualche secondo)…';
  const r = await call('search/values', { address, values: $('val-list').value, depth: Number($('val-depth').value) });
  $('btn-val').disabled = false;
  if (!r) { $('val-info').textContent = 'Ricerca non riuscita.'; return; }
  $('val-info').textContent = anywhere
    ? `Esaminati ${r.scanned_mb.toLocaleString('it-IT')} MB: ${r.count} blocchi con almeno l'85% dei valori.`
    : `Esaminati ${r.visited.toLocaleString('it-IT')} blocchi di memoria, verificati su ${r.peers} oggetti dello stesso tipo. I migliori:`;
  for (const it of r.items) {
    const path = !it.path ? '(tutta la memoria)' : it.path.length
      ? it.path.map((s) => `[+0x${s.offset.toString(16).toUpperCase()}] → ${s.pointer}`).join('  ')
      : '(dentro l\'oggetto stesso)';
    const winCell = el('td', { class: 'mono addr', title: 'Apri nel visore memoria' }, it.window);
    winCell.addEventListener('click', () => openInMemory(it.window));
    const good = it.score >= it.total * 0.9 && (it.confirm === null || it.confirm >= 60);
    body.append(el('tr', {},
      el('td', { class: good ? 'static' : '' }, `${it.score} / ${it.total}`),
      it.confirm === null
        ? el('td', { class: 'muted' }, '–')
        : el('td', { class: it.confirm >= 60 ? 'static' : 'muted', title: `verificato su ${it.peers} oggetti` }, `${it.confirm}%`),
      el('td', { class: 'muted' }, it.scale === 'x1' ? '1-20' : '1-100'),
      winCell,
      el('td', { class: 'mono', title: path }, path),
      el('td', { class: 'actions' },
        actionBtn('Memoria', () => openInMemory(it.window)),
        actionBtn('Puntatori', () => startPointerChain(it.window), 'Chi punta a questo blocco?'))));
  }
}
$('btn-val').addEventListener('click', searchValues);
$('val-list').addEventListener('keydown', (ev) => { if (ev.key === 'Enter') searchValues(); });


// --------------------------------------------------------- avvio / ciclo
function toolsInit(scanInfo) {
  renderEntries();
  // al riavvio gli indirizzi bloccati non lo sono più lato backend
  entries.forEach((e) => (e.frozen = false));
  saveEntries();
  renderEntries();
  setScanState(scanInfo || null);
}

function toolsTick() {
  refreshEntries();
  if ($('m-auto').checked && document.querySelector('#tab-memory.active')) dump(true);
}
