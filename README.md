# Imbeccata

Prototipo per imparare a memoria le battute di un testo teatrale: l'app legge
con voce sintetica tutti i personaggi tranne quello dell'attore, che parla nei vuoti.

## Come funziona

1. `src/copione.py` legge il testo e lo divide in battute (formato sotto).
2. `src/tts.py` genera una clip audio per battuta (Kokoro, open source) e la salva in `cache/`.
   La chiave di cache è `hash(motore + versione + voce + parametri + testo)`:
   una battuta già generata non viene mai rigenerata, e cambiare motore non invalida le altre.
3. `src/libreria.py` gestisce i copioni: crea (`web/opere/<nome>/` con manifest, testo e cast),
   elenca, elimina e ripulisce le clip non più usate. Le clip stanno solo in `cache/`.
4. `src/server.py` è il server locale: serve il player e le API per aggiungere/eliminare copioni.
5. `web/index.html` è il player: scegli opera e personaggio, le altre battute vengono
   riprodotte e sulle tue c'è una pausa (tap o automatica).

## Gestire i copioni

Dal pulsante **Copioni…** del player l'utente carica un file `.txt` o `.pdf`, vede
l'avanzamento della generazione audio ed elimina i copioni che non gli servono più.
Non c'è nessun login: l'app è pensata per un attore che carica il copione di volta in volta.

- **Limite**: al massimo 3 copioni insieme, per limitare lo spazio su disco
  (modificabile con la variabile d'ambiente `IMBECCATA_MAX_COPIONI`).
- Eliminando un copione si cancellano anche le sue clip audio, a meno che le usi un altro copione.
- Il nome del copione è quello del file; se ne esiste già uno con lo stesso nome va eliminato prima.
- Il server ascolta solo su `127.0.0.1`.

Per aggiungere un motore (anche a pagamento) basta una classe in `tts.py`
con `id`, `version` e `synthesize()`, registrata in `ENGINES`, e indicarla nel file cast.

## Installazione

Serve Python 3.12 (con Python 3.13+ alcune dipendenze di Kokoro possono non avere pacchetti pronti)
e `pdftotext` (poppler) solo se vuoi convertire copioni in PDF.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Al primo avvio Kokoro scarica il modello (circa 300 MB) da Hugging Face.

## Uso

```bash
.venv/bin/python -I src/server.py     # poi apri http://localhost:8766 (porta opzionale: src/server.py 9000)
```

Da riga di comando (stessa logica e stesso limite del pannello):

```bash
.venv/bin/python -I src/build.py testi/esempio.txt   # accetta .txt o .pdf
```

Per convertire un copione PDF nel formato del progetto, senza generare audio:

```bash
.venv/bin/python -I src/pdf2txt.py copione.pdf testi/copione.txt
```

Il convertitore si aspetta un PDF con sezione PERSONAGGI e battute del tipo
`NOME <spazio zero-width> testo` (vedi i commenti in `src/pdf2txt.py`).
Per altri impaginati va adattato, oppure si scrive direttamente il testo nel formato sotto.

## Formato del testo

```
# Titolo
## Scena 1
(Didascalia su una riga)
PERSONAGGIO: battuta, anche (con didascalia inline) che non viene letta.
    Righe rientrate = continuazione della battuta.
```

## Cast

Ogni copione ha un `cast.json` (in `web/opere/<nome>/`) che assegna a ogni personaggio
motore, voce e velocità. Con il caricamento dal player viene creato in automatico, alternando
le due voci italiane di Kokoro (`if_sara` femminile, `im_nicola` maschile) senza conoscere il
genere dei personaggi. Da riga di comando si può passare un cast scritto a mano
(`testi/<nome>.cast.json`, vedi `testi/esempio.cast.json`).

## Licenza

Codice sotto licenza Apache 2.0 (vedi `LICENSE`). Il modello Kokoro e le sue voci
hanno licenze proprie: controllale prima di distribuire l'audio generato.

## Da fare

- Scelta delle voci per personaggio dal player (ora è automatica).
- Riconoscimento vocale per la pausa dell'attore.
- Motori TTS aggiuntivi / a pagamento.
- App mobile e pacchetti audio offline.
