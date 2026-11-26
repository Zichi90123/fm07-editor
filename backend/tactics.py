"""Tattiche lette dai file .tac (Documenti/Sports Interactive/Football Manager 2007/tactics).

Formato decodificato su FM2008 (vedi MAPPA.md); NON ancora verificato sui file di FM2007:
i file che non corrispondono vengono semplicemente saltati.
  +0x00  "\\x02\\x01cat." + 4 byte
  +0x0A  stringa nome:   u32 lunghezza, UTF-16, u16 0
         stringa autore: u32 lunghezza, UTF-16, u16 0
         4 byte, poi 0x39 byte del portiere/squadra
  poi 10 blocchi da 0x51 byte, uno per giocatore di movimento:
    +0x1D  12 coppie (x, y) senza palla (difesa), una per zona della palla
    +0x35  12 coppie (x, y) con la palla (attacco, freccia compresa)
    +0x4D  u16 posizione di partenza, u16 destinazione della freccia
           byte basso = fila (0x04 difesa, 0x08 mediani, 0x10 centrocampo, 0x20 trequarti,
           0x40 attacco) + 0x80 se colonna sinistra; byte alto = colonna (0x01 centro-sinistra,
           0x02 centro, 0x04 centro-destra, 0x08 destra; 0 = sinistra).
Il file è la tattica SALVATA: se la modifichi nel gioco, salvala per vederla qui.
"""
import os
import struct

BLOCK = 0x51
SLOTS = 10
OFF_POS = 0x4D

ROWS = {0x04: "D", 0x08: "DM", 0x10: "M", 0x20: "AM", 0x40: "ST"}
ROW_ORDER = ["GK", "D", "DM", "M", "AM", "ST"]
COLS = {0x00: "L", 0x01: "CL", 0x02: "C", 0x04: "CR", 0x08: "R"}
COL_ORDER = ["L", "CL", "C", "CR", "R"]

# (fila, lato) -> (offset del voto nel blocco attributi, sigla, nome)
ROLE = {
    ("GK", "C"): (0x1C, "Por", "Portiere"),
    ("D", "L"): (0x28, "DS", "Difensore sinistro"),
    ("D", "C"): (0x29, "DC", "Difensore centrale"),
    ("D", "R"): (0x2A, "DD", "Difensore destro"),
    ("DM", "L"): (0x33, "ES", "Esterno sinistro"),
    ("DM", "C"): (0x2B, "MED", "Mediano"),
    ("DM", "R"): (0x34, "ED", "Esterno destro"),
    ("M", "L"): (0x2C, "CS", "Centrocampista sinistro"),
    ("M", "C"): (0x2D, "CC", "Centrocampista centrale"),
    ("M", "R"): (0x2E, "CD", "Centrocampista destro"),
    ("AM", "L"): (0x2F, "TS", "Trequartista sinistro"),
    ("AM", "C"): (0x30, "TC", "Trequartista centrale"),
    ("AM", "R"): (0x31, "TD", "Trequartista destro"),
    ("ST", "C"): (0x32, "P", "Punta"),
}


class TacticError(Exception):
    pass


def tactics_dir():
    return os.path.join(os.path.expanduser("~"), "Documents", "Sports Interactive",
                        "Football Manager 2007", "tactics")


def _string(data, off):
    n = struct.unpack_from("<I", data, off)[0]
    if n > 200:
        raise TacticError("File tattica non riconosciuto")
    s = data[off + 4:off + 4 + n * 2].decode("utf-16-le", errors="replace")
    return s, off + 4 + n * 2 + 2


def _decode_pos(v):
    row_bits, col_bits = v & 0x7F, v >> 8
    row = ROWS.get(row_bits)
    col = "L" if v & 0x80 else COLS.get(col_bits)
    if row is None or col is None:
        return None
    return {"row": row, "col": col}


def _side(col):
    return "L" if col == "L" else "R" if col == "R" else "C"


def parse(data):
    if data[2:6] != b"cat.":
        raise TacticError("Non è un file tattica di FM")
    name, off = _string(data, 0x0A)
    author, off = _string(data, off)
    first = off + 4 + 0x39
    if first + SLOTS * BLOCK > len(data):
        raise TacticError("File tattica troppo corto")
    slots = [{"n": 0, "base": {"row": "GK", "col": "C"}, "dest": {"row": "GK", "col": "C"}}]
    for i in range(SLOTS):
        blk = data[first + i * BLOCK:first + (i + 1) * BLOCK]
        base_v, dest_v = struct.unpack_from("<HH", blk, OFF_POS)
        base, dest = _decode_pos(base_v), _decode_pos(dest_v)
        if base is None:
            raise TacticError(f"Posizione non riconosciuta nel blocco {i + 1}: {base_v:#06x}")
        slots.append({"n": i + 1, "base": base, "dest": dest or base})
    for s in slots:
        off_role, abbr, role_name = ROLE[(s["base"]["row"], _side(s["base"]["col"]))]
        s.update({"role_off": off_role, "abbr": abbr, "role": role_name,
                  "run": s["dest"] != s["base"]})
    return {"name": name, "author": author, "slots": slots}


def list_tactics():
    d = tactics_dir()
    out = []
    if not os.path.isdir(d):
        return out
    for f in os.listdir(d):
        if not f.lower().endswith(".tac"):
            continue
        path = os.path.join(d, f)
        try:
            with open(path, "rb") as fh:
                t = parse(fh.read())
            out.append({"file": f, "name": t["name"], "author": t["author"], "mtime": os.path.getmtime(path)})
        except (OSError, TacticError, struct.error):
            continue
    out.sort(key=lambda x: -x["mtime"])
    return out


