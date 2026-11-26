"""Server HTTP locale (solo 127.0.0.1) usato dalla GUI Electron.

Avvio: python server.py --port 47810
Stampa "READY <porta>" quando è pronto.
"""
import argparse
import json
import os
import socket
import sys
import struct
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from memory import Process, TYPES
from scanner import Scanner, ScanError
from people import list_people, read_attr_block
from player import PlayerError, heal, list_players, read_attributes, write_attributes, write_extra
from analysis import AnalysisError, find_ca_pa
from tactics import TacticError, list_tactics, read_tactic, role_score, tactics_dir
from clubs import ClubError, currency, human_clubs, list_clubs, read_finances, read_info, write_finances, write_info
from search import (SearchError, find_name_users, find_pointers, find_strings, find_value_group,
                    find_values_anywhere, find_values_near)

lock = threading.RLock()
state = {"proc": None}
scanner = Scanner()
frozen = {}  # (address, type) -> value
MAX_BULK_WRITE = 200  # "Scrivi sui risultati": oltre questo numero è quasi certamente rumore


def _proc():
    proc = state["proc"]
    if proc is None or not proc.is_alive():
        state["proc"] = None
        raise LookupError("Non agganciato a fm.exe: premi 'Aggancia'")
    return proc


def _addr(x):
    if isinstance(x, int):
        return x
    return int(str(x).strip(), 16 if not str(x).strip().lower().startswith("0x") else 0)


# --- handler delle API ------------------------------------------------------
def api_status(_):
    proc = state["proc"]
    alive = proc is not None and proc.is_alive()
    return {
        "attached": alive,
        "pid": proc.pid if alive else None,
        "scan": scanner.info(),
        "frozen": len(frozen),
        "currency": _currency(proc) if alive else None,
    }


def _currency(proc):
    try:
        return currency(proc)
    except Exception:
        return None


def api_attach(body):
    name = body.get("name") or "fm.exe"
    if state["proc"] is not None:
        state["proc"].close()
        state["proc"] = None
    proc = Process.attach(name)
    state["proc"] = proc
    base = proc.module_base()
    regions = proc.regions()
    return {
        "attached": True,
        "pid": proc.pid,
        "module_base": f"0x{base[0]:08X}" if base else None,
        "regions": len(regions),
        "writable_mb": round(sum(s for _, s in regions) / 1048576, 1),
    }


def api_scan_first(body):
    proc = _proc()
    return scanner.first_scan(proc, body.get("type", "int32"), body.get("cond", "exact"),
                              body.get("value"), body.get("value2"), body.get("aligned", True))


def api_scan_next(body):
    proc = _proc()
    return scanner.next_scan(proc, body.get("cond", "exact"), body.get("value"), body.get("value2"))


def api_scan_reset(_):
    scanner.reset()
    return scanner.info()


def api_scan_results(body):
    proc = _proc()
    count = scanner.count()
    limit = int(body.get("limit", 200))
    items = scanner.list_results(proc, limit) if count <= 100000 else []
    return {"count": count, "items": items}


def api_scan_write(body):
    """Scrive lo stesso valore sui risultati dal n. `start` al n. `end` (1 = primo).
    Salva i valori originali per poterli ripristinare."""
    proc = _proc()
    addrs = scanner.addresses()
    if not addrs:
        raise LookupError("Nessun risultato su cui scrivere")
    start = max(1, int(body.get("start") or 1))
    end = min(len(addrs), int(body.get("end") or len(addrs)))
    if start > end:
        raise ValueError("Intervallo non valido")
    if end - start + 1 > MAX_BULK_WRITE:
        raise ValueError(f"Troppi risultati ({end - start + 1}): scrivere su più di {MAX_BULK_WRITE} indirizzi "
                         "insieme può rovinare la partita. Restringi prima la ricerca.")
    vtype = scanner.vtype
    backup = state.setdefault("backup", {})
    written = 0
    for a in addrs[start - 1:end]:
        if (a, vtype) not in backup:
            old = proc.read_value(a, vtype)
            if old is None:
                continue
            backup[(a, vtype)] = old
        if proc.write_value(a, vtype, body["value"]):
            written += 1
    return {"written": written, "from": start, "to": end, "backup": len(backup)}


def api_scan_restore(_):
    proc = _proc()
    backup = state.pop("backup", {})
    restored = sum(1 for (a, t), v in backup.items() if proc.write_value(a, t, v))
    return {"restored": restored}


