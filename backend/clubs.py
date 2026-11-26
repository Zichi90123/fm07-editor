"""Club e finanze di FM2007 7.0.2 (vedi MAPPA.md).

I soldi in memoria sono in sterline; il gioco li mostra moltiplicati per un
fattore di cambio (dipende dalla valuta scelta). Qui si lavora sempre con i
valori interni: la conversione la fa l'interfaccia.

L'oggetto CLUB ha lo stesso layout di FM08 fino a +0x130 (stessi membri nel costruttore);
CLUB_FINANCE invece è cambiato: gli offset vengono dal confronto dei metodi del gioco.
"""
import struct

from people import PageCache, find_dword

CLUB_VTABLE = 0x0133ADAC
CLUB_ID = 0x14
CLUB_NAME_RECORD = 0x28      # riferimento al nome lungo: record lista nomi
NAME_RECORD_STRING = 0x08
CLUB_FINANCE_PTR = 0x118     # FM08: +0x11C (trovato sulla partita: 300 finanze su 300)

FINANCE_VTABLE = 0x0133ABD4
FINANCE_CLUB_PTR = 0x08      # l'oggetto finanze punta al suo club: usato come controllo

# (chiave, nome, offset nell'oggetto finanze, tipo, modificabile)
#   tipo "money"  = sterline
#   tipo "weekly" = sterline a settimana (il gioco le mostra all'anno: x52)
#   tipo "number" = numero semplice
# FM08 -> FM07: saldo +0x04 (uguale), fondi +0x40/+0x44 -> +0x30/+0x34, % +0x48 -> +0x38,
# spesa ingaggi +0xC0 -> +0xB0. Il budget ingaggi (+0xB8 in FM08) segue lo stesso spostamento
# di -0x10 degli altri campi vicini, ma non c'è un metodo che lo confermi: da verificare.
# Il finanziamento del settore giovanile di FM08 non ha un equivalente riconoscibile.
FINANCE_FIELDS = [
    ("balance", "Saldo (Bilancio)", 0x04, "money", True),
    ("budget_remaining", "Fondo campagna acquisti (Rimanente)", 0x30, "money", True),
    ("budget_season", "Fondo campagna acquisti (Stagione)", 0x34, "money", True),
    ("transfer_pct", "% entrate del mercato disponibile", 0x38, "number", True),
    ("wage_budget", "Budget ingaggi", 0xA8, "weekly", True),
    ("wage_spend", "Spesa attuale per gli ingaggi (calcolata dal gioco)", 0xB0, "weekly", False),
]
FIELDS = {k: (name, off, kind, editable) for k, name, off, kind, editable in FINANCE_FIELDS}


class ClubError(Exception):
    pass


def _name(cache, club):
    try:
        rec = cache.u32(club + CLUB_NAME_RECORD)
        s = cache.u32(rec + NAME_RECORD_STRING) if rec else 0
        if not s:
            return ""
        raw = cache.read(s, 128)
    except Exception:
        return ""
    for i in range(0, len(raw) - 1, 2):
        if raw[i] == 0 and raw[i + 1] == 0:
            raw = raw[:i]
            break
    return raw.decode("utf-16-le", errors="replace")


def list_clubs(proc):
    cache = PageCache(proc)
    out = []
    for club in find_dword(proc, CLUB_VTABLE):
        name = _name(cache, club)
        if name:
            out.append({"address": f"0x{club:08X}", "name": name, "id": cache.u32(club + CLUB_ID)})
    return out


def finance_object(proc, club):
    cache = PageCache(proc)
    if cache.u32(club) != CLUB_VTABLE:
        raise ClubError("Questo indirizzo non è (più) un club: ricarica l'elenco")
    fin = cache.u32(club + CLUB_FINANCE_PTR)
    if not fin or cache.u32(fin) != FINANCE_VTABLE or cache.u32(fin + FINANCE_CLUB_PTR) != club:
        raise ClubError("Questo club non ha un oggetto finanze riconoscibile")
    return fin


def read_finances(proc, club):
    fin = finance_object(proc, club)
    out = []
    for key, name, off, kind, editable in FINANCE_FIELDS:
        data = proc.read(fin + off, 4)
        if data is None:
            raise ClubError(f"Impossibile leggere {name}")
        out.append({"key": key, "name": name, "value": struct.unpack("<i", data)[0],
                    "kind": kind, "editable": editable})
    return {"finance": f"0x{fin:08X}", "fields": out}


