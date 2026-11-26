"""Trova campi sconosciuti (CA, PA…) con la statistica su migliaia di giocatori.

Idea: la CA è calcolata dagli attributi, quindi la posizione in memoria il cui
valore va più d'accordo con la media degli attributi è quasi certamente la CA.
La PA è un valore vicino sempre >= CA (o tra -10 e -1 per le PA "a intervallo"),
con la differenza più grande nei giocatori giovani.
"""
import numpy as np

from people import OFF_ATTR_PTR, OFF_BIRTH, PERSON_VTABLE, PageCache, find_dword
from player import ATTR_BLOCK_VTABLE, ATTR_FIRST, ATTR_LAST, ATTRIBUTES, OBJ

# zone da esaminare: (nome, come arrivarci, inizio, fine) relativi alla base
#   "persona": base = indirizzo della persona; l'oggetto completo va da OBJ (-0xD4) a +0x290
#   "attributi": base = blocco attributi (0x70 byte)
ZONES = [
    ("persona", OBJ, 0x290),
    ("attributi", 0x00, 0x70),
]

GK_GROUP = "Portiere"
OUTFIELD = [off for g, _, off in ATTRIBUTES if g in ("Tecniche", "Mentali", "Fisiche")]
GOALKEEPING = [off for g, _, off in ATTRIBUTES if g == GK_GROUP]


class AnalysisError(Exception):
    pass


def _corr(a, b):
    a = a - a.mean()
    b = b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d else 0.0