def api_read_many(body):
    """body.items = [{address, type}]"""
    proc = _proc()
    out = []
    for it in body.get("items", []):
        out.append(proc.read_value(_addr(it["address"]), it.get("type", "int32")))
    return {"values": out}


def api_write(body):
    proc = _proc()
    addr, vtype = _addr(body["address"]), body.get("type", "int32")
    ok = proc.write_value(addr, vtype, body["value"])
    if not ok:
        raise OSError("Scrittura fallita (indirizzo non valido o protetto)")
    key = (addr, vtype)
    if key in frozen:
        frozen[key] = body["value"]
    return {"ok": True, "value": proc.read_value(addr, vtype)}


def api_freeze(body):
    addr, vtype = _addr(body["address"]), body.get("type", "int32")
    key = (addr, vtype)
    if body.get("on"):
        value = body.get("value")
        if value is None:
            value = _proc().read_value(addr, vtype)
        frozen[key] = value
    else:
        frozen.pop(key, None)
    return {"frozen": len(frozen)}


def api_dump(body):
    proc = _proc()
    addr = _addr(body["address"])
    length = max(16, min(int(body.get("length", 256)), 4096))
    start = addr - (addr % 16)
    data = proc.read(start, length)
    if data is None:
        raise OSError("Impossibile leggere la memoria a quell'indirizzo")
    rows = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        ints = [struct.unpack_from("<i", chunk, j)[0] for j in range(0, 16, 4)]
        rows.append({
            "address": f"0x{start + i:08X}",
            "hex": " ".join(f"{b:02X}" for b in chunk),
            "ascii": "".join(chr(b) if 32 <= b < 127 else "." for b in chunk),
            "int32": ints,
        })
    return {"start": f"0x{start:08X}", "rows": rows}


def api_search_string(body):
    proc = _proc()
    return find_strings(proc, body.get("text"), body.get("encodings"),
                        bool(body.get("case_sensitive")))


def api_search_pointers(body):
    proc = _proc()
    return find_pointers(proc, _addr(body["address"]), int(body.get("max_offset", 0)))


def api_search_values(body):
    proc = _proc()
    raw = body.get("values", [])
    if isinstance(raw, str):
        raw = raw.replace(",", " ").split()
    values = [int(v) for v in raw]
    if not str(body.get("address") or "").strip():
        return find_values_anywhere(proc, values)
    return find_values_near(proc, _addr(body["address"]), values,
                            depth=int(body.get("depth", 2)))


def _norm(text):
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def api_people(body):
    """Elenco persone, letto una volta e tenuto in memoria (refresh=true per rileggere)."""
    proc = _proc()
    cache = state.get("people")
    if body.get("refresh") or not cache or cache["pid"] != proc.pid:
        t = time.time()
        people = list_people(proc)
        for p in people:
            p["_key"] = _norm(" ".join([p["first"], p["last"], p["common"]]))
        cache = state["people"] = {"pid": proc.pid, "items": people, "secs": round(time.time() - t, 1)}
    words = _norm(body.get("query", "")).split()
    hits = [p for p in cache["items"] if all(w in p["_key"] for w in words)]
    limit = int(body.get("limit", 300))
    return {
        "total": len(cache["items"]),
        "count": len(hits),
        "secs": cache["secs"],
        "items": [{k: v for k, v in p.items() if k != "_key"} for p in hits[:limit]],
    }


def api_person_attrs(body):
    proc = _proc()
    person = _addr(body["address"])
    ptr, data = read_attr_block(proc, person)
    if ptr is None:
        raise LookupError("Questa persona non ha un blocco attributi (forse non è un giocatore)")
    if data is None:
        raise OSError(f"Impossibile leggere il blocco attributi a 0x{ptr:08X}")
    return {"block": f"0x{ptr:08X}", "bytes": list(data)}


def api_player_get(body):
    return read_attributes(_proc(), _addr(body["address"]))


def api_player_set(body):
    proc = _proc()
    person = _addr(body["address"])
    n = write_attributes(proc, person, body.get("changes", []))
    return {"written": n, **read_attributes(proc, person)}


def api_analysis_capa(body):
    ref = body.get("reference")
    return find_ca_pa(_proc(), reference=_addr(ref) if ref else None)


def api_search_group(body):
    ranges = [(r.get("name", f"valore {i + 1}"), int(r["min"]), int(r["max"]))
              for i, r in enumerate(body.get("ranges", []))]
    return find_value_group(_proc(), ranges, int(body.get("distance", 0x200)))


def api_search_name_users(body):
    return find_name_users(_proc(), _addr(body["address"]))


