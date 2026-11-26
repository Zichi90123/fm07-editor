"""Elenco delle persone (giocatori, staff…) di FM2007 7.0.2.

Le persone si trovano cercando la loro vtable: fm.exe non è rilocabile,
quindi l'indirizzo della vtable è sempre lo stesso. Offset in MAPPA.md.
Le vtable di FM07 sono state ricavate dalle informazioni RTTI dell'eseguibile
(stesse classi di FM08: ACTUAL_PLAYER, CLUB, TEAM…).
"""
import datetime
import struct

import numpy as np

# ACTUAL_PLAYER, sotto-oggetto "persona" (a +0xD4 nell'oggetto giocatore; in FM08 era a +0xEC)
PERSON_VTABLE = 0x0133E96C
OFF_FIRST_NAME = 0x2C
OFF_LAST_NAME = 0x30
OFF_COMMON_NAME = 0x34
OFF_BIRTH = 0x48

# Il puntatore al blocco attributi sta 0x20 byte PRIMA della persona
# (oggetto giocatore +0xB4, dal getter del gioco; l'oggetto inizia a persona - 0xD4).
OFF_ATTR_PTR = -0x20
ATTR_BLOCK_SIZE = 0x80

NAME_OBJ_RECORD = 0x24   # oggetto nome -> record della lista dei nomi
NAME_RECORD_STRING = 0x08  # record -> stringa UTF-16


class PageCache:
    """Legge la memoria a pagine da 64 KB e le tiene in cache: i nomi sono
    raggruppati in poche zone, quindi bastano poche letture vere."""

    PAGE = 0x10000

    def __init__(self, proc):
        self.proc = proc
        self.pages = {}

    def _page(self, n):
        if n not in self.pages:
            data = self.proc.read(n * self.PAGE, self.PAGE)
            if data is None:
                # la pagina da 64 KB può superare la fine della regione: proviamo a 4 KB
                parts = []
                for i in range(self.PAGE // 0x1000):
                    parts.append(self.proc.read(n * self.PAGE + i * 0x1000, 0x1000) or b"\0" * 0x1000)
                data = b"".join(parts)
            self.pages[n] = data
        return self.pages[n]

    def read(self, addr, size):
        out = b""
        while size > 0:
            n, off = divmod(addr, self.PAGE)
            chunk = self._page(n)[off:off + size]
            out += chunk
            addr += len(chunk)
            size -= len(chunk)
        return out

    def u32(self, addr):
        if not addr:
            return 0
        return struct.unpack("<I", self.read(addr, 4))[0]


def find_dword(proc, value, limit=None):
    """Tutti gli indirizzi (allineati a 4) che contengono `value`."""
    out = []
    for base, size in proc.regions():
        data = proc.read(base, size)
        if data is None:
            continue
        arr = np.frombuffer(data, dtype="<u4", count=len(data) // 4)
        for i in np.nonzero(arr == value)[0]:
            out.append(base + int(i) * 4)
            if limit and len(out) >= limit:
                return out
    return out


def read_name(cache, name_obj):
    if not name_obj:
        return ""
    try:
        rec = cache.u32(name_obj + NAME_OBJ_RECORD)
        s = cache.u32(rec + NAME_RECORD_STRING)
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


def read_date(cache, addr):
    day, year = struct.unpack("<HH", cache.read(addr, 4))
    if year <= 1900 or year > 2200 or day > 365:
        return None
    try:
        return (datetime.date(year, 1, 1) + datetime.timedelta(days=day)).isoformat()
    except ValueError:
        return None


def list_people(proc):
    cache = PageCache(proc)
    out = []
    for addr in find_dword(proc, PERSON_VTABLE):
        first = read_name(cache, cache.u32(addr + OFF_FIRST_NAME))
        last = read_name(cache, cache.u32(addr + OFF_LAST_NAME))
        common = read_name(cache, cache.u32(addr + OFF_COMMON_NAME))
        if not (first or last or common):
            continue
        out.append({
            "address": f"0x{addr:08X}",
            "first": first,
            "last": last,
            "common": common,
            "birth": read_date(cache, addr + OFF_BIRTH),
        })
    return out


def read_attr_block(proc, person):
    """Legge il blocco attributi grezzo di una persona (valori 1-100)."""
    cache = PageCache(proc)
    ptr = cache.u32(person + OFF_ATTR_PTR)
    if not ptr:
        return None, None
    data = proc.read(ptr, ATTR_BLOCK_SIZE)
    return ptr, data
