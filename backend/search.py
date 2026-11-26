"""Ricerca di stringhe e di puntatori nella memoria del processo.

Come lo scanner, funziona con qualunque oggetto che offra regions(),
read(addr, size) e modules(): così si può testare anche senza il gioco.
"""
import numpy as np

# codifica -> nome leggibile. FM2007 usa quasi certamente UTF-16 per i nomi,
# ma proviamo anche le codifiche a 8 bit.
ENCODINGS = {
    "utf-16-le": "UTF-16",
    "cp1252": "ANSI",
    "utf-8": "UTF-8",
}

MAX_RESULTS = 2000
CONTEXT = 48  # byte di anteprima prima e dopo una stringa trovata


class SearchError(Exception):
    pass


# --------------------------------------------------------------- moduli
class ModuleMap:
    """Traduce un indirizzo in 'modulo+offset' se cade dentro un modulo."""

    def __init__(self, modules):
        self.mods = sorted(modules, key=lambda m: m[1])

    def find(self, addr):
        for name, base, size in self.mods:
            if base <= addr < base + size:
                return name, addr - base
        return None

    def label(self, addr):
        hit = self.find(addr)
        return f"{hit[0]}+0x{hit[1]:X}" if hit else None


# -------------------------------------------------------------- stringhe
def _fold_table():
    """Tabella che porta in minuscolo A-Z e le lettere accentate Latin-1 (À-Þ).

    Vale anche per UTF-16: i caratteri latini hanno il byte basso uguale al
    codice Latin-1. Applicata sia al buffer sia alla parola cercata, rende la
    ricerca insensibile a maiuscole/minuscole a velocità di C.
    """
    t = bytearray(range(256))
    for b in list(range(0x41, 0x5B)) + [b for b in range(0xC0, 0xDF) if b != 0xD7]:
        t[b] = b + 0x20
    return bytes(t)


FOLD = _fold_table()


def _needle(text, enc, case_sensitive):
    try:
        data = text.encode(enc)
    except UnicodeEncodeError:
        return None  # carattere non rappresentabile in questa codifica
    return data if case_sensitive else data.translate(FOLD)


