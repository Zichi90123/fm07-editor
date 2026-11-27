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

Poi controllati su una partita vera (25/06/2006, 103.806 giocatori, 12.463 club) con `backend/verify.py`
e `tools/diag.py`, che cerca all'indietro chi punta a contratti, finanze e infortuni.

Legenda stato: ✅ certo (classe RTTI, getter identico o verificato sulla partita) · 🟡 dedotto (molto probabile) · ❓ da verificare.

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
| condizione u16 0-10000 | +0x08 | −0xCC | −0xE4 | ✅ partita (media 9476) |
| ritmo partita u16 | +0x0A | −0xCA | −0xE2 | ✅ partita |
| CA int16 | +0x14 | **−0xC0** | −0xD8 | ✅ getter, correlazione con gli attributi 0,92 |
| PA int16 | +0x16 | **−0xBE** | −0xD6 | ✅ partita (≥ CA nel 100%) |
| peso / altezza u16 | +0x1C / +0x1E | −0xB8 / −0xB6 | −0xD0 / −0xCE | 🟡 |
| valore int32 | +0x24 | −0xB0 | −0xC8 | ✅ getter |
| prezzo richiesto int32 | +0x28 | −0xAC | −0xC4 | 🟡 |
| stato (→ infortuni) ptr | +0x30 | −0xA4 | −0xBC | ✅ getter |
| morale byte | +0x48 | −0x8C | −0xA4 | ✅ getter |
| array FOG_DATA | +0xA8 | | (+0xBC) | ✅ costruttore |
| **blocco attributi** ptr | **+0xB4** | **−0x20** | −0x20 (+0xCC) | ✅ getter |
| array PLAYER_BOOKING_COUNT | +0xC0 | | (+0xD8) | ✅ costruttore |
| lista contratti | +0x16C | **+0x98** | +0xA0 (+0x18C) | ✅ partita (diag.py) |

Gli oggetti giocatore sono consecutivi ogni **0x1E4** byte (FM08: 0x37C).
Nelle rose ci sono anche oggetti di altre classi: VIRTUAL_PLAYER (`0x0134B4BC`) e
ACTUAL_PLAYER_AND_NON_PLAYER (`0x0136E024`, giocatori-allenatori, persona a +0x10C): l'editor li ignora.

Infortuni: stato = oggetto +0x30; nello stato **lista +0x08, numero +0x0C** (FM08: +0x10 / +0x14) ✅ partita
(19 infortunati su 3000). L'editor lo ricontrolla all'aggancio (`player.injury_layout`). Oggetto infortunio:
+0x10 u16 giorni stimati, +0x12 u16 durata totale (es. 98 / 128).

## Blocco attributi (PLAYING_DATA)

Un getter del gioco legge `attributi +0x6C` in FM08 e `+0x6B` in FM07: **il blocco è più corto di 1 byte**.
Ipotesi usata dall'editor: manca il byte "sconosciuto" di FM08 a +0x46 (tra Rilanci e Intuito), quindi:

- ruoli da +0x1C a +0x34: uguali a FM08;
- attributi da +0x35 a +0x45 (Cross … Rilanci): uguali a FM08;
- attributi da Intuito in poi: **offset FM08 − 1** (Intuito +0x46, …, Concentrazione +0x6A).

La conversione è in `player.py` (`ATTR_GAP`, funzione `fm07`). ✅ Verificato sulla partita: su 319
portieri gli 11 attributi da portiere sono esattamente agli offset previsti (0x40-0x45, 0x48, 0x4A, 0x54-0x56).

## Contratto (FULL_CONTRACT)

| Campo | FM08 | FM07 | Stato |
|---|---|---|---|
| club | +0x08 | +0x08 | 🟡 |
| stipendio settimanale | +0x10 | +0x10 | 🟡 |
| inizio / scadenza (data) | +0x18 / +0x20 | +0x18 / +0x20 | 🟡 |
| premio presenza | +0x48 | **+0x4C** | 🟡 getter spostato; sulla partita = 10% dello stipendio, come in FM08 |
| premio gol | +0x4C | **+0x50** | ❓ |
| premio porta inviolata? | +0x50 | **+0x58** (+0x54 è un campo nuovo) | ❓ |

