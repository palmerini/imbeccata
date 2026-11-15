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

Dal pulsante **Copioni…** del player l'utente carica un file `.txt`, `.pdf` o `.fountain`, vede
l'avanzamento della generazione audio ed elimina i copioni che non gli servono più.
Non c'è nessun login: l'app è pensata per un attore che carica il copione di volta in volta.

- **Limite**: al massimo 3 copioni insieme, per limitare lo spazio su disco
  (modificabile con la variabile d'ambiente `IMBECCATA_MAX_COPIONI`).
- Il pulsante **Voci** di ogni copione permette di scegliere, per ogni personaggio, la voce e la
  velocità (con un pulsante ▶ per ascoltare una prova). Applicando si rigenerano solo le battute
  dei personaggi modificati.
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
./avvia.sh            # avvia il server e apre http://localhost:8766 (porta opzionale: ./avvia.sh 9000)
```

Se l'app è già in esecuzione, lo script apre solo il browser. `NO_BROWSER=1 ./avvia.sh` non apre il browser.
Al primo avvio, se manca `.venv`, lo script propone di crearlo e di installare le dipendenze
(servono alcuni GB di spazio). Equivale a lanciare a mano `.venv/bin/python -I src/server.py`.

Da riga di comando (stessa logica e stesso limite del pannello):

```bash
.venv/bin/python -I src/build.py testi/esempio.txt   # accetta .txt, .pdf o .fountain
```

Per convertire un copione PDF nel formato del progetto, senza generare audio:

```bash
.venv/bin/python -I src/pdf2txt.py copione.pdf testi/copione.txt
```

Il convertitore riconosce da solo due impaginazioni (vedi i commenti in `src/pdf2txt.py`):

1. battute del tipo `NOME <spazio zero-width> testo`, con righe rientrate di continuazione;
2. battute `NOME: testo` (o `NOME (didascalia)` su una riga e testo sotto), con didascalie come
   paragrafi liberi e righe lunghe spezzate senza rientro. Qui la separazione fra parlato e
   didascalie si basa su euristiche: conviene rileggere il `.txt` generato e correggerlo a mano
   (ad esempio un discorso in più paragrafi separati da righe vuote può essere scambiato per
   didascalie). Per usare la versione corretta, carica il `.txt` invece del PDF.

Per altri impaginati il convertitore va adattato, oppure si scrive direttamente il testo nel formato sotto.

I copioni in formato [Fountain](https://fountain.io) (`.fountain`) si caricano come i `.txt`; per
convertirli senza generare audio:

```bash
.venv/bin/python -I src/fountain2txt.py copione.fountain testi/copione.txt
```

Le battute sono i nomi in maiuscolo (`NOME`, anche `A E B` per le battute corali), le didascalie sono
i paragrafi di azione, `.SCENA ...` è una scena (unita alla sezione `# ATTO ...` che la precede).
Un paragrafo staccato da una riga vuota dalla battuta precedente è una didascalia anche se è la
continuazione di un discorso: se serve, correggi il `.txt` generato.

## Formato del testo

```
# Titolo
## Scena 1
(Didascalia su una riga)
PERSONAGGIO: battuta, anche (con didascalia inline) che non viene letta.
    Righe rientrate = continuazione della battuta.
```

### Testo letto dal TTS

Prima della sintesi (`src/normalizza.py`) il testo di ogni battuta viene normalizzato: numeri,
ordinali e percentuali in lettere (`1977`, `39º`, `78%`), nomi dei personaggi in maiuscolo in forma
normale (`OLIVIERO` -> `Oliviero`), apostrofi e virgolette tipografiche semplificati, puntini di
sospensione ridotti a `...` (mai a inizio battuta), trattini usati come incisi resi con virgole.
A schermo il testo resta quello scritto. Le parole urlate in maiuscolo che non sono nomi restano
com'erano. Se cambia una regola, le battute modificate hanno una nuova chiave di cache e vengono
rigenerate.

## Cast

Ogni copione ha un `cast.json` (in `web/opere/<nome>/`) che assegna a ogni personaggio
motore, voce e velocità. Con il caricamento dal player viene creato in automatico, alternando
le due voci italiane di Kokoro (`if_sara` femminile, `im_nicola` maschile) senza conoscere il
genere dei personaggi: si corregge dal pulsante **Voci**. Da riga di comando si può passare
un cast scritto a mano (`testi/<nome>.cast.json`, vedi `testi/esempio.cast.json`).

## Pubblicazione online (sola lettura)

Per mettere online un copione **già generato**, senza server e senza possibilità di generare
nuovi audio, si esporta un sito statico e lo si pubblica su Cloudflare (Workers con asset statici).
Il sito esportato contiene solo il player, il testo del copione e le clip MP3; non ha il pannello
Copioni né Voci. Il sito è in `dist/` (ignorato da git: contiene l'audio dei copioni reali).

1. **Esporta** (serve `ffmpeg`; le clip diventano MP3 mono a 96 kbps, circa un quarto del peso dei WAV; `--bitrate 64k` per file più piccoli):

   ```bash
   .venv/bin/python -I src/esporta.py nome_copione      # senza nome esporta tutti i copioni
   ```

   Ogni clip viene anche portata allo stesso volume medio del parlato (default -20 dBFS, con un picco
   massimo di -1,5 dBFS), così i personaggi hanno volumi simili e l'MP3 non satura: si cambia con
   `--livello -22` o si disattiva con `--senza-livellamento`. Solo all'esportazione, la cache resta
   com'è. I nomi dei file MP3 contengono una sigla delle impostazioni (bitrate e livello): il sito li
   serve con cache "immutable", e così cambiando le impostazioni i browser scaricano i file nuovi.

   Per un copione di circa 320 battute: 327 file, circa 31 MB a 96 kbps, 21 MB a 64 kbps (il limite di Cloudflare è
   20.000 file, 25 MiB ciascuno). Prova in locale: `python3 -m http.server 8767 --directory dist`.

2. **Pubblica** (serve Node; il primo comando apre il browser per autorizzare il tuo account Cloudflare):

   ```bash
   npx wrangler login
   npx wrangler deploy
   ```

   Il sito risponde su `https://imbeccata.<tuo-sottodominio>.workers.dev` (configurazione in `wrangler.jsonc`).

3. **Proteggilo subito con Cloudflare Access**, perché il sito non ha un login suo e fino a
   quel momento è raggiungibile da chiunque conosca l'indirizzo. Dal pannello Cloudflare:
   Workers & Pages → `imbeccata` → Settings → Domains & Routes → `workers.dev` → abilita
   Cloudflare Access (includendo anche i preview URL). Poi in Zero Trust → Access → Applications
   apri l'applicazione creata e imposta una policy *Allow* con regola *Emails* e l'elenco degli
   invitati; come metodo di accesso basta *One-time PIN* (codice via email, gratis fino a 50 utenti).
   I nomi dei menu possono cambiare.

4. **Invitare qualcuno** = aggiungere la sua email alla policy. **Aggiornare il copione** = rifare
   i passi 1 e 2.

## Licenza

Codice sotto licenza Apache 2.0 (vedi `LICENSE`). Il modello Kokoro e le sue voci
hanno licenze proprie: controllale prima di distribuire l'audio generato.

## Da fare

- Riconoscimento vocale per la pausa dell'attore.
- Motori TTS aggiuntivi / a pagamento.
- App mobile e pacchetti audio offline.
