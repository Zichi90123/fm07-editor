"""Scanner di memoria in stile Cheat Engine, vettorizzato con numpy.

Funziona con qualunque oggetto che offra regions(), read(addr, size)
e read_value(addr, type): così si può testare anche fuori da Windows.
"""
import numpy as np

DTYPES = {
    "byte": "<u1",
    "int16": "<i2",
    "int32": "<i4",
    "int64": "<i8",
    "float": "<f4",
    "double": "<f8",
}

FIRST_CONDS = {"exact", "between", "greater", "less", "unknown"}
NEXT_CONDS = {"exact", "between", "greater", "less", "changed", "unchanged",
              "increased", "decreased", "increased_by", "decreased_by", "ratio"}

# "ratio": il valore è cambiato nella stessa proporzione di un numero mostrato dal gioco
# (vecchio -> nuovo). Funziona anche se il gioco converte i valori (es. valute).
RATIO_TOL = 2e-5

# Oltre questo numero di risultati non si legge il valore corrente di ciascuno
LIST_LIMIT = 500


class ScanError(Exception):
    pass


def _views(buf, dt, aligned):
    """Restituisce [(offset_iniziale, array)] per i vari allineamenti."""
    size = dt.itemsize
    starts = [0] if aligned else range(size)
    out = []
    for r in starts:
        count = (len(buf) - r) // size
        if count > 0:
            out.append((r, np.frombuffer(buf, dtype=dt, count=count, offset=r)))
    return out


def _in_range(dt, v):
    if dt.kind in "iu":
        info = np.iinfo(dt)
        return info.min <= v <= info.max
    return True


def _match(arr, prev, cond, v, v2, dt):
    is_float = dt.kind == "f"
    tol = 0.5 if is_float else 0
    with np.errstate(all="ignore"):
        if cond == "exact":
            if is_float:
                return np.abs(arr - v) <= tol
            if not _in_range(dt, v):
                return np.zeros(arr.shape, bool)
            return arr == v
        if cond == "between":
            lo, hi = min(v, v2), max(v, v2)
            if is_float:
                return (arr >= lo) & (arr <= hi)
            a = arr.astype(np.int64)
            return (a >= lo) & (a <= hi)
        if cond == "greater":
            return arr.astype(np.float64) > v
        if cond == "less":
            return arr.astype(np.float64) < v
        # condizioni relative al valore precedente
        if prev is None:
            raise ScanError("Serve una scansione precedente")
        if is_float:
            a, p = arr.astype(np.float64), prev.astype(np.float64)
            same = (a == p) | (np.isnan(a) & np.isnan(p))
        else:
            a, p = arr.astype(np.int64), prev.astype(np.int64)
            same = a == p
        if cond == "changed":
            return ~same
        if cond == "unchanged":
            return same
        if cond == "increased":
            return a > p
        if cond == "decreased":
            return a < p
        if cond == "increased_by":
            return np.abs((a - p) - v) <= tol
        if cond == "decreased_by":
            return np.abs((p - a) - v) <= tol
        if cond == "ratio":
            if not v or v2 is None:
                raise ScanError("Inserisci il valore vecchio e quello nuovo mostrati dal gioco")
            r = float(v2) / float(v)
            af, pf = a.astype(np.float64), p.astype(np.float64)
            ok = (pf != 0) & (np.abs(pf) >= 1000)  # esclude i numeri piccoli: troppo rumore
            with np.errstate(divide="ignore", invalid="ignore"):
                ok &= np.abs(af / np.where(pf == 0, 1, pf) - r) <= RATIO_TOL * abs(r)
            if r != 1:
                ok &= af != pf
            return ok
    raise ScanError(f"Condizione sconosciuta: {cond}")


def _to_number(x, dt):
    if x is None or x == "":
        return None
    return float(x) if dt.kind == "f" else int(float(x))