def _sample(proc, limit, reference=None):
    """Legge `limit` giocatori: zone di memoria grezze, media attributi, anno di nascita."""
    cache = PageCache(proc)
    people = find_dword(proc, PERSON_VTABLE)
    if not people:
        raise AnalysisError("Nessuna persona trovata: il gioco è caricato?")
    step = max(1, len(people) // (limit * 3))  # campione sparso su tutto il database
    rows = {name: [] for name, _, _ in ZONES}
    skill, year, addrs = [], [], []
    chosen = people[::step]
    if reference in people:
        chosen = [reference] + [p for p in chosen if p != reference]  # sempre nel campione
    for person in chosen:
        block = cache.u32(person + OFF_ATTR_PTR)
        if not block or cache.u32(block) != ATTR_BLOCK_VTABLE:
            continue  # non è un giocatore
        attrs = np.frombuffer(cache.read(block, 0x70), dtype=np.uint8)
        gk = attrs[GOALKEEPING].mean() > attrs[OUTFIELD].mean()
        # per un portiere contano gli attributi da portiere, per gli altri quelli di movimento
        main = attrs[GOALKEEPING] if gk else attrs[OUTFIELD]
        y = int.from_bytes(cache.read(person + OFF_BIRTH + 2, 2), "little")
        rows["persona"].append(cache.read(person + OBJ, 0x290 - OBJ))
        rows["attributi"].append(cache.read(block, 0x70))
        skill.append(float(main.mean()))
        year.append(y if 1900 < y < 2100 else 0)
        addrs.append(person)
        if len(addrs) >= limit:
            break
    if len(addrs) < 200:
        raise AnalysisError(f"Troppo pochi giocatori nel campione ({len(addrs)})")
    return rows, np.array(skill), np.array(year), addrs


def _candidates(raw_rows, start):
    """Tutte le interpretazioni (byte, int16) di ogni posizione nelle zone."""
    buf = np.frombuffer(b"".join(raw_rows), dtype=np.uint8).reshape(len(raw_rows), -1)
    out = []
    n = buf.shape[1]
    for off in range(n):
        out.append((start + off, "byte", buf[:, off].astype(np.int32)))
        if off % 2 == 0 and off + 1 < n:
            v = (buf[:, off].astype(np.int32) | (buf[:, off + 1].astype(np.int32) << 8))
            v = np.where(v >= 0x8000, v - 0x10000, v)  # int16 con segno (PA negative)
            out.append((start + off, "int16", v))
    return out


def find_ca_pa(proc, reference=None, limit=3000):
    rows, skill, year, addrs = _sample(proc, limit, reference)
    young = year >= (year[year > 0].max() - 3) if (year > 0).any() else np.zeros(len(year), bool)
    ref_i = addrs.index(reference) if reference in addrs else None

    ca_list = []
    cand_by_zone = {}
    for zone, start, _ in ZONES:
        cands = _candidates(rows[zone], start)
        cand_by_zone[zone] = cands
        for off, typ, v in cands:
            if zone == "attributi" and ATTR_FIRST <= off <= ATTR_LAST + 1:
                continue  # gli attributi stessi: correlano per forza
            ok = (v >= 1) & (v <= 200)
            if ok.mean() < 0.97 or v.std() < 5:
                continue
            ca_list.append({"zone": zone, "offset": off, "type": typ,
                            "corr": _corr(v.astype(float), skill), "v": v})
    if not ca_list:
        raise AnalysisError("Nessun candidato per la CA")
    ca_list.sort(key=lambda c: -c["corr"])

    # PA: per i migliori candidati CA cerco nella stessa zona un valore compatibile
    pa_list = []
    for ca in ca_list[:3]:
        for off, typ, v in cand_by_zone[ca["zone"]]:
            if off == ca["offset"] and typ == ca["type"]:
                continue
            ranged = (v >= -10) & (v <= -1)
            in_range = ((v >= 1) & (v <= 200)) | ranged
            if in_range.mean() < 0.97:
                continue
            ge = ((v >= ca["v"]) & (v > 0)) | ranged
            if ge.mean() < 0.95 or (v == ca["v"]).mean() > 0.9:
                continue
            pos = v > 0
            gap_young = float((v - ca["v"])[pos & young].mean()) if (pos & young).any() else 0.0
            gap_all = float((v - ca["v"])[pos].mean()) if pos.any() else 0.0
            pa_list.append({"zone": ca["zone"], "offset": off, "type": typ, "ca_offset": ca["offset"],
                            "ge": float(ge.mean()), "ranged": float(ranged.mean()),
                            "gap_young": gap_young, "gap_all": gap_all,
                            "corr": _corr(v.astype(float), ca["v"].astype(float)), "v": v})
    # la PA vera: quasi sempre >= CA, correlata alla CA, differenza maggiore nei giovani
    pa_list.sort(key=lambda p: -(p["ge"] + 0.5 * p["corr"] + 0.01 * (p["gap_young"] - p["gap_all"])))
    seen, unique = set(), []
    for p in pa_list:
        key = (p["zone"], p["offset"], p["type"])
        if key not in seen:
            seen.add(key)
            unique.append(p)
    pa_list = unique

    def fmt(c, extra):
        d = {"zone": c["zone"], "offset": c["offset"], "type": c["type"],
             "label": f"{c['zone']} {'+' if c['offset'] >= 0 else '-'}0x{abs(c['offset']):X} ({c['type']})",
             "min": int(c["v"].min()), "max": int(c["v"].max()), "mean": round(float(c["v"].mean()), 1),
             "ref": int(c["v"][ref_i]) if ref_i is not None else None}
        d.update(extra(c))
        return d

    return {
        "players": len(addrs),
        "reference_found": ref_i is not None,
        "ca": [fmt(c, lambda c: {"corr": round(c["corr"], 3)}) for c in ca_list[:10]],
        "pa": [fmt(p, lambda p: {"corr": round(p["corr"], 3), "ge": round(100 * p["ge"], 1),
                                 "ranged": round(100 * p["ranged"], 1),
                                 "gap_young": round(p["gap_young"], 1), "gap_all": round(p["gap_all"], 1),
                                 "ca_offset": p["ca_offset"]}) for p in pa_list[:10]],
    }