def write_finances(proc, club, changes):
    """changes = {chiave: valore interno (sterline)}"""
    fin = finance_object(proc, club)
    written = 0
    for key, value in changes.items():
        if key not in FIELDS:
            raise ClubError(f"Campo sconosciuto: {key}")
        name, off, kind, editable = FIELDS[key]
        if not editable:
            raise ClubError(f"{name}: il gioco lo ricalcola, non si modifica")
        value = int(value)
        if key == "transfer_pct" and not 0 <= value <= 100:
            raise ClubError("La percentuale va da 0 a 100")
        if kind != "number" and not -2_000_000_000 <= value <= 2_000_000_000:
            raise ClubError(f"{name}: valore fuori dai limiti di un intero a 4 byte")
        if not proc.write(fin + off, struct.pack("<i", value)):
            raise ClubError(f"Scrittura fallita su {name}")
        written += 1
    return written


# ------------------------------------------------------------- informazioni
# Campi dell'oggetto club trovati con statistiche su 12.813 club (vedi MAPPA.md).
# (chiave, nome, offset, tipo, minimo, massimo)
INFO_FIELDS = [
    ("founded", "Anno di fondazione", 0xE2, "u16", 1800, 2100),
    ("status", "Stato", 0xEA, "u8", 1, 3),                      # 1 pro, 2 semi-pro, 3 dilettanti
    ("training", "Strutture di allenamento", 0xEB, "u8", 1, 20),
    ("youth", "Strutture giovanili", 0xE1, "u8", 1, 20),
    ("academy", "Scuola calcio giovanile", 0xE0, "u8", 0, 1),
    ("attendance", "Media spettatori", 0xF4, "i32", 0, 250_000),
    ("min_attendance", "Minimo spettatori", 0xF8, "i32", 0, 250_000),
    ("max_attendance", "Massimo spettatori", 0xFC, "i32", 0, 250_000),
    ("season_tickets", "Abbonati", 0xF0, "i32", 0, 250_000),
]
INFO = {f[0]: f[1:] for f in INFO_FIELDS}
FMT = {"u8": "<B", "u16": "<H", "i32": "<i"}

CLUB_COLORS_PTR = 0x50       # array di colori ARGB (0xFFRRGGBB), quanti a +0x54
CLUB_COLORS_COUNT = 0x54
CLUB_TEAMS_PTR = 0x68        # array di squadre (TEAM), quante a +0x6C
CLUB_TEAMS_COUNT = 0x6C
TEAM_REPUTATION = 0x6C       # u16 0-10000 (FM08 +0x70): Milan 9650, Chelsea 9300, Juventus 7750, Venezia 3500


def _check_club(cache, club):
    if cache.u32(club) != CLUB_VTABLE:
        raise ClubError("Questo indirizzo non è (più) un club: ricarica l'elenco")


def club_teams(cache, club):
    """[(indirizzo squadra, chiave, suffisso)] delle squadre del club."""
    lst = cache.u32(club + CLUB_TEAMS_PTR)
    n = cache.u32(club + CLUB_TEAMS_COUNT)
    if not lst or not 0 < n <= 20:
        return []
    out = []
    for t in struct.unpack(f"<{n}I", cache.read(lst, n * 4)):
        if t and cache.u32(t) == TEAM_VTABLE and cache.u32(t + TEAM_CLUB) == club:
            flags = cache.read(t + TEAM_NOT_FIRST, 3)
            out.append((t,) + team_kind(flags[0], flags[2]))
    return out


def _colors(cache, club):
    lst = cache.u32(club + CLUB_COLORS_PTR)
    n = cache.u32(club + CLUB_COLORS_COUNT)
    if not lst or not 0 < n <= 8:
        return 0, []
    return lst, list(struct.unpack(f"<{n}I", cache.read(lst, n * 4)))


def read_info(proc, club):
    cache = PageCache(proc)
    _check_club(cache, club)
    raw = proc.read(club, 0x100)
    if raw is None:
        raise ClubError("Impossibile leggere il club")
    fields = [{"key": k, "name": name, "value": struct.unpack_from(FMT[t], raw, off)[0], "min": lo, "max": hi}
              for k, name, off, t, lo, hi in INFO_FIELDS]
    teams = []
    for t, kind, suffix in club_teams(cache, club):
        rep = struct.unpack("<H", proc.read(t + TEAM_REPUTATION, 2))[0]
        teams.append({"address": f"0x{t:08X}", "kind": kind, "suffix": suffix, "reputation": rep})
    teams.sort(key=lambda x: RANK[x["kind"]])
    _, colors = _colors(cache, club)
    return {"fields": fields, "teams": teams, "colors": [f"#{c & 0xFFFFFF:06X}" for c in colors]}


