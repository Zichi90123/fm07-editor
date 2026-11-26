'use strict';

const $ = (id) => document.getElementById(id);
// Ogni richiesta al backend (tranne il controllo di stato ogni secondo) accende l'indicatore
// di caricamento in alto: barra animata + "Caricamento…".
let busyCount = 0;
function setBusy(delta) {
  busyCount = Math.max(0, busyCount + delta);
  document.body.classList.toggle('busy', busyCount > 0);
}
async function api(route, body) {
  if (route === 'status') return window.fm.api(route, body);
  setBusy(1);
  try { return await window.fm.api(route, body); } finally { setBusy(-1); }
}
// Mette un riquadro in stato "sta caricando" (velato, con rotellina) finché fn non finisce.
async function withLoading(target, fn) {
  const t = typeof target === 'string' ? $(target) : target;
  t.classList.add('loading');
  try { return await fn(); } finally { t.classList.remove('loading'); }
}

// ---------------------------------------------------------------- utilità
let toastTimer = null;
function toast(msg, isErr = false) {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'toast' + (isErr ? ' err' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), isErr ? 6000 : 2500);
}

async function call(route, body) {
  const res = await api(route, body);
  if (!res.ok) { toast(res.error || 'Errore', true); return null; }
  return res;
}

function fmt(v) {
  if (v === null || v === undefined) return '??';
  if (typeof v === 'number' && !Number.isInteger(v)) return v.toLocaleString('it-IT', { maximumFractionDigits: 3 });
  return typeof v === 'number' ? v.toLocaleString('it-IT') : String(v);
}

// Converte un numero scritto dall'utente in una stringa che il backend capisce.
// Accetta sia il formato italiano (1.000.000 / 0,5) sia quello inglese (0.5).
// Un punto singolo seguito da 3 cifre su un tipo intero è un separatore delle migliaia.
const INT_TYPES = new Set(['byte', 'int16', 'int32', 'int64']);
function parseNum(str, vtype) {
  const v = String(str || '').trim().replace(/[\s']/g, '');
  if (v === '') return '';
  if (v.includes(',')) return v.replace(/\./g, '').replace(',', '.');
  const dots = (v.match(/\./g) || []).length;
  if (dots > 1) return v.replace(/\./g, '');
  if (dots === 1 && INT_TYPES.has(vtype) && /^-?\d{1,3}\.\d{3}$/.test(v)) return v.replace('.', '');
  return v;
}

const hex = (n) => '0x' + n.toString(16).toUpperCase().padStart(8, '0');

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v;
    else if (k === 'dataset') Object.assign(e.dataset, v);
    else e.setAttribute(k, v);
  }
  for (const c of children) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return e;
}