def _preview(data, enc):
    """Decodifica un pezzo di memoria in modo leggibile (caratteri strani -> ·)."""
    if enc == "utf-16-le":
        data = data[: len(data) // 2 * 2]
    text = data.decode(enc, errors="replace")
    return "".join(c if c.isprintable() and c != "�" else "·" for c in text)


def find_strings(proc, text, encodings=None, case_sensitive=False, limit=MAX_RESULTS):
    text = (text or "").strip()
    if len(text) < 2:
        raise SearchError("Scrivi almeno 2 caratteri")
    encodings = [e for e in (encodings or list(ENCODINGS)) if e in ENCODINGS]
    if not encodings:
        raise SearchError("Scegli almeno una codifica")
    needles = [(enc, _needle(text, enc, case_sensitive)) for enc in encodings]
    needles = [(enc, n) for enc, n in needles if n]
    mods = ModuleMap(proc.modules())

    out = []
    seen = set()  # ANSI e UTF-8 coincidono sui caratteri semplici: niente doppioni
    truncated = False
    for base, size in proc.regions():
        buf = proc.read(base, size)
        if buf is None:
            continue
        hay = buf if case_sensitive else buf.translate(FOLD)
        for enc, needle in needles:
            step = 2 if enc == "utf-16-le" else 1
            s = hay.find(needle)
            while s != -1:
                e = s + len(needle)
                nxt = hay.find(needle, s + 1)
                if step == 2 and (base + s) % 2:
                    s = nxt
                    continue  # le stringhe UTF-16 stanno su indirizzi pari
                if (base + s, len(needle)) in seen:
                    s = nxt
                    continue
                seen.add((base + s, len(needle)))
                if len(out) >= limit:
                    truncated = True
                    break
                ctx_s = max(0, s - CONTEXT) // step * step
                ctx_e = min(len(buf), e + CONTEXT)
                addr = base + s
                out.append({
                    "address": f"0x{addr:08X}",
                    "encoding": ENCODINGS[enc],
                    "enc": enc,
                    "before": _preview(buf[ctx_s:s], enc),
                    "match": _preview(buf[s:e], enc),
                    "after": _preview(buf[e:ctx_e], enc),
                    "module": mods.label(addr),
                })
                s = nxt
            if truncated:
                break
        if truncated:
            break
    return {"count": len(out), "truncated": truncated, "items": out}


# ------------------------------------------------------------- puntatori
def find_pointers(proc, target, max_offset=0, limit=MAX_RESULTS):
    """Cerca valori a 32 bit (allineati a 4) che puntano a `target`
    o fino a `max_offset` byte prima di esso.

    Un risultato con offset 0x10 vuol dire: in quell'indirizzo c'è un puntatore
    a un oggetto che inizia 0x10 byte prima del target (il target è un suo campo).
    """
    if target <= 0 or target > 0xFFFFFFFF:
        raise SearchError("Indirizzo non valido (FM2007 è un processo a 32 bit)")
    max_offset = max(0, min(int(max_offset), 0x10000))
    lo, hi = max(0, target - max_offset), target
    mods = ModuleMap(proc.modules())
    dt = np.dtype("<u4")

    out = []
    truncated = False
    for base, size in proc.regions():
        buf = proc.read(base, size)
        if buf is None:
            continue
        # il buffer parte da base (allineata a pagina), quindi offset 0 = allineato a 4
        arr = np.frombuffer(buf, dtype=dt, count=len(buf) // 4)
        idx = np.nonzero((arr >= lo) & (arr <= hi))[0]
        for i in idx:
            if len(out) >= limit:
                truncated = True
                break
            addr = base + int(i) * 4
            value = int(arr[i])
            out.append({
                "address": f"0x{addr:08X}",
                "value": f"0x{value:08X}",
                "offset": target - value,
                "module": mods.label(addr),
            })
        if truncated:
            break
    # prima gli indirizzi statici (dentro fm.exe): sono la base delle catene stabili,
    # poi per offset crescente
    out.sort(key=lambda r: (r["module"] is None, r["offset"]))
    return {"count": len(out), "truncated": truncated, "items": out,
            "static": sum(1 for r in out if r["module"])}


# ------------------------------------------- valori vicino a un oggetto
# Scale con cui il gioco potrebbe salvare un valore mostrato come 1-20:
#   x1 -> salvato così com'è (15 -> 15)
#   x5 -> salvato su 1-100 (15 -> 73..77), con tolleranza di arrotondamento
SCALES = {"x1": (1, 0), "x5": (5, 2)}


class _RegionIndex:
    """Dice velocemente se un valore a 32 bit è un indirizzo leggibile."""

    def __init__(self, regions):
        rs = sorted(regions)
        self.starts = np.array([b for b, _ in rs], dtype=np.int64)
        self.ends = np.array([b + s for b, s in rs], dtype=np.int64)

    def valid(self, values):
        v = values.astype(np.int64)
        i = np.searchsorted(self.starts, v, side="right") - 1
        ok = i >= 0
        ok[ok] &= v[ok] < self.ends[i[ok]]
        return ok


def _read_block(proc, addr, size):
    while size >= 0x40:
        data = proc.read(addr, size)
        if data is not None:
            return data
        size //= 2
    return None


def _score(block, needs, scale, window):
    """Miglior finestra di `window` byte: quanti dei valori cercati contiene."""
    mult, tol = SCALES[scale]
    b = np.frombuffer(block, dtype=np.uint8).astype(np.int16)
    w = min(window, len(b))
    acc = np.zeros(len(b) - w + 1, dtype=np.int32)
    for v, c in needs.items():
        m = (np.abs(b - v * mult) <= tol).astype(np.int32)
        cs = np.concatenate(([0], np.cumsum(m)))
        acc += np.minimum(cs[w:] - cs[:-w], c)
    i = int(np.argmax(acc))
    return int(acc[i]), i


def _in_range_frac(data, scale):
    """Quota di byte che hanno l'aspetto di un attributo (1-20 o 1-100)."""
    b = np.frombuffer(data, dtype=np.uint8)
    hi = 20 if scale == "x1" else 100
    return float(np.mean((b >= 1) & (b <= hi))) if len(b) else 0.0


def _follow(cache, addr, path):
    """Segue i passi [(offset, _)] partendo da addr. None se un puntatore è nullo."""
    for off, _ in path:
        addr = cache.u32(addr + off)
        if not addr:
            return None
    return addr


def find_values_near(proc, start, values, depth=2, block=0x400, window=96,
                     max_blocks=8000, peers=300):
    """Parte dall'oggetto in `start`, segue i suoi puntatori fino a `depth` livelli
    e cerca il blocco che contiene il maggior numero dei `values` (es. attributi).

    Poi verifica ogni candidato su altri oggetti dello stesso tipo (stessa vtable):
    gli attributi veri stanno allo stesso percorso anche negli altri giocatori,
    una tabella che contiene i valori per caso no.
    """
    from people import PageCache, find_dword  # import qui per evitare cicli

    vals = [int(v) for v in values if 1 <= int(v) <= 20]
    if len(vals) < 5:
        raise SearchError("Inserisci almeno 5 valori da 1 a 20")
    needs = {}
    for v in vals:
        needs[v] = needs.get(v, 0) + 1
    total = len(vals)
    depth = max(0, min(int(depth), 3))
    index = _RegionIndex(proc.regions())

    seen = {start}
    queue = [(start, [])]   # (indirizzo, percorso)
    results = []
    visited = 0
    while queue and visited < max_blocks:
        addr, path = queue.pop(0)
        data = _read_block(proc, addr, block)
        if data is None:
            continue
        visited += 1
        for scale in SCALES:
            score, off = _score(data, needs, scale, window)
            results.append({"address": addr, "path": path, "scale": scale,
                            "score": score, "offset": off})
        if len(path) >= depth:
            continue
        dw = np.frombuffer(data, dtype="<u4", count=len(data) // 4)
        for i in np.nonzero(index.valid(dw))[0]:
            p = int(dw[i])
            if p in seen or (0 <= p - addr < len(data)):
                continue  # già visto o punta dentro lo stesso blocco
            seen.add(p)
            queue.append((p, path + [(int(i) * 4, p)]))

    results.sort(key=lambda r: -r["score"])
    cands, used = [], set()
    for r in results:
        key = (r["address"] + r["offset"]) // 16
        if key in used:
            continue
        used.add(key)
        cands.append(r)
        if len(cands) >= 60:
            break

    # --- verifica sugli altri oggetti con la stessa vtable -----------------
    cache = PageCache(proc)
    vtable = cache.u32(start)
    others = [a for a in find_dword(proc, vtable, limit=peers + 1) if a != start][:peers] if vtable else []
    for c in cands:
        w = min(window, block - c["offset"])
        mine = cache.read(c["address"] + c["offset"], w)
        my_frac = _in_range_frac(mine, c["scale"])
        ok = tried = 0
        for peer in others:
            base = _follow(cache, peer, c["path"])
            if base is None:
                continue
            tried += 1
            try:
                theirs = cache.read(base + c["offset"], w)
            except Exception:
                continue
            # stesso aspetto (valori da attributo) ma contenuto diverso
            if theirs != mine and _in_range_frac(theirs, c["scale"]) >= 0.85 * my_frac:
                ok += 1
        c["confirm"] = round(100 * ok / tried) if tried else 0
        c["peers"] = tried

    # punteggio combinato: un blocco non confermato dagli altri giocatori vale poco
    cands = [c for c in cands if c["score"] >= total * 0.4]
    cands.sort(key=lambda c: -c["score"] * (0.3 + 0.7 * c["confirm"] / 100))
    items = [{
        "address": f"0x{c['address']:08X}",
        "window": f"0x{c['address'] + c['offset']:08X}",
        "window_offset": c["offset"],
        "scale": c["scale"],
        "score": c["score"],
        "total": total,
        "confirm": c["confirm"],
        "peers": c["peers"],
        "path": [{"offset": o, "pointer": f"0x{p:08X}"} for o, p in c["path"]],
    } for c in cands[:20]]
    return {"visited": visited, "peers": len(others), "items": items}


# --------------------------------------- valori in tutta la memoria
# Solo il formato 1-20: con 1-100 ogni attributo corrisponde a 5-7 byte diversi
# e quasi ogni zona di memoria "sembra" contenerli. Quel formato si verifica
# confrontando più giocatori, non con una ricerca su tutta la memoria.
RANGES = {
    "x1": lambda d: (d, d),
}
MAX_CHECKS = 3000  # controlli precisi al massimo per zona da 16 MB
CHUNK = 16 * 1024 * 1024


def _exact_score(b, needs, scale, window):
    """Come _score ma con gli intervalli di RANGES; b è un array uint8."""
    w = min(window, len(b))
    acc = np.zeros(len(b) - w + 1, dtype=np.int32)
    for d, c in needs.items():
        lo, hi = RANGES[scale](d)
        m = ((b >= lo) & (b <= hi)).astype(np.int32)
        cs = np.concatenate(([0], np.cumsum(m)))
        acc += np.minimum(cs[w:] - cs[:-w], c)
    i = int(np.argmax(acc))
    return int(acc[i]), i


def find_values_anywhere(proc, values, window=64, min_ratio=0.85, top=20):
    """Cerca in tutta la memoria scrivibile un blocco di `window` byte che
    contiene (in qualsiasi ordine) almeno min_ratio dei valori indicati."""
    vals = [int(v) for v in values if 1 <= int(v) <= 20]
    if len(vals) < 5:
        raise SearchError("Inserisci almeno 5 valori da 1 a 20")
    needs = {}
    for v in vals:
        needs[v] = needs.get(v, 0) + 1
    total = len(vals)
    threshold = int(np.ceil(total * min_ratio))
    W = window

    found = []
    scanned = 0
    for base, size in proc.regions():
        data = proc.read(base, size)
        if data is None:
            continue
        scanned += size
        whole = np.frombuffer(data, dtype=np.uint8)
        for c0 in range(0, len(whole), CHUNK):
            # sovrapposizione di 2W per non perdere blocchi a cavallo
            s0 = max(0, c0 - 2 * W)
            b = whole[s0:c0 + CHUNK]
            for scale in RANGES:
                pos = {}
                for d in needs:
                    lo, hi = RANGES[scale](d)
                    m = (b == lo) if lo == hi else ((b >= lo) & (b <= hi))
                    pos[d] = np.flatnonzero(m)
                # ancore: le posizioni del valore più raro in questa zona
                d0 = min(needs, key=lambda d: len(pos[d]))
                anchors = pos[d0]
                if len(anchors) == 0:
                    continue
                # filtro veloce su una finestra larga 2W attorno a ogni ancora
                acc = np.zeros(len(anchors), dtype=np.int32)
                for d, c in needs.items():
                    p = pos[d]
                    cnt = np.searchsorted(p, anchors + W) - np.searchsorted(p, anchors - W)
                    acc += np.minimum(cnt, c).astype(np.int32)
                sel = np.flatnonzero(acc >= threshold)
                if len(sel) > MAX_CHECKS:  # zona densa: solo le ancore migliori
                    sel = sel[np.argsort(-acc[sel], kind="stable")[:MAX_CHECKS]]
                    sel.sort()
                keep = anchors[sel]
                # controllo preciso sulle poche ancore rimaste
                last = -10 * W
                for a in keep:
                    a = int(a)
                    if a - last < W // 2:
                        continue
                    lo_i = max(0, a - W)
                    score, off = _exact_score(b[lo_i:a + W], needs, scale, W)
                    if score >= threshold:
                        last = a
                        found.append({"addr": base + s0 + lo_i + off, "scale": scale, "score": score})

    # togli i doppioni (stesso blocco trovato da ancore vicine)
    found.sort(key=lambda r: -r["score"])
    items, used = [], set()
    for r in found:
        key = (r["addr"] // 64, r["scale"])
        if key in used:
            continue
        used.add(key)
        items.append({
            "address": f"0x{r['addr']:08X}",
            "window": f"0x{r['addr']:08X}",
            "scale": r["scale"],
            "score": r["score"],
            "total": total,
            "confirm": None,
            "peers": 0,
            "path": None,
        })
        if len(items) >= top:
            break
    return {"visited": 0, "scanned_mb": round(scanned / 1048576), "peers": 0,
            "count": len(found), "items": items}


# ------------------------------------------- gruppi di valori vicini (int32)
def find_value_group(proc, ranges, distance=0x200, limit=50, retry=True):
    """Cerca punti della memoria dove TUTTI gli intervalli [(nome, min, max)]
    compaiono come int32 allineati entro `distance` byte da un'ancora.

    L'ancora è l'intervallo con meno occorrenze; per ogni ancora valida si
    restituisce dove sta ciascun valore, con l'offset rispetto all'ancora.
    """
    if len(ranges) < 2:
        raise SearchError("Servono almeno 2 valori")
    distance = max(16, min(int(distance), 0x2000))
    rs = [(str(n), int(min(a, b)), int(max(a, b))) for n, a, b in ranges]

    groups = []
    truncated = False
    for base, size in proc.regions():
        data = proc.read(base, size)
        if data is None:
            continue
        arr = np.frombuffer(data, dtype="<i4", count=len(data) // 4)
        pos = [np.flatnonzero((arr >= lo) & (arr <= hi)) for _, lo, hi in rs]
        if any(len(p) == 0 for p in pos):
            continue
        k = int(np.argmin([len(p) for p in pos]))   # ancora = il più raro
        step = distance // 4
        anchors = pos[k]
        ok = np.ones(len(anchors), dtype=bool)
        for p in pos:
            ok &= (np.searchsorted(p, anchors + step, side="right") - np.searchsorted(p, anchors - step)) > 0
        for a in anchors[ok]:
            a = int(a)
            members = []
            for (name, _, _), p in zip(rs, pos):
                lo_i = np.searchsorted(p, a - step)
                hi_i = np.searchsorted(p, a + step, side="right")
                near = p[lo_i:hi_i]
                best = int(near[np.argmin(np.abs(near - a))])  # il più vicino all'ancora
                members.append({"name": name, "address": f"0x{base + best * 4:08X}",
                                "offset": (best - a) * 4, "value": int(arr[best])})
            span = max(m["offset"] for m in members) - min(m["offset"] for m in members)
            groups.append({"anchor": f"0x{base + a * 4:08X}", "span": span, "members": members,
                           "start": f"0x{base + a * 4 + min(m['offset'] for m in members):08X}"})
            if len(groups) >= limit * 4:
                truncated = True
                break
        if truncated:
            break
    groups.sort(key=lambda g: g["span"])  # prima i gruppi più compatti
    result = {"count": len(groups), "truncated": truncated, "items": groups[:limit], "dropped": None}
    if not groups and len(rs) > 2 and retry:
        # forse uno dei valori è calcolato dal gioco e non è in memoria: lo tolgo
        for i in range(len(rs)):
            sub = find_value_group(proc, rs[:i] + rs[i + 1:], distance, limit, retry=False)
            if sub["count"]:
                sub["dropped"] = rs[i][0]
                return sub
    return result


# ------------------------------------- chi usa un nome (stringa -> oggetti)
# Schema trovato con Del Piero (vedi MAPPA.md):
#   stringa UTF-16  <- record lista nomi (+0x08)  <- oggetto nome (+0x24)  <- proprietario
NAME_RECORD_STRING = 0x08
NAME_OBJ_RECORD = 0x24
NAME_OBJ_VTABLE = 0x012C523C  # PERSON_NAME (FM08: 0x0150FF24)


def _pointers_to(proc, targets):
    """Un solo passaggio su tutta la memoria: {target: [indirizzi che lo contengono]}."""
    targets = sorted(set(int(t) for t in targets))
    out = {t: [] for t in targets}
    if not targets:
        return out
    tarr = np.array(targets, dtype=np.uint32)
    for base, size in proc.regions():
        data = proc.read(base, size)
        if data is None:
            continue
        arr = np.frombuffer(data, dtype="<u4", count=len(data) // 4)
        for i in np.nonzero(np.isin(arr, tarr))[0]:
            out[int(arr[i])].append(base + int(i) * 4)
    return out


def _guess_object(proc, ptr_loc, mods, back=0x600):
    """Cerca all'indietro la vtable più vicina (un indirizzo dentro fm.exe):
    di solito segna l'inizio dell'oggetto (o di un suo sotto-oggetto)."""
    exe = next(((b, s) for n, b, s in mods.mods if n.lower() == "fm.exe"), None)
    start = max(0, ptr_loc - back)
    data = proc.read(start, ptr_loc - start)
    if data is None or exe is None:
        return None, None
    dw = np.frombuffer(data, dtype="<u4", count=len(data) // 4)
    hits = np.nonzero((dw >= exe[0]) & (dw < exe[0] + exe[1]))[0]
    if not len(hits):
        return None, None
    i = int(hits[-1])
    return start + i * 4, int(dw[i])


def find_name_users(proc, string_addr):
    mods = ModuleMap(proc.modules())
    # 1) record che puntano alla stringa
    recs = [loc - NAME_RECORD_STRING for loc in _pointers_to(proc, [string_addr])[string_addr]]
    if not recs:
        raise SearchError("Nessun record punta a questa stringa: prova con un'altra copia del nome")
    # 2) oggetti nome che puntano ai record (riconosciuti dalla loro vtable)
    name_objs = []
    for rec, locs in _pointers_to(proc, recs).items():
        for loc in locs:
            obj = loc - NAME_OBJ_RECORD
            raw = proc.read(obj, 4)
            if raw and int.from_bytes(raw, "little") == NAME_OBJ_VTABLE:
                name_objs.append(obj)
    if not name_objs:
        raise SearchError("Trovato il record ma nessun oggetto nome: questa stringa non è un nome del database")
    # 3) proprietari: chi punta agli oggetti nome
    users = []
    for obj, locs in _pointers_to(proc, name_objs).items():
        for loc in locs:
            start, vt = _guess_object(proc, loc, mods)
            users.append({
                "name_object": f"0x{obj:08X}",
                "pointer_at": f"0x{loc:08X}",
                "object": f"0x{start:08X}" if start else None,
                "field": loc - start if start else None,
                "vtable": f"0x{vt:08X}" if vt else None,
            })
    return {"records": len(recs), "name_objects": len(name_objs), "items": users}