def write_info(proc, club, changes, reputation=None, colors=None):
    """changes = {chiave: valore}; reputation = {indirizzo squadra: valore}; colors = {indice: "#RRGGBB"}"""
    cache = PageCache(proc)
    _check_club(cache, club)
    todo = []
    for key, value in (changes or {}).items():
        if key not in INFO:
            raise ClubError(f"Campo sconosciuto: {key}")
        name, off, t, lo, hi = INFO[key]
        value = int(value)
        if not lo <= value <= hi:
            raise ClubError(f"{name}: valore da {lo} a {hi}")
        todo.append((club + off, struct.pack(FMT[t], value), name))
    teams = {t for t, _, _ in club_teams(cache, club)}
    for addr, value in (reputation or {}).items():
        t = int(addr, 16) if isinstance(addr, str) else int(addr)
        if t not in teams:
            raise ClubError("La squadra non appartiene a questo club: ricarica")
        value = int(value)
        if not 0 <= value <= 10000:
            raise ClubError("La reputazione va da 0 a 10000")
        todo.append((t + TEAM_REPUTATION, struct.pack("<H", value), "Reputazione"))
    if colors:
        lst, current = _colors(cache, club)
        for i, rgb in colors.items():
            i = int(i)
            if not 0 <= i < len(current):
                raise ClubError("Colore inesistente")
            v = int(str(rgb).lstrip("#"), 16)
            if not 0 <= v <= 0xFFFFFF:
                raise ClubError(f"Colore non valido: {rgb}")
            todo.append((lst + i * 4, struct.pack("<I", (current[i] & 0xFF000000) | v), "Colore"))
    for addr, data, name in todo:  # tutto controllato prima: niente scritture a metà
        if not proc.write(addr, data):
            raise ClubError(f"Scrittura fallita su {name}")
    return len(todo)


# ------------------------------------------------------------------ squadre
# Ogni club ha più squadre (prima squadra, riserve, giovanili), oggetti TEAM (vtable 0x01339A4C):
#   +0x38 ptr club (getter identico a FM08), +0x41 byte (0 = prima squadra), +0x43 byte limite d'età
#   +0x90 elenco giocatori: vtable STEP_ARRAY<PLAYER> (in FM08 a +0xB0, dal costruttore),
#   +0x94 ptr array (oggetti giocatore = persona - 0xD4), +0x98 quanti
TEAM_VTABLE = 0x01339A4C
TEAM_CLUB = 0x38
TEAM_NOT_FIRST = 0x41
TEAM_AGE_LIMIT = 0x43
TEAM_PLAYERS_PTR = 0x94
TEAM_PLAYERS_COUNT = 0x98
PLAYER_OBJECT_TO_PERSON = 0xD4


def team_kind(not_first, age_limit):
    """-> (chiave, suffisso come nel gioco)"""
    if not not_first:
        return "first", ""
    if age_limit and age_limit < 100:
        return "youth", "Prim." if age_limit == 20 else f"U{age_limit}"
    return "reserves", "Ris."


RANK = {"first": 0, "reserves": 1, "youth": 2}


def player_teams(proc):
    """{indirizzo persona: [(club, chiave squadra, suffisso), ...]} per tutti i giocatori in una rosa.
    Un giocatore può stare in più rose: prima squadra e riserve del suo club, ma anche
    nazionali (anch'esse squadre di un "club")."""
    cache = PageCache(proc)
    out = {}
    for team in find_dword(proc, TEAM_VTABLE):
        club = cache.u32(team + TEAM_CLUB)
        if not club or cache.u32(club) != CLUB_VTABLE:
            continue
        flags = cache.read(team + TEAM_NOT_FIRST, 3)
        kind = team_kind(flags[0], flags[2])
        lst = cache.u32(team + TEAM_PLAYERS_PTR)
        n = cache.u32(team + TEAM_PLAYERS_COUNT)
        if not lst or not 0 < n <= 200:
            continue
        for obj in struct.unpack(f"<{n}I", cache.read(lst, n * 4)):
            if obj:
                out.setdefault(obj + PLAYER_OBJECT_TO_PERSON, []).append((club,) + kind)
    return out


def pick_team(memberships, contract_club):
    """Sceglie la rosa da mostrare: quella del club del contratto (la più importante se più d'una)."""
    own = [m for m in memberships if m[0] == contract_club] or memberships
    return min(own, key=lambda m: RANK[m[1]])


# --------------------------------------------------------------- data del gioco
# Data corrente della partita: in FM08 è un oggetto data (vtable SI_SHORT_DATE + giorno, anno) in un
# punto fisso di fm.exe (0x019242F0), letto dal codice tramite un oggetto globale, quindi non si
# ritrova nell'eseguibile di FM07. Finché non si trova l'indirizzo fisso (GAME_DATE), la si cerca:
# tra gli oggetti data nella sezione dati di fm.exe si prende la data più frequente.
GAME_DATE = None
DATE_VTABLE = 0x013D1794     # SI_SHORT_DATE
EXE_DATA = (0x01586000, 0x0190F000)  # sezione .data di fm.exe 7.0.2
_date_cache = {}