def read_tactic(file):
    if os.path.basename(file) != file or not file.lower().endswith(".tac"):
        raise TacticError("Nome file non valido")
    with open(os.path.join(tactics_dir(), file), "rb") as fh:
        return parse(fh.read())


# ----------------------------------------------------------------- punteggio per ruolo
# Media pesata degli attributi che contano nel ruolo (3 = fondamentale, 2 = importante, 1 = utile),
# sulla scala 1-20 del gioco. Pesi scelti a mano: sono un'indicazione, non la formula di FM.
_W = {
    "por": {"Riflessi": 3, "Uno contro uno": 3, "Bloccare tiri": 2, "Palle alte": 2, "Posizione": 2,
            "Autorità in area": 2, "Uscite": 2, "Agilità": 2, "Concentrazione": 2, "Comunicazione": 1,
            "Decisioni": 1, "Rinvii": 1, "Rilanci": 1},
    "dc": {"Marcatura": 3, "Contrasti": 3, "Colpo di testa": 3, "Posizione": 3, "Elevazione": 2, "Forza": 2,
           "Decisioni": 2, "Concentrazione": 2, "Coraggio": 1, "Velocità": 1, "Intuito": 1, "Freddezza": 1},
    "terzino": {"Marcatura": 2, "Contrasti": 2, "Posizione": 2, "Velocità": 2, "Accelerazione": 2,
                "Resistenza": 2, "Cross": 2, "Decisioni": 1, "Concentrazione": 1, "Dribbling": 1,
                "Gioco di squadra": 1, "Passaggi": 1},
    "esterno": {"Cross": 3, "Resistenza": 3, "Velocità": 2, "Accelerazione": 2, "Dribbling": 2, "Contrasti": 2,
                "Marcatura": 1, "Posizione": 1, "Gioco di squadra": 1, "Passaggi": 1, "Senza palla": 1, "Impegno": 1},
    "mediano": {"Contrasti": 3, "Posizione": 3, "Marcatura": 2, "Passaggi": 2, "Decisioni": 2, "Gioco di squadra": 2,
                "Intuito": 2, "Concentrazione": 2, "Resistenza": 2, "Impegno": 1, "Forza": 1, "Aggressività": 1},
    "cc": {"Passaggi": 3, "Decisioni": 2, "Gioco di squadra": 2, "Creatività": 2, "Tecnica": 2, "Resistenza": 2,
           "Intuito": 2, "Impegno": 1, "Senza palla": 1, "Tiri da lontano": 1, "Contrasti": 1, "Gioco di prima": 1},
    "laterale": {"Cross": 3, "Dribbling": 2, "Velocità": 2, "Accelerazione": 2, "Tecnica": 2, "Passaggi": 2,
                 "Resistenza": 2, "Senza palla": 1, "Creatività": 1, "Gioco di squadra": 1, "Impegno": 1},
    "ala": {"Dribbling": 3, "Cross": 2, "Velocità": 2, "Accelerazione": 2, "Tecnica": 2, "Fantasia": 2,
            "Senza palla": 2, "Creatività": 1, "Finalizzazione": 1, "Agilità": 1, "Gioco di prima": 1},
    "tc": {"Creatività": 3, "Passaggi": 3, "Tecnica": 2, "Fantasia": 2, "Dribbling": 2, "Gioco di prima": 2,
           "Decisioni": 2, "Senza palla": 1, "Tiri da lontano": 1, "Finalizzazione": 1, "Freddezza": 1},
    "punta": {"Finalizzazione": 3, "Senza palla": 3, "Freddezza": 2, "Colpo di testa": 2, "Accelerazione": 2,
              "Velocità": 2, "Tecnica": 1, "Dribbling": 1, "Gioco di prima": 1, "Forza": 1, "Decisioni": 1,
              "Elevazione": 1},
}
_ROLE_WEIGHTS = {0x1C: "por", 0x29: "dc", 0x28: "terzino", 0x2A: "terzino", 0x33: "esterno", 0x34: "esterno",
                 0x2B: "mediano", 0x2D: "cc", 0x2C: "laterale", 0x2E: "laterale", 0x2F: "ala", 0x31: "ala",
                 0x30: "tc", 0x32: "punta"}
_LEFT = {0x28, 0x33, 0x2C, 0x2F}   # nei ruoli di sinistra conta il piede sinistro
_RIGHT = {0x2A, 0x34, 0x2E, 0x31}  # e in quelli di destra il destro
ATTR_FIRST = 0x35                  # gli attributi arrivano come bytes del blocco da +0x35
_OFF = None


def role_score(attrs, role_off):
    """attrs = bytes del blocco attributi da +0x35 (valori 1-100) -> punteggio nel ruolo 1-20."""
    global _OFF
    if _OFF is None:
        from player import ATTRIBUTES
        _OFF = {name: off for _, name, off in ATTRIBUTES}
    w = dict(_W[_ROLE_WEIGHTS[role_off]])
    if role_off in _LEFT:
        w["Piede sinistro"] = 2
    elif role_off in _RIGHT:
        w["Piede destro"] = 2
    total = sum(w.values())
    s = sum(attrs[_OFF[name] - ATTR_FIRST] * k for name, k in w.items())
    return round(s / total / 5, 1)  # scala 1-100 -> 1-20