def api_clubs(body):
    """Elenco club, letto una volta e tenuto in memoria (refresh=true per rileggere)."""
    proc = _proc()
    cache = state.get("clubs")
    if body.get("refresh") or not cache or cache["pid"] != proc.pid:
        items = list_clubs(proc)
        for c in items:
            c["_key"] = _norm(c["name"])
        cache = state["clubs"] = {"pid": proc.pid, "items": items}
    words = _norm(body.get("query", "")).split()
    hits = [c for c in cache["items"] if all(w in c["_key"] for w in words)]
    hits.sort(key=lambda c: (len(c["name"]), c["name"]))
    limit = int(body.get("limit", 200))
    return {"total": len(cache["items"]), "count": len(hits),
            "items": [{k: v for k, v in c.items() if k != "_key"} for c in hits[:limit]]}


def api_club_finances(body):
    return read_finances(_proc(), _addr(body["address"]))


def api_club_finances_set(body):
    proc = _proc()
    club = _addr(body["address"])
    n = write_finances(proc, club, body.get("changes", {}))
    return {"written": n, **read_finances(proc, club)}


def api_club_info(body):
    return read_info(_proc(), _addr(body["address"]))


def api_club_info_set(body):
    proc = _proc()
    club = _addr(body["address"])
    n = write_info(proc, club, body.get("changes"), body.get("reputation"), body.get("colors"))
    return {"written": n, **read_info(proc, club)}


def api_player_heal(body):
    proc = _proc()
    person = _addr(body["address"])
    n = heal(proc, person)
    return {"healed": n, **read_attributes(proc, person)}


def _players_cache(proc):
    cache = state.get("players")
    return cache["items"] if cache and cache["pid"] == proc.pid else None


def api_clubs_human(_):
    """Club guidati da un utente (oggetti allenatore umano, vedi clubs.human_clubs)."""
    return {"items": human_clubs(_proc())}


def api_tactics(_):
    return {"dir": tactics_dir(), "items": list_tactics()}


def api_tactic(body):
    """Tattica dal file + i migliori per ogni posto, nella rosa del club e sul mercato.
    Punteggio = attributi del ruolo (tactics.role_score, 1-20) x radice(voto nel ruolo / 20)."""
    proc = _proc()
    try:
        t = read_tactic(body["file"])
    except (OSError, TacticError) as e:
        raise LookupError(f"Tattica non leggibile: {e}")
    api_players({"limit": 0})
    items = state["players"]["items"]
    club = _norm(body.get("club", ""))
    n_squad = int(body.get("n_squad", 5))
    n_market = int(body.get("n_market", 8))
    min_rating = int(body.get("min_rating", 15))
    age_max = int(body.get("age_max") or 0)
    ask_max = body.get("asking_max")
    ca_min = int(body.get("ca_min") or 0)
    # rosa = chi gioca per il club: esclusi i prestati ad altri (nota "out") e i giocatori in
    # comproprietà che giocano nell'altro club (gioca per il club del primo contratto, squads[0])
    def plays_for(x):
        for k, q in enumerate(x["squads"]):
            if q["_club"] == club:
                return q["note"] != "out" and (q["note"] != "co" or k == 0)
        return False

    squad = [x for x in items if club and plays_for(x)]
    market = [x for x in items if x["asking"] > 0 and not (club and any(q["_club"] == club for q in x["squads"]))
              and (not age_max or (x["age"] is not None and x["age"] <= age_max))
              and (ask_max is None or x["asking"] <= ask_max) and x["ca"] >= ca_min]

    def score(x, off):
        """Punteggio nel ruolo: attributi del ruolo (1-20) x quanto conosce il ruolo (voto/20)."""
        # radice: "bravo" (15) rende ancora l'87%, "si adatta" (11) il 74%, "fuori ruolo" (7) il 59%
        return role_score(x["_attr"], off) * (x["_pos"][off - 0x1C] / 20) ** 0.5

    def pick(pool, off, n, need):
        k = off - 0x1C
        scored = [(score(x, off), x) for x in pool if x["_pos"][k] >= need]
        scored.sort(key=lambda s: -s[0])
        return [{"address": x["address"], "name": x["name"], "short": x["short"], "club_label": x["club_label"],
                 "age": x["age"], "ca": x["ca"], "pa": x["pa"], "rating": x["_pos"][k], "score": round(sc, 1),
                 "fit": role_score(x["_attr"], off),
                 "value": x["value"], "asking": x["asking"], "nation": x["nation"], "injured": x["injured"],
                 "role": x["role"], "birth": x["birth"]}
                for sc, x in scored[:n]]

    for s in t["slots"]:
        s["squad"] = pick(squad, s["role_off"], n_squad, 1)
        s["market"] = pick(market, s["role_off"], n_market, min_rating)

    # formazione consigliata: ogni giocatore in un solo posto (scelta golosa dal punteggio più alto)
    healthy = [x for x in squad if not x["injured"]]
    pairs = sorted(((score(x, s["role_off"]), i, x["address"])
                    for i, s in enumerate(t["slots"]) for x in healthy), reverse=True)
    by_addr = {x["address"]: x for x in healthy}
    used, done = set(), set()
    for sc, i, a in pairs:
        if i in done or a in used:
            continue
        x = by_addr[a]
        off = t["slots"][i]["role_off"]
        t["slots"][i]["pick"] = {"address": a, "name": x["name"], "short": x["short"], "rating": x["_pos"][off - 0x1C],
                                 "fit": role_score(x["_attr"], off),
                                 "ca": x["ca"], "score": round(sc, 1), "age": x["age"], "club_label": x["club_label"],
                                 "role": x["role"], "pa": x["pa"], "birth": x["birth"]}
        used.add(a)
        done.add(i)
    return t