Esempio sulla partita: stipendio 15.000, inizio 01/07/2005, scadenza 30/06/2009, +0x48 = 100,
+0x4C = 1.500, +0x50 = 375, +0x54 = 3.750, +0x58 = 0. I contratti da 45-50 a settimana (dilettanti)
non hanno scadenza.

## Club

Quasi lo stesso layout di FM08 (stessi membri con vtable fino a +0x130; da +0x140 in poi FM07 ha un
array in meno). Nome +0x28, colori +0x50, squadre +0x68, informazioni +0xE0…+0xFC 🟡.
Finanze **`*(club + 0x118)`** (FM08 +0x11C) ✅ partita: 300 finanze su 300, e le finanze puntano al club a +0x08.

## Squadra (TEAM)

| Campo | FM08 | FM07 | Stato |
|---|---|---|---|
| club | +0x38 | +0x38 | ✅ getter |
| prima squadra / limite d'età | +0x41 / +0x43 | +0x41 / +0x43 | 🟡 |
| reputazione u16 | +0x70 | **+0x6C** | ✅ partita: Milan 9650, Chelsea 9300, Juventus 7750, Lens 6900, Venezia 3500 |
| elenco giocatori (STEP_ARRAY) | +0xB0, ptr +0xB4, n +0xB8 | **+0x90, ptr +0x94, n +0x98** | ✅ costruttore |

## Finanze (CLUB_FINANCE)

| Campo | FM08 | FM07 | Stato |
|---|---|---|---|
| saldo | +0x04 | +0x04 | ✅ getter |
| fondo acquisti rimanente / stagione | +0x40 / +0x44 | **+0x30 / +0x34** | ✅ metodo che li aggiorna insieme |
| % entrate del mercato | +0x48 | **+0x38** | ✅ getter |
| budget ingaggi a settimana | +0xB8 | **+0xA8** | 🟡 plausibile sulla partita (20.145 contro spesa 12.562) |
| spesa ingaggi a settimana | +0xC0 | **+0xB0** | ✅ metodo che la aggiorna |
| finanziamento settore giovanile | +0xFC | — | non trovato |

## Allenatori umani

Persona di HUMAN_NON_PLAYER: nome +0x2C / cognome +0x30, lista contratti +0x98 (come i giocatori). ✅ partita

## Data del gioco

In FM08 è un oggetto data fisso (`0x019242F0`) letto tramite un oggetto globale, quindi non ritrovabile
staticamente. L'editor cerca gli oggetti SI_SHORT_DATE nella sezione `.data` di fm.exe
(`0x01586000`–`0x0190F000`) e prende la data più frequente. ✅ Sulla partita di prova sceglie il
25/06/2006, la data mostrata dal gioco. Candidati con quella data: `0x0161F7F8`, `0x016228D8`, `0x0162F7F4`:
quello che segue il gioco quando la data avanza diventerà `GAME_DATE` (clubs.py).

## Valuta

Non trovata. I candidati ricavati dal codice (indice `0x015FD5F8`, tabella `0x01843CEC`) non danno valori
credibili sulla partita, e i double 1,45 / 1,9 non compaiono nell'immagine di fm.exe. L'editor usa il
cambio impostato a mano nelle impostazioni (`CURRENCY_INDEX = None`). ❓

## Tattiche

Lette da `Documenti\Sports Interactive\Football Manager 2007\tactics` con il lettore del formato FM08:
non ancora verificato sui file di FM07 (i file non riconosciuti vengono saltati). ❓

## Da verificare

Con il gioco aperto, `python backend/verify.py` controlla tutte le voci ❓ e 🟡. In ordine di importanza:

Tutte le letture risultano OK sulla partita di prova (verify.py del 26/11/2026) e l'editor è stato
provato in gioco con esito positivo (27/11/2026). Restano da confrontare con le schermate del gioco:

1. premi gol / porta inviolata del contratto e budget ingaggi;
2. indirizzo fisso della data di gioco e valuta.
