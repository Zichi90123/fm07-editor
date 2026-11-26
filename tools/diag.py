"""Diagnosi delle voci che verify.py segna come sbagliate: cerca gli offset giusti sulla partita vera.

Con FM2007 aperto (terminale come amministratore se il gioco lo è):
    python tools\\diag.py > %USERPROFILE%\\Desktop\\diagnosi.txt
Legge soltanto. Ci mette qualche minuto (più passate su tutta la memoria).
"""
import bisect
import collections
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import clubs  # noqa: E402
import people  # noqa: E402
import player  # noqa: E402
from memory import Process  # noqa: E402
from people import PageCache, find_dword, read_name  # noqa: E402

STEP_ARRAY_PLAYER = 0x01339890


def pointers_to(proc, targets):
    """{target: [indirizzi che lo contengono]} con una sola passata sulla memoria."""
    targets = sorted(set(int(t) for t in targets if t))
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


def near(sorted_objs, loc, before=0x300, after=0x400):
    """Offset di loc dall'oggetto più vicino (oggetto <= loc + before), o None."""
    i = bisect.bisect_right(sorted_objs, loc + before) - 1
    if i < 0:
        return None
    d = loc - sorted_objs[i]
    return d if -before <= d <= after else None


def hist(title, c, n=8):
    print(f"   {title}: " + (", ".join(f"{k:+#x} x{v}" if isinstance(k, int) else f"{k} x{v}"
                                    for k, v in c.most_common(n)) or "nessuno"))


def u32s(cache, addr, n):
    return struct.unpack(f"<{n}I", cache.read(addr, n * 4))


