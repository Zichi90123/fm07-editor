# FM07 Live Editor

Editor in tempo reale per Football Manager 2007 (versione 7.0.2), in stile FMRTE.
Costruito sulla base di [fm08-editor](https://github.com/Zichi90123/fm08-editor): stesso backend Python
(lettura/scrittura memoria con `ctypes` + `numpy`) e stessa interfaccia Electron.

> **Stato: provato in gioco.** La mappa della memoria di FM07 è stata ricavata dall'eseguibile
> (`fm.exe` 7.0.2) confrontandolo con quello di FM08 e poi verificata su una partita vera: letture e
> modifiche funzionano. Fai comunque sempre un backup del salvataggio prima di modificare.

## Download (per usarlo e basta)

1. Vai su **[Releases](https://github.com/Zichi90123/fm07-editor/releases/latest)** e scarica `FM07-Live-Editor-x.y.z.exe`.
2. Apri Football Manager 2007 (7.0.2) e carica la partita.
3. Fai doppio clic sull'exe scaricato. Non serve installare niente: Python ed Electron sono già inclusi.

Windows potrebbe mostrare "Windows ha protetto il PC" perché l'exe non è firmato: clicca
**Ulteriori informazioni → Esegui comunque**. Se il gioco è avviato come amministratore, avvia anche
l'editor come amministratore (tasto destro → Esegui come amministratore).

## Avvio dai sorgenti (sviluppatori)

### Requisiti

- Windows 10/11
- Python 3.9 o superiore (spunta "Add Python to PATH" durante l'installazione)
- Node.js 18 o superiore
- Football Manager 2007 aggiornato alla 7.0.2

### Avvio

1. Apri FM2007 e carica la partita.
2. Fai doppio clic su `avvia.bat`. La prima volta installa numpy ed Electron (ci vuole qualche minuto).
3. Nell'editor premi **Aggancia fm.exe**.

Se il gioco è avviato come amministratore, avvia anche `avvia.bat` come amministratore
(tasto destro → Esegui come amministratore), altrimenti Windows nega l'accesso alla memoria.

Il backend usa la porta **47810** (fm08-editor usa la 47808, scudetto0102-editor la 47809): gli editor
possono stare aperti insieme. Per cambiare l'eseguibile Python imposta `FM07_PYTHON`, per la porta `FM07_PORT`.

### Verifica della mappa

Con FM2007 aperto e una partita caricata:

```
cd backend
python verify.py > verifica.txt
```

Controlla vtable, offset e valori su qualche migliaio di giocatori e club, senza scrivere nulla.
Le voci `[NO]` o `[??]` dicono cosa correggere (vedi [MAPPA.md](MAPPA.md), sezione "Da verificare").

### Creare l'exe

`build.bat` crea l'exe portatile in `app\dist\`. Per pubblicare una nuova versione su GitHub:
aggiorna `version` in `app/package.json`, poi `git tag v0.2.0 && git push origin v0.2.0`: il workflow
`.github/workflows/release.yml` compila l'exe e lo allega alla release.

## Cosa fa

Le stesse funzioni di fm08-editor:

- **Giocatori**: elenco con filtri (nome, club, ruolo, CA minima, infortunati) e scheda modificabile:
  attributi, CA/PA, condizione, morale, infortuni (*Guarisci*), ruoli, contratto, valore.
- **Club**: informazioni (reputazione, fondazione, stato, strutture, spettatori, colori), **finanze** e rosa.
- **Tattica**: disegna una tattica salvata e suggerisce formazione e acquisti
  (il formato dei file `.tac` di FM07 non è ancora verificato).
- **Impostazioni** (⚙): valuta mostrata dal gioco, strumenti avanzati.
- **Avanzate**: scanner, ricerche in memoria, indirizzi salvati, visore esadecimale, analisi statistica
  ("Trova CA e PA") per correggere la mappa se serve.

Differenze rispetto a FM08: niente "finanziamento settore giovanile" (non trovato in FM07);
la data di gioco viene cercata a ogni aggancio invece di stare a un indirizzo fisso.

## Struttura

```
backend/
  memory.py    accesso al processo (OpenProcess, ReadProcessMemory, VirtualQueryEx…)
  people.py    persone (vtable), nomi, date
  player.py    attributi, CA/PA, ruoli, stato, infortuni, contratto, elenco giocatori
  clubs.py     club, squadre, finanze, data di gioco, valuta
  verify.py    controllo della mappa su una partita vera
  scanner.py   motore di scansione vettorizzato con numpy
  search.py    ricerche in memoria (stringhe, puntatori, valori, rapporti)
  analysis.py  analisi statistica (usata per trovare CA/PA)
  tactics.py   lettura dei file .tac
  server.py    API HTTP su 127.0.0.1:47810 per la GUI
app/
  main.js      avvia il backend Python e apre la finestra
  preload.js   ponte sicuro tra finestra e backend
  renderer/    interfaccia: ui.js (giocatori, club), tools.js (strumenti avanzati), common.js
```

Fai sempre un backup del salvataggio prima di modificare.
