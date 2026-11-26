"""Controllo della mappa di FM2007 su una partita vera.

Gli indirizzi e gli offset di FM07 sono stati ricavati dall'eseguibile (RTTI e confronto
dei metodi con FM08), senza il gioco avviato. Questo script li controlla uno per uno:
apri FM2007 7.0.2, carica una partita e lancia

    python verify.py            (oppure: python verify.py > verifica.txt)

Per ogni voce stampa OK / ?? / NO con i numeri che servono a correggere la mappa.
Non scrive niente nella memoria del gioco.
"""
import collections
import struct
import sys

import numpy as np

import clubs
import people
import player
from memory import Process
from people import PageCache, find_dword

SAMPLE = 3000


def say(ok, title, detail=""):
    mark = {True: "OK", False: "NO", None: "??"}[ok]
    print(f"[{mark}] {title}")
    if detail:
        for line in str(detail).splitlines():
            print(f"       {line}")


def frac(x):
    return f"{100 * x:.1f}%"


def main():
    proc = Process.attach("fm.exe")
    mod = proc.module_base("fm.exe")
    say(mod is not None and mod[0] == 0x400000, "fm.exe agganciato",
        f"base {mod[0]:#x}, dimensione {mod[1]:#x}" if mod else "modulo non trovato")
    cache = PageCache(proc)

    # ------------------------------------------------------------------ vtable
    counts = {}
    for name, vt in [("persona giocatore (ACTUAL_PLAYER)", people.PERSON_VTABLE),
                     ("blocco attributi (PLAYING_DATA)", player.ATTR_BLOCK_VTABLE),
                     ("club (CLUB)", clubs.CLUB_VTABLE),
                     ("squadra (TEAM)", clubs.TEAM_VTABLE),
                     ("finanze (CLUB_FINANCE)", clubs.FINANCE_VTABLE),
                     ("nazione (NATION)", player.NATION_VTABLE),
                     ("contratto (FULL_CONTRACT)", player.CONTRACT_VTABLE),
                     ("prestito (LOAN_CONTRACT)", player.LOAN_VTABLE),
                     ("infortunio (PLAYER_INJURY)", player.INJURY_VTABLE),
                     ("allenatore umano (HUMAN_NON_PLAYER)", clubs.HUMAN_VTABLE)]:
        n = len(find_dword(proc, vt))
        counts[name] = n
        say(n > 0 if "infortunio" not in name and "prestito" not in name else None,
            f"vtable {vt:#010x} {name}: {n} oggetti")

    persons = find_dword(proc, people.PERSON_VTABLE)
    step = max(1, len(persons) // SAMPLE)
    sample = persons[::step][:SAMPLE]

    # ------------------------------------------------- persona: nomi e blocco attributi
    named = sum(1 for p in sample[:300] if people.read_name(cache, cache.u32(p + people.OFF_LAST_NAME)))
    say(named > 250, "nomi delle persone (+0x2C/+0x30)", f"{named}/300 con cognome leggibile")
    ex = [p for p in sample[:20]]
    print("       esempi: " + ", ".join(
        f"{people.read_name(cache, cache.u32(p + people.OFF_FIRST_NAME))} "
        f"{people.read_name(cache, cache.u32(p + people.OFF_LAST_NAME))} ({people.read_date(cache, p + people.OFF_BIRTH)})"
        for p in ex[:5]))

    players = []
    for p in sample:
        b = cache.u32(p + people.OFF_ATTR_PTR)
        if b and cache.u32(b) == player.ATTR_BLOCK_VTABLE:
            players.append((p, b))
    say(len(players) > 0.5 * len(sample), "puntatore al blocco attributi (persona -0x20)",
        f"{len(players)}/{len(sample)} persone del campione hanno un blocco PLAYING_DATA")
    if not players:
        print("Senza giocatori non si può continuare.")
        return

    blocks = np.array([np.frombuffer(cache.read(b, 0x70), dtype=np.uint8) for _, b in players])
    mx = blocks.max(axis=0)
    roles_end = next((o for o in range(0x1C, 0x70) if mx[o] > 20), None)
    say(roles_end == player.ATTR_FIRST, "fine dei ruoli / inizio attributi nel blocco",
        f"primo byte con valori > 20: {roles_end:#x} (atteso {player.ATTR_FIRST:#x})" if roles_end else "nessuno")
    print("       massimo per offset 0x14-0x6F: " + " ".join(f"{o:02x}:{mx[o]}" for o in range(0x14, 0x70)))

    gk = blocks[:, 0x1C] >= 15
    if gk.sum() >= 20 and (~gk).sum() >= 20:
        diff = blocks[gk].mean(axis=0) - blocks[~gk].mean(axis=0)
        strong = [o for o in range(player.ATTR_FIRST, player.ATTR_LAST + 1) if diff[o] > 20]
        expected = sorted(off for g, _, off in player.ATTRIBUTES if g == "Portiere")
        say(set(expected) <= set(strong) | {o for o in expected if diff[o] > 10},
            "layout attributi (portieri contro giocatori di movimento)",
            f"portieri nel campione: {int(gk.sum())}\n"
            f"offset molto più alti nei portieri: {' '.join(f'{o:#x}' for o in strong)}\n"
            f"attributi da portiere secondo la mappa (ATTR_GAP={player.ATTR_GAP:#x}): "
            f"{' '.join(f'{o:#x}' for o in expected)}\n"
            "Se non coincidono, il byte mancante non è ATTR_GAP: guarda dove inizia lo spostamento.")
        print("       differenza media portieri - altri: " +
              " ".join(f"{o:02x}:{diff[o]:+.0f}" for o in range(player.ATTR_FIRST, player.ATTR_LAST + 2)))
    else:
        say(None, "layout attributi", "troppo pochi portieri nel campione")

    # ----------------------------------------------------- campi dell'oggetto giocatore
    def field(off, fmt):
        size = struct.calcsize(fmt)
        return np.array([struct.unpack(fmt, cache.read(p + off, size))[0] for p, _ in players])

    ca, pa = field(player.OFF_CA, "<h"), field(player.OFF_PA, "<h")
    ok_ca = ((ca >= 1) & (ca <= 200)).mean()
    ok_pa = (((pa >= ca) & (pa <= 200)) | ((pa >= -10) & (pa <= -1))).mean()
    attr_mean = blocks[:, player.ATTR_FIRST:player.ATTR_LAST + 1].mean(axis=1)
    corr = float(np.corrcoef(ca, attr_mean)[0, 1]) if ca.std() else 0
    say(ok_ca > 0.97 and ok_pa > 0.95, f"CA / PA (persona {player.OFF_CA:#x} / {player.OFF_PA:#x})",
        f"CA tra 1 e 200: {frac(ok_ca)}, PA >= CA o a intervallo: {frac(ok_pa)}, "
        f"correlazione CA-media attributi: {corr:.2f} (FM08: 0,87)")

    cond, fit = field(player.OFF_CONDITION, "<H"), field(player.OFF_FITNESS, "<H")
    say((cond <= 10000).mean() > 0.99 and cond.mean() > 3000, f"condizione (persona {player.OFF_CONDITION:#x})",
        f"0-10000: {frac((cond <= 10000).mean())}, media {cond.mean():.0f}")
    say((fit <= 10000).mean() > 0.99, f"ritmo partita (persona {player.OFF_FITNESS:#x})",
        f"0-10000: {frac((fit <= 10000).mean())}, media {fit.mean():.0f}")
    mor = field(player.OFF_MORALE, "<B")
    say((mor <= 20).mean() > 0.99, f"morale (persona {player.OFF_MORALE:#x})",
        f"0-20: {frac((mor <= 20).mean())}, valori: {dict(sorted(collections.Counter(mor.tolist()).items()))}")
    val = field(player.MARKET_FIELDS[0][2], "<i")
    ask = field(player.MARKET_FIELDS[1][2], "<i")
    say((val >= 0).mean() > 0.99 and float(np.corrcoef(val, ca)[0, 1]) > 0.4,
        "valore (persona %#x)" % player.MARKET_FIELDS[0][2],
        f">= 0: {frac((val >= 0).mean())}, correlazione con CA: {np.corrcoef(val, ca)[0, 1]:.2f} (FM08: ~0,7), "
        f"prezzo richiesto -1: {int((ask == -1).sum())}, 0: {int((ask == 0).sum())}")

    # --------------------------------------------------------------- contratti
    def contract_at(p, off):
        lst = cache.u32(p + off)
        c = cache.u32(lst) if lst else 0
        return c if c and cache.u32(c) == player.CONTRACT_VTABLE else 0

    sub = players[:500]
    hits = sum(1 for p, _ in sub if contract_at(p, player.OFF_PLAYER_OBJECT + player.PLAYER_CONTRACT_LIST))
    say(hits > 0.7 * len(sub), "lista contratti (persona +0xA0)", f"{hits}/{len(sub)} giocatori con contratto")
    if hits < 0.7 * len(sub):
        best = collections.Counter()
        for p, _ in sub[:150]:
            for off in range(player.OBJ, 0x200, 4):
                if contract_at(p, off):
                    best[off] += 1
        print("       offset alternativi (dalla persona): " +
              ", ".join(f"{o:+#x}:{n}" for o, n in best.most_common(5)))
    wages = []
    for p, _ in sub:
        c = contract_at(p, player.OFF_PLAYER_OBJECT + player.PLAYER_CONTRACT_LIST)
        if c:
            raw = cache.read(c, player.CONTRACT_READ)
            wages.append([struct.unpack_from("<i", raw, off)[0] if k != "date" else
                          player._date_read(raw[off:off + 4]) for _, _, off, k in player.CONTRACT_FIELDS])
    if wages:
        print("       primi contratti (stipendio, inizio, scadenza, premi): ")
        for w in wages[:6]:
            print("         ", w)

    inj = sum(1 for p, _ in players if player.injuries(proc, p))
    say(None, "infortuni", f"{inj} giocatori infortunati nel campione (controlla che siano plausibili)")

    # ------------------------------------------------------------- squadre e club
    teams = find_dword(proc, clubs.TEAM_VTABLE)
    good = total = 0
    reps = []
    for t in teams[:3000]:
        club = cache.u32(t + clubs.TEAM_CLUB)
        if not club or cache.u32(club) != clubs.CLUB_VTABLE:
            continue
        reps.append(struct.unpack("<H", cache.read(t + clubs.TEAM_REPUTATION, 2))[0])
        lst, n = cache.u32(t + clubs.TEAM_PLAYERS_PTR), cache.u32(t + clubs.TEAM_PLAYERS_COUNT)
        if lst and 0 < n <= 200:
            total += 1
            objs = struct.unpack(f"<{n}I", cache.read(lst, n * 4))
            if all(o and cache.u32(o + clubs.PLAYER_OBJECT_TO_PERSON) == people.PERSON_VTABLE for o in objs):
                good += 1
    say(total > 0 and good > 0.9 * total, "rose delle squadre (squadra +0x94/+0x98)",
        f"{good}/{total} squadre con elenco giocatori valido")
    reps = np.array(reps) if reps else np.array([0])
    say((reps <= 10000).mean() > 0.99 and reps.max() > 5000, "reputazione squadra (+0x70)",
        f"0-10000: {frac((reps <= 10000).mean())}, massimo {reps.max()}, media {reps.mean():.0f}")

    club_list = clubs.list_clubs(proc)
    say(len(club_list) > 100, "nomi dei club", f"{len(club_list)} club, es. " +
        ", ".join(c["name"] for c in club_list[:6]))
    fin_ok = 0
    shown = 0
    for c in club_list:
        try:
            f = clubs.read_finances(proc, int(c["address"], 16))
        except clubs.ClubError:
            continue
        fin_ok += 1
        if shown < 4 and f["fields"][0]["value"] != 0:
            shown += 1
            print(f"       {c['name']}: " + ", ".join(f"{x['key']}={x['value']}" for x in f["fields"]))
    say(fin_ok > 0, "oggetti finanze (club +0x11C)", f"{fin_ok} club con finanze. Confronta le cifre sopra "
        "con la schermata Finanze del gioco (divise per il cambio della valuta)")
    info = 0
    for c in club_list[:2000]:
        try:
            i = clubs.read_info(proc, int(c["address"], 16))
        except clubs.ClubError:
            continue
        v = {x["key"]: x["value"] for x in i["fields"]}
        if 1850 <= v["founded"] <= 2010 and 1 <= v["status"] <= 3:
            info += 1
    say(info > 0.5 * min(len(club_list), 2000), "informazioni club (fondazione +0xE2, stato +0xEA)",
        f"{info} club con valori plausibili")

    hum = clubs.human_clubs(proc)
    say(bool(hum), "squadre allenate dall'utente", ", ".join(f"{h['manager']} -> {h['name']}" for h in hum))

    # ------------------------------------------------------------ data e valuta
    cands = clubs.game_date_candidates(proc)
    cnt = collections.Counter(cands.values())
    say(bool(cands), "data di gioco (oggetti data in fm.exe)",
        f"scelta: {clubs.game_date(proc)}; date più frequenti: " +
        ", ".join(f"{d} x{n}" for d, n in cnt.most_common(5)) +
        "\nSe la data giusta compare a un indirizzo solo, segnalo: diventa GAME_DATE.\n" +
        "Indirizzi: " + ", ".join(f"{a:#x}={d}" for a, d in list(cands.items())[:12]))
    cur = clubs.currency(proc)
    say(cur is not None, "valuta del gioco (indice e tabella)", str(cur) if cur else
        "non leggibile: l'editor userà il cambio impostato a mano")


if __name__ == "__main__":
    try:
        main()
    except (LookupError, PermissionError) as e:
        print(e)
        sys.exit(1)
