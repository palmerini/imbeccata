# Imbeccata

Prototipo per imparare a memoria le battute di un testo teatrale: l'app legge
con voce sintetica tutti i personaggi tranne quello dell'attore, che parla nei vuoti.

## Come funziona

1. `src/copione.py` legge il testo e lo divide in battute (formato sotto).
2. `src/tts.py` genera una clip audio per battuta (Kokoro, open source) e la salva in `cache/`.
   La chiave di cache è `hash(motore + versione + voce + parametri + testo)`:
   una battuta già generata non viene mai rigenerata, e cambiare motore non invalida le altre.
3. `src/build.py` costruisce il pacchetto in `web/opere/<nome>/` (manifest + clip).
4. `web/index.html` è il player: scegli opera e personaggio, le altre battute vengono
   riprodotte e sulle tue c'è una pausa (tap o automatica).

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
.venv/bin/python -I src/build.py testi/esempio.txt   # genera audio e pacchetto
python3 -m http.server 8766 --directory web          # poi apri http://localhost:8766
```

Per convertire un copione PDF nel formato del progetto:

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

`testi/<nome>.cast.json` assegna a ogni personaggio motore, voce e velocità.
Se manca viene creato in automatico: controlla i generi delle voci
(Kokoro in italiano ha solo `if_sara` femminile e `im_nicola` maschile).

## Licenza

Codice sotto licenza Apache 2.0 (vedi `LICENSE`). Il modello Kokoro e le sue voci
hanno licenze proprie: controllale prima di distribuire l'audio generato.

## Da fare

- Provare i PDF reali (richiedono la conversione in questo formato).
- Riconoscimento vocale per la pausa dell'attore.
- Motori TTS aggiuntivi / a pagamento.
- App mobile e pacchetti audio offline.