def main():
    proc = Process.attach("fm.exe")
    cache = PageCache(proc)
    persons = sorted(find_dword(proc, people.PERSON_VTABLE))
    humans = sorted(find_dword(proc, clubs.HUMAN_VTABLE))
    club_set = set(find_dword(proc, clubs.CLUB_VTABLE))
    print(f"persone {len(persons)}, allenatori umani {len(humans)}, club {len(club_set)}")

    # ------------------------------------------------------------- contratti
    print("\n== CONTRATTI (FULL_CONTRACT)")
    contracts = find_dword(proc, player.CONTRACT_VTABLE)
    sample = contracts[:: max(1, len(contracts) // 400)][:400]
    c08 = collections.Counter()
    for c in sample:
        for off in range(0x04, 0x40, 4):
            if cache.u32(cache.u32(c + off)) == clubs.CLUB_VTABLE if cache.u32(c + off) else False:
                c08[off] += 1
    hist("offset nel contratto che punta a un CLUB", c08)
    print("   primo contratto, dword 0x00-0x7C: " + " ".join(f"{v:08x}" for v in u32s(cache, sample[0], 32)))
    lvl1 = pointers_to(proc, sample)
    direct = collections.Counter()
    starts = set()
    for c, locs in lvl1.items():
        for loc in locs:
            d = near(persons, loc)
            if d is not None:
                direct[d] += 1
            starts.add(loc)  # possibile inizio di un array di contratti
    hist("puntatore DIRETTO al contratto, offset dalla persona", direct)
    lvl2 = pointers_to(proc, starts)
    via = collections.Counter()
    via_h = collections.Counter()
    for a, locs in lvl2.items():
        for loc in locs:
            d = near(persons, loc)
            if d is not None:
                via[d] += 1
            h = near(humans, loc)
            if h is not None:
                via_h[h] += 1
    hist("puntatore all'ARRAY di contratti, offset dalla persona", via)
    hist("puntatore all'ARRAY di contratti, offset dall'allenatore umano", via_h)

    # ------------------------------------------------------------- finanze
    print("\n== FINANZE (CLUB_FINANCE)")
    fins = find_dword(proc, clubs.FINANCE_VTABLE)
    fc = collections.Counter()
    for f in fins[:300]:
        for off in range(0x04, 0x40, 4):
            v = cache.u32(f + off)
            if v in club_set:
                fc[off] += 1
    hist("offset nelle finanze che punta al club", fc)
    back = pointers_to(proc, fins[:300])
    cc = collections.Counter()
    for f, locs in back.items():
        for loc in locs:
            for cl in (loc - o for o in range(0, 0x400, 4)):
                if cl in club_set:
                    cc[loc - cl] += 1
                    break
    hist("offset nel club che punta alle finanze", cc)
    if fins:
        f = fins[0]
        print("   prime finanze, dword 0x00-0xFC (con segno): " +
              " ".join(str(struct.unpack('<i', cache.read(f + o, 4))[0]) for o in range(0, 0x100, 4)))

    # ------------------------------------------------------------- squadre
    print("\n== SQUADRE (TEAM)")
    teams = find_dword(proc, clubs.TEAM_VTABLE)
    so = collections.Counter()
    for t in teams[:2000]:
        for off in range(0x40, 0x140, 4):
            if cache.u32(t + off) == STEP_ARRAY_PLAYER:
                so[off] += 1
    hist("offset del vtable STEP_ARRAY<PLAYER> nella squadra", so)
    bad_vt = collections.Counter()
    bad = 0
    for t in teams[:3000]:
        lst, n = cache.u32(t + clubs.TEAM_PLAYERS_PTR), cache.u32(t + clubs.TEAM_PLAYERS_COUNT)
        if not lst or not 0 < n <= 200 or cache.u32(cache.u32(t + clubs.TEAM_CLUB)) != clubs.CLUB_VTABLE:
            continue
        objs = u32s(cache, lst, n)
        if all(o and cache.u32(o + clubs.PLAYER_OBJECT_TO_PERSON) == people.PERSON_VTABLE for o in objs):
            continue
        bad += 1
        for o in objs:
            if o and cache.u32(o + clubs.PLAYER_OBJECT_TO_PERSON) != people.PERSON_VTABLE:
                bad_vt[f"{cache.u32(o):#010x}"] += 1
    print(f"   squadre con elementi non giocatori: {bad}")
    hist("vtable degli elementi estranei", bad_vt)

    # reputazione: campi u16 della squadra plausibili (0-10000) con i valori delle prime squadre dei big
    big = {}
    for cl in club_set:
        nm = clubs._name(cache, cl)
        if nm in ("Juventus", "Milan", "Inter", "Chelsea", "Real Madrid", "Barcellona", "Venezia", "Lens"):
            big[nm] = cl
    print("   squadre dei club noti: campi u16 da +0x40 a +0x8E (prima squadra)")
    for nm, cl in sorted(big.items()):
        for t, kind, _ in clubs.club_teams(cache, cl):
            if kind == "first":
                vals = struct.unpack("<40H", cache.read(t + 0x40, 80))
                print(f"     {nm:12} " + " ".join(f"{0x40 + 2 * i:02x}:{v}" for i, v in enumerate(vals)))
    if not big:
        print("     nessun club noto trovato per nome")

    # ------------------------------------------------------------- infortuni
    print("\n== INFORTUNI (PLAYER_INJURY)")
    injs = find_dword(proc, player.INJURY_VTABLE)[:200]
    if injs:
        print("   primo infortunio, dword 0x00-0x2C: " + " ".join(f"{v:08x}" for v in u32s(cache, injs[0], 12)))
    l1 = pointers_to(proc, injs)
    arr_starts = {loc - 4 * k for locs in l1.values() for loc in locs for k in range(4)}
    l2 = pointers_to(proc, arr_starts)
    holders = set()
    for a, locs in l2.items():
        for loc in locs:
            holders.update(loc - o for o in range(0, 0x30, 4))  # inizio dell'oggetto "stato"
    l3 = pointers_to(proc, holders)
    ic = collections.Counter()
    for h, locs in l3.items():
        for loc in locs:
            d = near(persons, loc)
            if d is not None:
                # offset dell'array dentro lo stato = (indirizzo array) - h: lo ricaviamo da l2
                ic[d] += 1
    hist("offset dalla persona del puntatore allo stato (catena persona->stato->lista->infortunio)", ic)
    direct_i = collections.Counter()
    for locs in l1.values():
        for loc in locs:
            d = near(persons, loc)
            if d is not None:
                direct_i[d] += 1
    for locs in l2.values():
        for loc in locs:
            d = near(persons, loc)
            if d is not None:
                direct_i[f"lista {d:+#x}"] += 1
    hist("riferimenti agli infortuni vicini a una persona", direct_i)
    for p in persons[:: max(1, len(persons) // 20000)]:
        st = cache.u32(p + player.OFF_PLAYER_OBJECT + player.PLAYER_STATUS)
        if st and 0 < cache.u32(st + player.STATUS_INJURY_COUNT) <= 8:
            print(f"   esempio stato +0x14>0: {read_name(cache, cache.u32(p + 0x30))}, "
                  f"stato dword: " + " ".join(f"{v:08x}" for v in u32s(cache, st, 8)))
            break

    # ------------------------------------------------------------- valuta
    print("\n== VALUTA")
    lo, hi = 0x00401000, 0x0191F000
    found = collections.defaultdict(list)
    for base, size in proc.regions(writable_only=False):
        s, e = max(base, lo), min(base + size, hi)
        if s >= e:
            continue
        data = proc.read(s, e - s)
        if data is None:
            continue
        for rate in (1.45, 1.9):
            pat = struct.pack("<d", rate)
            i = data.find(pat)
            while i >= 0:
                found[rate].append(s + i)
                i = data.find(pat, i + 1)
    for rate, locs in found.items():
        print(f"   double {rate} in fm.exe: " + " ".join(f"{a:#x}" for a in locs[:30]))


if __name__ == "__main__":
    main()