def _to_date(day, year):
    import datetime
    if not 2000 <= year < 2100 or day > 365:
        return None
    return datetime.date(year, 1, 1) + datetime.timedelta(days=day)


def game_date_candidates(proc):
    """{indirizzo: data} di tutti gli oggetti data plausibili nella sezione dati di fm.exe."""
    import numpy as np
    out = {}
    lo, hi = EXE_DATA
    for base, size in proc.regions():
        start, end = max(base, lo), min(base + size, hi)
        if start >= end:
            continue
        data = proc.read(start, end - start)
        if data is None:
            continue
        arr = np.frombuffer(data, dtype="<u4", count=len(data) // 4)
        for i in np.nonzero(arr[:-1] == DATE_VTABLE)[0]:
            v = int(arr[i + 1])
            d = _to_date(v & 0xFFFF, v >> 16)
            if d:
                out[start + int(i) * 4 + 4] = d
    return out


def game_date(proc):
    if GAME_DATE:
        raw = proc.read(GAME_DATE, 4)
        return _to_date(*struct.unpack("<HH", raw)) if raw else None
    import collections
    import time
    key = proc.pid
    hit = _date_cache.get(key)
    if hit and time.time() - hit[0] < 30:  # la data cambia solo quando il gioco avanza
        return hit[1]
    cands = game_date_candidates(proc)
    best = None
    if cands:
        count = collections.Counter(cands.values())
        best = max(count, key=lambda d: (count[d], d))
    _date_cache[key] = (time.time(), best)
    return best


# --------------------------------------------------------------- valuta mostrata dal gioco
# Indice della valuta scelta nelle preferenze (u32 in un punto fisso di fm.exe).
# In FM08 0x018FAE88 e tabella a 0x01B227CC (verificati). In FM07 non ancora trovati: i candidati
# ricavati dal codice (indice 0x015FD5F8, tabella 0x01843CEC) non danno valori credibili sulla
# partita di prova. Con CURRENCY_INDEX = None l'interfaccia usa il cambio impostato a mano.
CURRENCY_INDEX = None
# Tabella delle valute in fm.exe: una voce ogni 0x78 byte (in FM08). Alla voce +0x00 un u32 (3 o 4),
# a +0x04 un double = cambio rispetto alla sterlina (euro 1,45, dollaro 1,9).
CURRENCY_TABLE = None
CURRENCY_STEP = 0x78
CURRENCY_MAX = 80


def currency(proc):
    """-> {"index", "rate"} della valuta mostrata dal gioco, o None se i dati non sono credibili."""
    if CURRENCY_INDEX is None:
        return None
    raw = proc.read(CURRENCY_INDEX, 4)
    if not raw:
        return None
    idx = struct.unpack("<I", raw)[0]
    if idx >= CURRENCY_MAX:
        return None
    entry = proc.read(CURRENCY_TABLE + idx * CURRENCY_STEP, 12)
    if not entry:
        return None
    count, rate = struct.unpack("<Id", entry)
    if not 1 <= count <= 10 or not 0.0001 < rate < 1e6:
        return None
    return {"index": idx, "rate": round(rate, 4)}


# --------------------------------------------------------------- club guidati da un utente
# Gli allenatori umani: HUMAN_NON_PLAYER, sotto-oggetto "persona" (a +0x25C; in FM08 +0x29C).
# Come i giocatori hanno nome (+0x2C) e cognome (+0x30); a +0xA0 la lista contratti:
# contratto = *( *(allenatore + 0xA0) ), FULL_CONTRACT, club a +0x08.
HUMAN_VTABLE = 0x01348384
HUMAN_CONTRACTS = 0x98  # come i giocatori: la parte "persona" ha la lista contratti a +0x98 (FM08 +0xA0)
CONTRACT_VTABLE = 0x010A434C
CONTRACT_CLUB = 0x08


def human_clubs(proc):
    """[{address, name, id, manager}] dei club allenati da un utente."""
    from people import read_name
    cache = PageCache(proc)
    out = []
    for man in find_dword(proc, HUMAN_VTABLE):
        lst = cache.u32(man + HUMAN_CONTRACTS)
        con = cache.u32(lst) if lst else 0
        if not con or cache.u32(con) != CONTRACT_VTABLE:
            continue  # utente senza squadra (disoccupato)
        club = cache.u32(con + CONTRACT_CLUB)
        if not club or cache.u32(club) != CLUB_VTABLE:
            continue
        manager = f"{read_name(cache, cache.u32(man + 0x2C))} {read_name(cache, cache.u32(man + 0x30))}".strip()
        out.append({"address": f"0x{club:08X}", "name": _name(cache, club),
                    "id": cache.u32(club + CLUB_ID), "manager": manager})
    return out
