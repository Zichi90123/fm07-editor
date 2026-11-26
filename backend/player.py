"""Attributi dei giocatori di FM2007 7.0.2.

Blocco attributi = *(persona - 0x20). Valori su scala 1-100: il gioco mostra
round(valore / 5). Layout ricavato da quello di FM08 (vedi MAPPA.md): in FM07
il blocco è più corto di 1 byte (un getter del gioco legge +0x6B invece di +0x6C).
"""
import collections
import struct

from people import OFF_ATTR_PTR, PageCache

# Oggetto giocatore = persona - 0xD4. I campi all'inizio dell'oggetto hanno gli stessi offset
# di FM08 (getter identici nelle due versioni), ma la persona è 0x18 byte più vicina:
# per questo, rispetto alla persona, gli offset sono quelli di FM08 + 0x18.
OBJ = -0xD4

# CA e PA: int16 a oggetto +0x14 / +0x16 (getter del gioco identico a FM08).
# PA negativa (-1…-10) = PA "a intervallo" del database.
OFF_CA = OBJ + 0x14
OFF_PA = OBJ + 0x16
ABILITY = [("ca", "CA (abilità attuale)", OFF_CA, 1, 200),
           ("pa", "PA (abilità potenziale)", OFF_PA, -10, 200)]

# Byte del blocco FM08 che in FM07 non c'è: gli attributi dopo di lui stanno 1 byte prima.
# Ipotesi: è il "sconosciuto (+0x46)" di FM08 (tra Rilanci e Intuito). Da verificare con
# `python verify.py`; se il byte mancante è un altro basta cambiare questo valore.
ATTR_GAP = 0x46


def fm07(off08):
    """Offset FM08 nel blocco attributi -> offset FM07."""
    return off08 - 1 if off08 > ATTR_GAP else off08


ATTR_FIRST = 0x35
ATTR_LAST = fm07(0x6B)

# (gruppo, nome, offset nel blocco)
ATTRIBUTES = [
    ("Tecniche", "Calci d'angolo", 0x51),
    ("Tecniche", "Calci di punizione", 0x59),
    ("Tecniche", "Colpo di testa", 0x38),
    ("Tecniche", "Contrasti", 0x3E),
    ("Tecniche", "Cross", 0x35),
    ("Tecniche", "Dribbling", 0x36),
    ("Tecniche", "Finalizzazione", 0x37),
    ("Tecniche", "Gioco di prima", 0x4C),
    ("Tecniche", "Lanci lunghi", 0x54),
    ("Tecniche", "Marcatura", 0x3A),
    ("Tecniche", "Passaggi", 0x3C),
    ("Tecniche", "Rigori", 0x3D),
    ("Tecniche", "Tecnica", 0x4D),
    ("Tecniche", "Tiri da lontano", 0x39),

    ("Mentali", "Aggressività", 0x63),
    ("Mentali", "Carisma", 0x5E),
    ("Mentali", "Concentrazione", 0x6B),
    ("Mentali", "Coraggio", 0x61),
    ("Mentali", "Creatività", 0x3F),
    ("Mentali", "Decisioni", 0x48),
    ("Mentali", "Determinazione", 0x69),
    ("Mentali", "Fantasia", 0x50),
    ("Mentali", "Freddezza", 0x6A),
    ("Mentali", "Gioco di squadra", 0x52),
    ("Mentali", "Impegno", 0x53),
    ("Mentali", "Intuito", 0x47),
    ("Mentali", "Posizione", 0x4A),
    ("Mentali", "Senza palla", 0x3B),

    ("Fisiche", "Accelerazione", 0x58),
    ("Fisiche", "Agilità", 0x64),
    ("Fisiche", "Elevazione", 0x5D),
    ("Fisiche", "Equilibrio", 0x60),
    ("Fisiche", "Forza", 0x5A),
    ("Fisiche", "Integrità fisica", 0x68),
    ("Fisiche", "Resistenza", 0x5B),
    ("Fisiche", "Velocità", 0x5C),

    ("Portiere", "Autorità in area", 0x42),
    ("Portiere", "Bloccare tiri", 0x40),
    ("Portiere", "Comunicazione", 0x43),
    ("Portiere", "Eccentricità", 0x55),
    ("Portiere", "Palle alte", 0x41),
    ("Portiere", "Resp. di pugno", 0x57),
    ("Portiere", "Riflessi", 0x4B),
    ("Portiere", "Rilanci", 0x45),
    ("Portiere", "Rinvii", 0x44),
    ("Portiere", "Uno contro uno", 0x49),
    ("Portiere", "Uscite", 0x56),

    ("Nascosti e piedi", "Piede sinistro", 0x4E),
    ("Nascosti e piedi", "Piede destro", 0x4F),
    ("Nascosti e piedi", "Costanza", 0x62),
    ("Nascosti e piedi", "Partite importanti", 0x65),
    ("Nascosti e piedi", "Predisposizione infortuni", 0x66),
    ("Nascosti e piedi", "Versatilità", 0x67),
    ("Nascosti e piedi", "Scorrettezza", 0x5F),
]
# sopra ci sono gli offset di FM08: qui si convertono in quelli di FM07
ATTRIBUTES = [(g, n, fm07(off)) for g, n, off in ATTRIBUTES]
BY_OFFSET = {off: (group, name) for group, name, off in ATTRIBUTES}