def api_squad_boost(body):
    """Azioni su tutta la rosa di un club: morale al massimo e/o guarigione di tutti gli infortunati.
    Usa gli stessi filtri della rosa (club + squadra)."""
    proc = _proc()
    found = api_players({"club": body["club"], "team": body.get("team") or "", "limit": 1000})
    items = found["items"]
    morale = body.get("morale")
    done = {"players": len(items), "morale": 0, "healed": 0, "condition": 0, "errors": 0}
    cached = {x["address"]: x for x in (_players_cache(proc) or [])}
    for x in items:
        person = _addr(x["address"])
        try:
            if morale is not None:
                if write_extra(proc, person, "morale", int(morale)):
                    done["morale"] += 1
            if body.get("condition"):
                ok = write_extra(proc, person, "cond", 100)  # 10000 in memoria
                ok = write_extra(proc, person, "fitness", 100) and ok  # ritmo partita
                if ok:
                    done["condition"] += 1
            # tutti, non solo quelli segnati: l'elenco in cache può essere vecchio
            if body.get("heal"):
                if heal(proc, person):
                    done["healed"] += 1
                    if x["address"] in cached:
                        cached[x["address"]]["injured"] = False
        except PlayerError:
            done["errors"] += 1
    return done


def api_players(body):
    """Elenco giocatori con filtri. Letto una volta e tenuto in memoria (refresh=true per rileggere)."""
    proc = _proc()
    cache = state.get("players")
    if body.get("refresh") or not cache or cache["pid"] != proc.pid:
        items = list_players(proc)
        for x in items:
            x["_key"] = _norm(" ".join([x["first"], x["last"], x["common"]]))
            x["_club"] = _norm(x["club"])
            x["_nation"] = _norm(x["nation"])
            for q in x["squads"]:
                q["_club"] = _norm(q["club"])
        cache = state["players"] = {"pid": proc.pid, "items": items}
    words = _norm(body.get("query", "")).split()
    club = _norm(body.get("club", ""))
    role = (body.get("role") or "").strip()
    ca_min = int(body.get("ca_min") or 0)
    age_min = int(body.get("age_min") or 0)
    age_max = int(body.get("age_max") or 0)
    team = body.get("team")
    nation = _norm(body.get("nation", ""))
    ask_min = body.get("asking_min")
    ask_max = body.get("asking_max")

    def price_ok(x):
        """Filtro sul prezzo richiesto (in sterline, come in memoria): esclude -1 (tuo club) e 0 (non calcolato)."""
        if ask_min is None and ask_max is None:
            return True
        a = x["asking"]
        return a > 0 and (ask_min is None or a >= ask_min) and (ask_max is None or a <= ask_max)

    def squad_of(x):
        """La voce della rosa che corrisponde ai filtri club/squadra (None = escluso)."""
        if not club:
            return {} if not team or x["team"] == team else None
        for q in x["squads"]:
            same = club == q["_club"] or (body.get("club_contains") and club in q["_club"])
            if same and (not team or q["team"] == team):
                return q
        return None

    hits = []
    for x in cache["items"]:
        if not (all(w in x["_key"] for w in words)
                and (not role or any(part.split()[0] == role for part in x["role"].split(", ") if part))
                and x["ca"] >= ca_min
                and (not age_min or (x["age"] is not None and x["age"] >= age_min))
                and (not age_max or (x["age"] is not None and x["age"] <= age_max))
                and (not body.get("injured") or x["injured"])
                and (not nation or nation in x["_nation"])
                and price_ok(x)):
            continue
        q = squad_of(x)
        if q is None:
            continue
        hits.append(dict(x, loan=q.get("note", "")) if q else x)
    sort = body.get("sort", "ca")
    numeric = sort in ("ca", "pa", "age", "value", "asking")
    reverse = bool(body.get("desc", sort in ("ca", "pa")))
    hits.sort(key=lambda x: (x.get(sort) or 0) if numeric else str(x.get(sort) or ""), reverse=reverse)
    limit = int(body.get("limit", 300))
    if "nations" not in cache:
        cache["nations"] = sorted({x["nation"] for x in cache["items"] if x["nation"]})
    return {"total": len(cache["items"]), "count": len(hits), "nations": cache["nations"],
            "items": [{k: (v if k != "squads" else [{a: b for a, b in q.items() if not a.startswith("_")} for q in v])
                       for k, v in x.items() if not k.startswith("_")} for x in hits[:limit]]}