class Scanner:
    def __init__(self):
        self.reset()

    def reset(self):
        self.vtype = None
        self.dt = None
        self.aligned = True
        self.snapshot = None  # [(base, bytes)] per la scansione "valore sconosciuto"
        self.results = None   # [(base, size, offsets int64, valori ora, valori alla scansione prima)]
        self.scans = 0

    # --- stato --------------------------------------------------------------
    def count(self):
        if self.snapshot is not None:
            return sum(len(b) // self.dt.itemsize for _, b in self.snapshot) * (1 if self.aligned else self.dt.itemsize)
        if self.results is None:
            return 0
        return int(sum(len(r[2]) for r in self.results))

    def info(self):
        return {
            "active": self.scans > 0,
            "type": self.vtype,
            "aligned": self.aligned,
            "scans": self.scans,
            "count": self.count(),
            "unknown": self.snapshot is not None,
        }

    # --- scansioni ----------------------------------------------------------
    def first_scan(self, proc, vtype, cond, value=None, value2=None, aligned=True):
        if vtype not in DTYPES:
            raise ScanError(f"Tipo non valido: {vtype}")
        if cond not in FIRST_CONDS:
            raise ScanError(f"Condizione non valida per la prima scansione: {cond}")
        self.reset()
        self.vtype, self.dt, self.aligned = vtype, np.dtype(DTYPES[vtype]), bool(aligned)
        v, v2 = _to_number(value, self.dt), _to_number(value2, self.dt)
        if cond != "unknown" and v is None:
            raise ScanError("Inserisci un valore")
        if cond == "between" and v2 is None:
            raise ScanError("Inserisci entrambi i valori dell'intervallo")

        if cond == "unknown":
            snap = []
            for base, size in proc.regions():
                buf = proc.read(base, size)
                if buf is not None:
                    snap.append((base, buf))
            self.snapshot = snap
        else:
            results = []
            for base, size in proc.regions():
                buf = proc.read(base, size)
                if buf is None:
                    continue
                offs, vals = [], []
                for r, arr in _views(buf, self.dt, self.aligned):
                    idx = np.nonzero(_match(arr, None, cond, v, v2, self.dt))[0]
                    if idx.size:
                        offs.append(idx.astype(np.int64) * self.dt.itemsize + r)
                        vals.append(arr[idx].copy())
                if offs:
                    vals = np.concatenate(vals)
                    results.append((base, size, np.concatenate(offs), vals, vals))
            self.results = results
        self.scans = 1
        return self.info()

    def next_scan(self, proc, cond, value=None, value2=None):
        if self.scans == 0:
            raise ScanError("Fai prima una prima scansione")
        if cond not in NEXT_CONDS:
            raise ScanError(f"Condizione non valida: {cond}")
        dt = self.dt
        v, v2 = _to_number(value, dt), _to_number(value2, dt)
        if cond in {"exact", "between", "greater", "less", "increased_by", "decreased_by", "ratio"} and v is None:
            raise ScanError("Inserisci un valore")
        if cond in ("between", "ratio") and v2 is None:
            raise ScanError("Inserisci entrambi i valori dell'intervallo")

        results = []
        if self.snapshot is not None:
            for base, old in self.snapshot:
                new = proc.read(base, len(old))
                if new is None:
                    continue
                old_views = dict(_views(old, dt, self.aligned))
                offs, vals, before = [], [], []
                for r, arr in _views(new, dt, self.aligned):
                    idx = np.nonzero(_match(arr, old_views[r], cond, v, v2, dt))[0]
                    if idx.size:
                        offs.append(idx.astype(np.int64) * dt.itemsize + r)
                        vals.append(arr[idx].copy())
                        before.append(old_views[r][idx].copy())
                if offs:
                    results.append((base, len(old), np.concatenate(offs), np.concatenate(vals),
                                    np.concatenate(before)))
            self.snapshot = None
        else:
            for base, size, offs, prev, _ in self.results:
                new = proc.read(base, size)
                if new is None:
                    continue
                cur = self._gather(new, offs)
                keep = _match(cur, prev, cond, v, v2, dt)
                if keep.any():
                    # "prima" = il valore alla scansione precedente, per vedere di quanto è cambiato
                    results.append((base, size, offs[keep], cur[keep], prev[keep]))
        self.results = results
        self.scans += 1
        return self.info()

    def _gather(self, buf, offs):
        dt = self.dt
        size = dt.itemsize
        out = np.empty(len(offs), dtype=dt)
        rem = offs % size
        for r in np.unique(rem):
            r = int(r)
            sel = rem == r
            arr = np.frombuffer(buf, dtype=dt, count=(len(buf) - r) // size, offset=r)
            out[sel] = arr[(offs[sel] - r) // size]
        return out

    def addresses(self):
        """Tutti gli indirizzi dei risultati, nello stesso ordine della lista."""
        if self.results is None:
            return []
        return [base + int(off) for base, _, offs, _, _ in self.results for off in offs]

    def list_results(self, proc, limit=200):
        if self.results is None:
            return []
        out = []
        for base, _, offs, _, prev in self.results:
            for off, pv in zip(offs, prev):
                if len(out) >= min(limit, LIST_LIMIT):
                    return out
                addr = base + int(off)
                cur = proc.read_value(addr, self.vtype)
                out.append({"n": len(out) + 1, "address": f"0x{addr:08X}", "value": cur, "previous": pv.item()})
        return out