def to_display(raw):
    """1-100 -> 1-20 come lo mostra il gioco (83 -> 17, 98 -> 20)."""
    return max(1, min(20, (raw + 2) // 5))


def to_raw(display):
    return max(1, min(100, int(display) * 5))


class PlayerError(Exception):
    pass


def attr_block(proc, person):
    ptr = PageCache(proc).u32(person + OFF_ATTR_PTR)
    if not ptr:
        raise PlayerError("Questa persona non ha attributi da giocatore")
    return ptr


def read_ability(proc, person):
    out = []
    for field, name, off, lo, hi in ABILITY:
        data = proc.read(person + off, 2)
        if data is None:
            raise PlayerError(f"Impossibile leggere {name}")
        v = struct.unpack("<h", data)[0]
        out.append({"group": "Abilità", "name": name, "field": field, "raw": v, "value": v, "min": lo, "max": hi})
    return out


def read_attributes(proc, person):
    block = attr_block(proc, person)
    data = proc.read(block, ATTR_LAST + 1)
    if data is None:
        raise PlayerError(f"Impossibile leggere il blocco attributi a 0x{block:08X}")
    return {
        "block": f"0x{block:08X}",
        "attributes": read_ability(proc, person) + [
            {"group": g, "name": n, "offset": off, "raw": data[off], "value": to_display(data[off]),
             "min": 1, "max": 20}
            for g, n, off in ATTRIBUTES
        ] + read_extra(proc, person),
    }


def write_attributes(proc, person, changes):
    """changes = [{offset, value (1-20)} | {offset, raw (1-100)} | {field: ca|pa, value}]"""
    block = attr_block(proc, person)
    written = 0
    ability = {f: (name, off, lo, hi) for f, name, off, lo, hi in ABILITY}
    for ch in changes:
        if ch.get("field") and ch["field"] not in ability:
            if not write_extra(proc, person, ch["field"], ch["value"]):
                raise PlayerError(f"Scrittura fallita su {ch['field']}")
            written += 1
            continue
        if ch.get("field") in ability:
            name, off, lo, hi = ability[ch["field"]]
            v = int(ch["value"])
            if not lo <= v <= hi or v == 0:
                raise PlayerError(f"{name}: valore tra {lo} e {hi} (0 escluso)")
            if not proc.write(person + off, struct.pack("<h", v)):
                raise PlayerError(f"Scrittura fallita su {name}")
            written += 1
            continue
        off = int(ch["offset"])
        if off not in BY_OFFSET:
            raise PlayerError(f"Offset non valido: 0x{off:X}")
        raw = int(ch["raw"]) if "raw" in ch else to_raw(ch["value"])
        if not 1 <= raw <= 100:
            raise PlayerError("I valori devono essere tra 1 e 100 (1-20 nel gioco)")
        if not proc.write(block + off, bytes([raw])):
            raise PlayerError(f"Scrittura fallita su {BY_OFFSET[off][1]}")
        written += 1
    return written


# ===================================================== ruoli, stato, contratto
import datetime

# Ruoli: nel blocco attributi, valori 1-20 (20 = naturale).
POSITIONS = [  # formato del database: 9 posizioni + 3 lati
    (0x1C, "Portiere"), (0x1D, "Libero"), (0x1E, "Difensore"), (0x1F, "Mediano"),
    (0x20, "Centrocampista"), (0x21, "Trequartista"), (0x22, "Attaccante"),
    (0x23, "Esterno a tutta fascia"), (0x24, "Libero di svariare"),
    (0x25, "Lato destro"), (0x26, "Lato sinistro"), (0x27, "Lato centrale"),
]
PITCH_ROLES = [  # valutazioni per posizione in campo (verificate su Del Piero e Grygera)
    (0x28, "Difensore sinistro"), (0x29, "Difensore centrale"), (0x2A, "Difensore destro"),
    (0x2B, "Mediano centrale"), (0x2C, "Centrocampista sinistro"), (0x2D, "Centrocampista centrale"),
    (0x2E, "Centrocampista destro"), (0x2F, "Trequartista sinistro"), (0x30, "Trequartista centrale"),
    (0x31, "Trequartista destro"), (0x32, "Punta"), (0x33, "Esterno sinistro"), (0x34, "Esterno destro"),
]

# Condizione: u16 0-10000 a oggetto +0x08 (in FM08: Grygera 6250 -> 63% nel gioco).
OFF_CONDITION = OBJ + 0x08
# Ritmo partita: u16 0-10000 subito dopo la condizione.
# In FM08 servono condizione e ritmo a 10000 per vedere 100% nel gioco.
OFF_FITNESS = OBJ + 0x0A

# Morale: byte 0-20 a oggetto +0x48 (getter identico a FM08). In FM08: Basso 5-8, Ok 9-12,
# Buono 13-15, Molto buono 16-18. Il gioco lo ricalcola ogni giorno.
OFF_MORALE = OBJ + 0x48

# Infortuni: oggetto giocatore +0x30 -> stato (getter identico a FM08); stato +0x10 = lista, +0x14 = quanti.
# La lista è un array di puntatori (4 byte l'uno) a oggetti infortunio (PLAYER_INJURY, vtable 0x01097EDC):
#   +0x10 u16 durata stimata in giorni (NON scende col tempo: azzerarlo cambia solo l'etichetta),
#   +0x12 u16 durata totale. Ogni infortunio è puntato SOLO dalla lista: per guarire si toglie da lì.
PLAYER_STATUS = 0x30
STATUS_INJURY_LIST = 0x08   # FM07, trovato sulla partita (FM08: 0x10); injury_layout lo ricontrolla
STATUS_INJURY_COUNT = 0x0C
INJURY_VTABLE = 0x01097EDC
INJURY_DAYS_LEFT = 0x10
INJURY_DAYS_TOTAL = 0x12
MAX_INJURIES = 8

# Contratto: *( *(persona + 0x98) ) (FM08: persona +0xA0). Trovato sulla partita con tools/diag.py:
# chi punta agli array di contratti sta a persona +0x98 (gli oggetti giocatore sono consecutivi ogni 0x1E4
# byte, per questo la diagnosi lo vede anche come -0x14C dalla persona successiva).
OFF_PLAYER_OBJECT = OBJ
PLAYER_CONTRACT_LIST = 0x98 - OBJ
CONTRACT_VTABLE = 0x010A434C   # FULL_CONTRACT
# Getter del gioco: i premi sono spostati rispetto a FM08 (0x48/0x4C/0x50 -> 0x4C/0x50/0x58).
CONTRACT_FIELDS = [  # (campo, nome, offset, tipo)
    ("wage", "Stipendio (il gioco lo mostra all'anno)", 0x10, "wage"),
    ("start", "Inizio contratto", 0x18, "date"),
    ("expiry", "Scadenza contratto", 0x20, "date"),
    ("bonus_app", "Premio presenza (da verificare)", 0x4C, "money"),
    ("bonus_goal", "Premio gol (da verificare)", 0x50, "money"),
    ("bonus_cs", "Premio porta inviolata (da verificare)", 0x58, "money"),
]
CONTRACT_READ = 0x5C


# Mercato (int32 in sterline), oggetto +0x24 / +0x28 (getter di +0x24 identico a FM08).
# Prezzo richiesto: deciso dal club IA, -1 per i giocatori del club controllato dall'utente,
# 0 = non ancora calcolato.
MARKET_FIELDS = [  # (campo, nome, offset, minimo)
    ("value", "Valore", OBJ + 0x24, 0),
    ("asking", "Prezzo richiesto dal club", OBJ + 0x28, -1),
]


def contract_address(proc, person):
    cache = PageCache(proc)
    lst = cache.u32(person + OFF_PLAYER_OBJECT + PLAYER_CONTRACT_LIST)
    c = cache.u32(lst) if lst else 0
    if not c or cache.u32(c) != CONTRACT_VTABLE:
        return None
    return c


_injury_layout = {}


def injury_layout(proc):
    """(offset lista, offset numero) degli infortuni nell'oggetto stato.

    In FM08 sono +0x10 / +0x14; in FM07 il puntatore allo stato (oggetto giocatore +0x30) è confermato,
    ma dentro lo stato la lista non è a +0x10. La si cerca una volta per processo: la coppia
    (puntatore, numero 1-8) il cui primo elemento è un oggetto PLAYER_INJURY."""
    if proc.pid in _injury_layout:
        return _injury_layout[proc.pid]
    from people import PERSON_VTABLE, find_dword
    cache = PageCache(proc)
    votes = collections.Counter()
    for person in find_dword(proc, PERSON_VTABLE):
        st = cache.u32(person + OFF_PLAYER_OBJECT + PLAYER_STATUS)
        if not st:
            continue
        raw = cache.read(st, 0x60)
        for off in range(0, 0x58, 4):
            p, n = struct.unpack_from("<II", raw, off)
            if p and 0 < n <= MAX_INJURIES and cache.u32(cache.u32(p)) == INJURY_VTABLE:
                votes[off] += 1
        if votes and votes.most_common(1)[0][1] >= 10:
            break
    off = votes.most_common(1)[0][0] if votes else STATUS_INJURY_LIST
    _injury_layout[proc.pid] = (off, off + 4)
    return _injury_layout[proc.pid]


def injury_count(proc, cache, status):
    """Numero di infortuni (0 se lo stato non ha la forma attesa)."""
    _, count_off = injury_layout(proc)
    n = cache.u32(status + count_off)
    return n if 0 < n <= MAX_INJURIES else 0


def injuries(proc, person):
    """Indirizzi degli oggetti infortunio del giocatore."""
    cache = PageCache(proc)
    st = cache.u32(person + OFF_PLAYER_OBJECT + PLAYER_STATUS)
    if not st:
        return []
    list_off, count_off = injury_layout(proc)
    n = cache.u32(st + count_off)
    lst = cache.u32(st + list_off)
    if not lst or not 0 < n <= MAX_INJURIES:
        return []
    out = []
    for i in range(n):
        inj = cache.u32(lst + i * 4)
        if inj and cache.u32(inj) == INJURY_VTABLE:
            out.append(inj)
    return out


def _date_read(data):
    day, year = struct.unpack("<HH", data)
    if year <= 1900 or day > 365:
        return ""
    d = datetime.date(year, 1, 1) + datetime.timedelta(days=day)
    return d.strftime("%d/%m/%Y")


def _date_pack(text):
    try:
        d = datetime.datetime.strptime(str(text).strip(), "%d/%m/%Y").date()
    except ValueError:
        raise PlayerError(f"Data non valida: {text} (usa gg/mm/aaaa)")
    return struct.pack("<HH", (d - datetime.date(d.year, 1, 1)).days, d.year)


def read_extra(proc, person):
    """Campi oltre agli attributi: ruoli, condizione, contratto."""
    out = []
    block = attr_block(proc, person)
    pos = proc.read(block + 0x1C, 25)
    for group, table in (("Ruoli", POSITIONS), ("Ruoli in campo", PITCH_ROLES)):
        for off, name in table:
            v = pos[off - 0x1C]
            out.append({"group": group, "name": name, "field": f"pos:{off}", "kind": "number",
                        "raw": v, "value": v, "min": 1, "max": 20})
    cond = struct.unpack("<H", proc.read(person + OFF_CONDITION, 2))[0]
    out.append({"group": "Stato", "name": "Condizione %", "field": "cond", "kind": "number",
                "raw": cond, "value": (cond + 99) // 100, "min": 0, "max": 100})  # il gioco arrotonda per eccesso
    fit = struct.unpack("<H", proc.read(person + OFF_FITNESS, 2))[0]
    out.append({"group": "Stato", "name": "Ritmo partita %", "field": "fitness", "kind": "number",
                "raw": fit, "value": (fit + 99) // 100, "min": 0, "max": 100})
    mor = proc.read(person + OFF_MORALE, 1)[0]
    out.append({"group": "Stato", "name": "Morale (Basso 5-8 · Ok 9-12 · Buono 13-15 · Molto buono 16-18)", "field": "morale",
                "kind": "number", "raw": mor, "value": mor, "min": 0, "max": 20})
    for i, inj in enumerate(injuries(proc, person)):
        left, total = struct.unpack("<HH", proc.read(inj + INJURY_DAYS_LEFT, 4))
        out.append({"group": "Infortuni", "name": f"Infortunio {i + 1}: durata stimata in giorni (su {total})",
                    "field": f"inj:{i}", "kind": "number", "raw": left, "value": left, "min": 0, "max": 1000})
    for field, name, off, _ in MARKET_FIELDS:
        v = struct.unpack("<i", proc.read(person + off, 4))[0]
        out.append({"group": "Mercato", "name": name, "field": field, "kind": "money",
                    "raw": v, "value": v, "min": -1, "max": 2_000_000_000})
    c = contract_address(proc, person)
    if c:
        data = proc.read(c, CONTRACT_READ)
        for field, name, off, kind in CONTRACT_FIELDS:
            raw = data[off:off + 4]
            value = _date_read(raw) if kind == "date" else struct.unpack("<i", raw)[0]
            out.append({"group": "Contratto", "name": name, "field": field, "kind": kind,
                        "raw": value, "value": value, "min": 0, "max": 2_000_000_000})
    return out


def write_extra(proc, person, field, value):
    if field.startswith("pos:"):
        off = int(field[4:])
        if not (0x1C <= off <= 0x34):
            raise PlayerError("Ruolo non valido")
        v = int(value)
        if not 1 <= v <= 20:
            raise PlayerError("I ruoli vanno da 1 a 20")
        return proc.write(attr_block(proc, person) + off, bytes([v]))
    if field == "cond":
        v = int(value)
        if not 0 <= v <= 100:
            raise PlayerError("La condizione va da 0 a 100")
        return proc.write(person + OFF_CONDITION, struct.pack("<H", v * 100))
    if field == "fitness":
        v = int(value)
        if not 0 <= v <= 100:
            raise PlayerError("Il ritmo partita va da 0 a 100")
        return proc.write(person + OFF_FITNESS, struct.pack("<H", v * 100))
    if field == "morale":
        v = int(value)
        if not 0 <= v <= 20:
            raise PlayerError("Il morale va da 0 a 20")
        return proc.write(person + OFF_MORALE, bytes([v]))
    if field.startswith("inj:"):
        lst = injuries(proc, person)
        i = int(field[4:])
        if i >= len(lst):
            raise PlayerError("Infortunio non più presente: ricarica il giocatore")
        v = int(value)
        if not 0 <= v <= 1000:
            raise PlayerError("Giorni di stop tra 0 e 1000")
        return proc.write(lst[i] + INJURY_DAYS_LEFT, struct.pack("<H", v))
    market = {f: (off, lo) for f, _, off, lo in MARKET_FIELDS}
    if field in market:
        off, lo = market[field]
        v = int(value)
        if v < lo:
            raise PlayerError("Il valore non può essere negativo")
        return proc.write(person + off, struct.pack("<i", v))
    spec = {f: (off, kind) for f, _, off, kind in CONTRACT_FIELDS}
    if field in spec:
        c = contract_address(proc, person)
        if not c:
            raise PlayerError("Questo giocatore non ha un contratto riconoscibile")
        off, kind = spec[field]
        if kind == "date":
            return proc.write(c + off, _date_pack(value))
        v = int(value)
        if v < 0:
            raise PlayerError("Il valore non può essere negativo")
        return proc.write(c + off, struct.pack("<i", v))
    raise PlayerError(f"Campo sconosciuto: {field}")


def heal(proc, person):
    """Toglie tutti gli infortuni dalla lista del giocatore e porta la condizione al 100%.
    Gli oggetti infortunio restano in memoria ma non sono più usati da nessuno."""
    cache = PageCache(proc)
    st = cache.u32(person + OFF_PLAYER_OBJECT + PLAYER_STATUS)
    if not st:
        raise PlayerError("Stato del giocatore non trovato")
    n = injury_count(proc, cache, st)
    if not n:
        return 0
    if len(injuries(proc, person)) != n:
        raise PlayerError("La lista infortuni non ha la forma attesa: non la tocco")
    if not proc.write(st + injury_layout(proc)[1], struct.pack("<I", 0)):
        raise PlayerError("Scrittura fallita")
    proc.write(person + OFF_CONDITION, struct.pack("<H", 10000))
    return n


# =========================================================== elenco giocatori
from people import (PERSON_VTABLE, OFF_FIRST_NAME, OFF_LAST_NAME, OFF_COMMON_NAME, OFF_BIRTH,
                    find_dword, read_name, read_date)

ATTR_BLOCK_VTABLE = 0x012F2754  # PLAYING_DATA
CONTRACT_CLUB = 0x08
NATION_PTR = 0x50           # persona +0x50 -> oggetto nazione
NATION_VTABLE = 0x0133FAE4  # NATION: nome a +0x20 (record a +0x28, come i club)
LOAN_VTABLE = 0x012F7174  # LOAN_CONTRACT: secondo elemento della lista contratti
LOAN_CLUB = 0x08          # club che ha il giocatore in prestito
CLUB_NAME_RECORD = 0x28
ROLE_SHOWN = 16  # da questo valore il gioco elenca il ruolo nel profilo

# (byte, sigla, usa i lati?)
ROLE_ABBR = [(0x1C, "Por", False), (0x1D, "Lib", False), (0x1E, "D", True), (0x1F, "M", False),
             (0x20, "C", True), (0x21, "T", True), (0x22, "A", False), (0x23, "TF", True)]  # "libero di svariare" non compare nell'elenco del gioco
SIDES = [(0x25, "D"), (0x26, "S"), (0x27, "C")]


def role_string(pos):
    """25 byte dei ruoli (da +0x1C) -> sigla come nell'elenco rosa del gioco, es. 'T SC, A C'."""
    sides = "".join(letter for off, letter in SIDES if pos[off - 0x1C] >= ROLE_SHOWN) or "C"
    parts = []
    for off, abbr, use_sides in ROLE_ABBR:
        if pos[off - 0x1C] >= ROLE_SHOWN:
            parts.append(f"{abbr} {sides}" if use_sides else (f"{abbr} C" if abbr == "A" else abbr))
    return ", ".join(parts)


def _club_name(cache, club, names):
    if club in names:
        return names[club]
    rec = cache.u32(club + CLUB_NAME_RECORD)
    s = cache.u32(rec + 8) if rec else 0
    name = ""
    if s:
        raw = cache.read(s, 96)
        for i in range(0, len(raw) - 1, 2):
            if raw[i] == 0 and raw[i + 1] == 0:
                raw = raw[:i]
                break
        name = raw.decode("utf-16-le", errors="replace")
    names[club] = name
    return name


def list_players(proc):
    """Tutti i giocatori (persone con blocco attributi): nome, club, squadra, ruoli, età, CA, PA."""
    from clubs import game_date, pick_team, player_teams
    cache = PageCache(proc)
    clubs = {}
    nations = {}
    teams = player_teams(proc)
    today = game_date(proc)
    out = []
    for person in find_dword(proc, PERSON_VTABLE):
        block = cache.u32(person + OFF_ATTR_PTR)
        if not block or cache.u32(block) != ATTR_BLOCK_VTABLE:
            continue
        first = read_name(cache, cache.u32(person + OFF_FIRST_NAME))
        last = read_name(cache, cache.u32(person + OFF_LAST_NAME))
        common = read_name(cache, cache.u32(person + OFF_COMMON_NAME))
        if not (first or last or common):
            continue
        ca, pa = struct.unpack("<hh", cache.read(person + OFF_CA, 4))
        obj = person + OFF_PLAYER_OBJECT
        lst = cache.u32(obj + PLAYER_CONTRACT_LIST)
        n = cache.u32(obj + PLAYER_CONTRACT_LIST + 4) if lst else 0
        entries = [cache.u32(lst + i * 4) for i in range(n)] if 0 < n <= 4 else []
        club = 0       # club proprietario (primo contratto)
        loan_club = 0  # club che lo ha in prestito
        co_owners = []  # comproprietà: altri contratti veri
        for e in entries:
            vt = cache.u32(e) if e else 0
            if vt == CONTRACT_VTABLE:
                if not club:
                    club = cache.u32(e + CONTRACT_CLUB)
                else:
                    co_owners.append(cache.u32(e + CONTRACT_CLUB))
            elif vt == LOAN_VTABLE:
                loan_club = cache.u32(e + LOAN_CLUB)
        st = cache.u32(obj + PLAYER_STATUS)
        injured = bool(st and injury_count(proc, cache, st))
        member = teams.get(person, [])
        # una voce per ogni club di cui il giocatore fa parte (proprietario, prestito, comproprietà)
        squads = []
        for k, note in [(club, "out" if loan_club else ("co" if co_owners else "")), (loan_club, "in")] + [(x, "co") for x in co_owners]:
            if not k or any(q["_club"] == k for q in squads):
                continue
            mine = [m for m in member if m[0] == k]
            team, suffix = pick_team(mine, k)[1:] if mine else ("first", "")
            squads.append({"_club": k, "addr": f"0x{k:08X}", "club": _club_name(cache, k, clubs), "team": team,
                           "suffix": suffix, "note": note})
        if not squads and member:  # senza contratto (es. solo nazionale)
            k, team, suffix = pick_team(member, 0)
            squads.append({"_club": k, "addr": f"0x{k:08X}", "club": _club_name(cache, k, clubs), "team": team,
                           "suffix": suffix, "note": ""})
        main = next((q for q in squads if q["note"] == "in"), squads[0] if squads else None)
        club_name = main["club"] if main else ""
        team = main["team"] if main else ""
        label = f"{club_name} {main['suffix']}".strip() if main else ""
        if loan_club and len(squads) > 1:
            label += f" (prestito da {squads[0]['club']})"
        elif co_owners:
            label += " (comproprietà)"
        for q in squads:
            del q["_club"]
        nat = cache.u32(person + NATION_PTR)
        nation = _club_name(cache, nat, nations) if nat and cache.u32(nat) == NATION_VTABLE else ""
        value, asking = struct.unpack("<ii", cache.read(person + MARKET_FIELDS[0][2], 8))
        birth = read_date(cache, person + OFF_BIRTH)
        age = None
        if birth and today:
            b = datetime.date.fromisoformat(birth)
            age = today.year - b.year - ((today.month, today.day) < (b.month, b.day))
        out.append({
            "address": f"0x{person:08X}",
            "name": common or f"{first} {last}".strip(),
            "first": first, "last": last, "common": common,
            "club": club_name,
            "team": team,
            "club_label": label,
            "squads": squads,
            "age": age,
            "nation": nation,
            "value": value,
            "asking": asking,
            "role": role_string(cache.read(block + 0x1C, 25)),
            "_pos": cache.read(block + 0x1C, 25),  # voti di ruolo grezzi (offset 0x1C-0x34)
            "_attr": cache.read(block + ATTR_FIRST, ATTR_LAST - ATTR_FIRST + 1),  # attributi 1-100
            "short": common or last or first,
            "birth": birth,
            "ca": ca, "pa": pa,
            "injured": injured,
        })
    return out