def api_modules(_):
    proc = _proc()
    mods = sorted(proc.modules(), key=lambda m: m[1])
    return {"items": [{"name": n, "base": f"0x{b:08X}", "size": s} for n, b, s in mods]}


ROUTES = {
    "status": api_status,
    "attach": api_attach,
    "scan/first": api_scan_first,
    "scan/next": api_scan_next,
    "scan/reset": api_scan_reset,
    "scan/results": api_scan_results,
    "scan/write": api_scan_write,
    "scan/restore": api_scan_restore,
    "read": api_read_many,
    "write": api_write,
    "freeze": api_freeze,
    "dump": api_dump,
    "search/string": api_search_string,
    "search/pointers": api_search_pointers,
    "search/values": api_search_values,
    "people": api_people,
    "person/attrs": api_person_attrs,
    "player/get": api_player_get,
    "player/set": api_player_set,
    "player/heal": api_player_heal,
    "analysis/capa": api_analysis_capa,
    "search/group": api_search_group,
    "search/name-users": api_search_name_users,
    "clubs": api_clubs,
    "club/finances": api_club_finances,
    "club/finances/set": api_club_finances_set,
    "club/info": api_club_info,
    "club/info/set": api_club_info_set,
    "players": api_players,
    "squad/boost": api_squad_boost,
    "clubs/human": api_clubs_human,
    "tactics": api_tactics,
    "tactic": api_tactic,
    "modules": api_modules,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        route = self.path.split("?")[0].removeprefix("/api/").strip("/")
        fn = ROUTES.get(route)
        if fn is None:
            return self._send(404, {"ok": False, "error": f"Rotta sconosciuta: {route}"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            with lock:
                result = fn(body)
            self._send(200, {"ok": True, **result})
        except (LookupError, PermissionError, ScanError, SearchError, PlayerError, AnalysisError, ClubError, OSError, ValueError, KeyError) as e:
            self._send(200, {"ok": False, "error": str(e)})
        except Exception as e:  # errore inatteso: lo registriamo
            traceback.print_exc()
            self._send(500, {"ok": False, "error": f"Errore interno: {e}"})


def freeze_loop():
    while True:
        time.sleep(0.1)
        if not frozen:
            continue
        with lock:
            proc = state["proc"]
            if proc is None or not proc.is_alive():
                continue
            for (addr, vtype), value in list(frozen.items()):
                proc.write_value(addr, vtype, value)


class ExclusiveServer(ThreadingHTTPServer):
    """Su Windows SO_REUSEADDR permette a due server di usare la stessa porta:
    le richieste finirebbero a un backend vecchio. Qui la porta è esclusiva."""
    allow_reuse_address = False
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def exit_with_parent():
    """L'editor ci passa uno stdin: quando si chiude (anche se l'editor
    crasha o viene chiuso a forza) il backend termina invece di restare orfano."""
    try:
        while sys.stdin.buffer.read(1024):
            pass
    except Exception:
        pass
    os._exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=47810)
    ap.add_argument("--watch-stdin", action="store_true")
    args = ap.parse_args()
    threading.Thread(target=freeze_loop, daemon=True).start()
    try:
        server = ExclusiveServer(("127.0.0.1", args.port), Handler)
    except OSError:
        print(f"PORT_IN_USE {args.port}", flush=True)
        sys.exit(2)
    if args.watch_stdin:
        threading.Thread(target=exit_with_parent, daemon=True).start()
    print(f"READY {args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
