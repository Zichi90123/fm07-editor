# Mappa della memoria di FM2007 (7.0.2)

Appunti sulle strutture di `fm.exe` 7.0.2 (`C:\Program Files (x86)\Sports Interactive\Football Manager 2007`).
Gli indirizzi d'esempio cambiano a ogni avvio; le **vtable** (indirizzi dentro fm.exe) e gli **offset** no.

La mappa completa di FM2008, da cui questa deriva, è in
[fm08-editor/MAPPA.md](https://github.com/Zichi90123/fm08-editor/blob/main/MAPPA.md): qui ci sono solo
le differenze e da dove vengono.

## Come è stata ricavata

Senza avviare il gioco, confrontando gli eseguibili di FM07 e FM08:

1. **RTTI**: fm.exe contiene i nomi delle classi C++ (`.?AVCLUB@@`, `.?AVACTUAL_PLAYER@@`…) e, per ogni
   vtable, il "Complete Object Locator" con classe e offset del sotto-oggetto. Ogni vtable usata da
   fm08-editor ha quindi un nome, e la vtable di FM07 con lo stesso nome e offset è la corrispondente
   (`tools/rtti.py`).
2. **Getter**: i metodi brevi delle vtable (`mov eax,[ecx+0x24]; ret`) sono nello stesso ordine nelle
   due versioni: confrontandoli si vede quali campi hanno cambiato offset.
3. **Costruttori**: le istruzioni che scrivono vtable di membri (`mov [esi+0xB0], vtable`) danno gli
   offset degli array interni (rose delle squadre, ecc.).
4. **Indirizzi statici**: il codice attorno ai riferimenti di FM08, con gli indirizzi mascherati,
   cercato in FM07.

Legenda stato: ✅ certo (stessa classe RTTI o getter identico) · 🟡 dedotto (molto probabile) · ❓ da verificare.

## Vtable

| Classe (RTTI) | Uso | FM08 | FM07 | Stato |
|---|---|---|---|---|
| ACTUAL_PLAYER (sotto-oggetto persona) | persona giocatore | `0x015AB12C` (+0xEC) | **`0x0133E96C`** (+0xD4) | ✅ |
| ACTUAL_PLAYER | oggetto giocatore | `0x015AB414` | `0x0133EC44` | ✅ |
| PLAYING_DATA | blocco attributi | `0x01547AA4` | **`0x012F2754`** | ✅ |
| PERSON_NAME | oggetto nome | `0x0150FF24` | `0x012C523C` | ✅ |
| NATION | nazione | `0x015AA73C` | `0x0133FAE4` | ✅ |
| CLUB | club | `0x015996C4` | **`0x0133ADAC`** | ✅ |
| CLUB_FINANCE | finanze | `0x015994B4` | **`0x0133ABD4`** | ✅ |
| TEAM | squadra | `0x015A9E0C` | **`0x01339A4C`** | ✅ |
| STEP_ARRAY&lt;PLAYER*&gt; | rosa della squadra | `0x015A9B58` | `0x01339890` | ✅ |
| HUMAN_NON_PLAYER (sotto-oggetto persona) | allenatore umano | `0x015AE024` (+0x29C) | `0x01348384` (+0x25C) | ✅ |
| FULL_CONTRACT | contratto | `0x012A7F74` | **`0x010A434C`** | ✅ |
| LOAN_CONTRACT | prestito | `0x0154CF9C` | `0x012F7174` | ✅ |
| PLAYER_INJURY | infortunio | `0x0129ACC4` | `0x01097EDC` | ✅ |
| SI_SHORT_DATE | data | `0x0154E4C0` | `0x013D1794` | ✅ |
| STRING (rif. a stringa) | nomi club/nazioni | `0x0166A398`, `0x0166A38C` | `0x013D26B8`, `0x013D26AC` | ✅ |

## Oggetto giocatore (ACTUAL_PLAYER)

La persona sta a **+0xD4** (FM08: +0xEC). I campi all'inizio dell'oggetto hanno gli **stessi offset
dall'inizio dell'oggetto** (getter identici: +0x0E, +0x10, +0x12, +0x14, +0x24, +0x2C, +0x30, +0x40,
+0x44, +0x48, +0x49, +0x4A), quindi dalla persona sono spostati di +0x18.

| Campo | Oggetto | Dalla persona FM07 | Dalla persona FM08 | Stato |
|---|---|---|---|---|
| condizione u16 0-10000 | +0x08 | −0xCC | −0xE4 | 🟡 |
| ritmo partita u16 | +0x0A | −0xCA | −0xE2 | 🟡 |
| CA int16 | +0x14 | **−0xC0** | −0xD8 | ✅ getter |
| PA int16 | +0x16 | **−0xBE** | −0xD6 | 🟡 |
| peso / altezza u16 | +0x1C / +0x1E | −0xB8 / −0xB6 | −0xD0 / −0xCE | 🟡 |
| valore int32 | +0x24 | −0xB0 | −0xC8 | ✅ getter |
| prezzo richiesto int32 | +0x28 | −0xAC | −0xC4 | 🟡 |
| stato (→ infortuni) ptr | +0x30 | −0xA4 | −0xBC | ✅ getter |
| morale byte | +0x48 | −0x8C | −0xA4 | ✅ getter |
| array FOG_DATA | +0xA8 | | (+0xBC) | ✅ costruttore |
| **blocco attributi** ptr | **+0xB4** | **−0x20** | −0x20 (+0xCC) | ✅ getter |
| array PLAYER_BOOKING_COUNT | +0xC0 | | (+0xD8) | ✅ costruttore |
| lista contratti | +0x174 | **+0xA0** | +0xA0 (+0x18C) | 🟡 come gli allenatori |

## Blocco attributi (PLAYING_DATA)

Un getter del gioco legge `attributi +0x6C` in FM08 e `+0x6B` in FM07: **il blocco è più corto di 1 byte**.
Ipotesi usata dall'editor: manca il byte "sconosciuto" di FM08 a +0x46 (tra Rilanci e Intuito), quindi:

- ruoli da +0x1C a +0x34: uguali a FM08;
- attributi da +0x35 a +0x45 (Cross … Rilanci): uguali a FM08;
- attributi da Intuito in poi: **offset FM08 − 1** (Intuito +0x46, …, Concentrazione +0x6A).

La conversione è in `player.py` (`ATTR_GAP`, funzione `fm07`): se `verify.py` mostra che il byte mancante
è un altro, basta cambiare `ATTR_GAP`. ❓

## Contratto (FULL_CONTRACT)

| Campo | FM08 | FM07 | Stato |
|---|---|---|---|
| club | +0x08 | +0x08 | 🟡 |
| stipendio settimanale | +0x10 | +0x10 | 🟡 |
| inizio / scadenza (data) | +0x18 / +0x20 | +0x18 / +0x20 | 🟡 |
| premio presenza | +0x48 | **+0x4C** | 🟡 getter spostato |
| premio gol | +0x4C | **+0x50** | 🟡 |
| premio porta inviolata? | +0x50 | **+0x58** (+0x54 è un campo nuovo) | ❓ |

## Club

Stesso layout di FM08 almeno fino a +0x130 (stessi membri e stessi offset nel costruttore; da +0x140
in poi FM07 ha un array in meno). Nome +0x28, colori +0x50, squadre +0x68, informazioni +0xE0…+0xFC,
finanze `*(club + 0x11C)`. 🟡

## Squadra (TEAM)

| Campo | FM08 | FM07 | Stato |
|---|---|---|---|
| club | +0x38 | +0x38 | ✅ getter |
| prima squadra / limite d'età | +0x41 / +0x43 | +0x41 / +0x43 | 🟡 |
| reputazione u16 | +0x70 | +0x70 | ❓ |
| elenco giocatori (STEP_ARRAY) | +0xB0, ptr +0xB4, n +0xB8 | **+0x90, ptr +0x94, n +0x98** | ✅ costruttore |

## Finanze (CLUB_FINANCE)

| Campo | FM08 | FM07 | Stato |
|---|---|---|---|
| saldo | +0x04 | +0x04 | ✅ getter |
| fondo acquisti rimanente / stagione | +0x40 / +0x44 | **+0x30 / +0x34** | ✅ metodo che li aggiorna insieme |
| % entrate del mercato | +0x48 | **+0x38** | ✅ getter |
| budget ingaggi a settimana | +0xB8 | **+0xA8** | ❓ stesso spostamento (−0x10) dei campi vicini |
| spesa ingaggi a settimana | +0xC0 | **+0xB0** | ✅ metodo che la aggiorna |
| finanziamento settore giovanile | +0xFC | — | non trovato |

## Allenatori umani

Persona di HUMAN_NON_PLAYER: nome +0x2C / cognome +0x30, lista contratti +0xA0 (come FM08). 🟡

## Data del gioco

In FM08 è un oggetto data fisso (`0x019242F0`) letto tramite un oggetto globale, quindi non ritrovabile
staticamente. L'editor cerca gli oggetti SI_SHORT_DATE nella sezione `.data` di fm.exe
(`0x01586000`–`0x0190F000`) e prende la data più frequente. `verify.py` elenca i candidati: quando si
conosce l'indirizzo giusto va messo in `GAME_DATE` (clubs.py). ❓

## Valuta

Indice della valuta scelta `0x015FD5F8`, tabella delle valute `0x01843CEC` (FM08: `0x018FAE88`,
`0x01B227CC`), trovati confrontando il codice che li usa. Se i valori letti non sono credibili l'editor
usa il cambio impostato a mano nelle impostazioni. ❓

## Tattiche

Lette da `Documenti\Sports Interactive\Football Manager 2007\tactics` con il lettore del formato FM08:
non ancora verificato sui file di FM07 (i file non riconosciuti vengono saltati). ❓

## Da verificare

Con il gioco aperto, `python backend/verify.py` controlla tutte le voci ❓ e 🟡. In ordine di importanza:

1. layout del blocco attributi (`ATTR_GAP`);
2. lista contratti a persona +0xA0;
3. budget ingaggi +0xA8, reputazione squadra +0x70, premi del contratto;
4. data di gioco e valuta;
5. scrittura: provare una modifica per tipo (attributo, condizione, saldo) e controllarla nel gioco.
