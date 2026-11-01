"""Gestione dei copioni: creazione, elenco, eliminazione e pulizia delle clip audio.

Le clip stanno solo in cache/ (nome = hash del contenuto); ogni copione in
web/opere/<nome>/ contiene solo il manifest (opera.json), il testo e il cast.
Quando un copione viene eliminato, le clip che nessun altro copione usa
vengono cancellate per non occupare spazio.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unicodedata
from pathlib import Path

from copione import parse
from pdf2txt import converti
from tts import ClipCache

ROOT = Path(__file__).resolve().parent.parent
OPERE_DIR = ROOT / "web" / "opere"
CACHE_DIR = ROOT / "cache"
MAX_COPIONI = int(os.environ.get("IMBECCATA_MAX_COPIONI", "3"))
MAX_BYTES = 8 * 1024 * 1024
VOCI_IT = ["if_sara", "im_nicola"]
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,48}$")

# Una sola generazione alla volta; protegge anche la pulizia della cache.
lock = threading.Lock()
# Condivisa: il modello Kokoro viene caricato una volta sola.
_cache = ClipCache(CACHE_DIR)


class ErroreCopione(Exception):
    def __init__(self, messaggio: str, codice: int = 400):
        super().__init__(messaggio)
        self.codice = codice


def slugify(testo: str) -> str:
    s = unicodedata.normalize("NFKD", testo).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9_]+", "-", s.lower()).strip("-_")[:40].strip("-_")
    return s or "copione"


def _leggi(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def elenca() -> list[dict]:
    out = []
    for p in sorted(OPERE_DIR.glob("*/opera.json")):
        o = _leggi(p)
        clip = {r["audio"] for r in o["righe"] if r.get("audio")}
        byte = sum((CACHE_DIR / f).stat().st_size for f in clip if (CACHE_DIR / f).exists())
        out.append({
            "nome": p.parent.name,
            "titolo": o.get("titolo") or p.parent.name,
            "personaggi": o["personaggi"],
            "battute": sum(1 for r in o["righe"] if r["tipo"] == "battuta"),
            "mb": round(byte / 1e6, 1),
        })
    return out


def da_file(nome_file: str, dati: bytes) -> tuple[str, dict]:
    """Da un file caricato (.txt o .pdf) ricava (testo nel formato del progetto, copione parsato)."""
    if len(dati) > MAX_BYTES:
        raise ErroreCopione(f"File troppo grande (massimo {MAX_BYTES // 2**20} MB).", 413)

    if nome_file.lower().endswith(".pdf") or dati[:5] == b"%PDF-":
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(dati)
            tmp.flush()
            try:
                res = subprocess.run(["pdftotext", "-layout", tmp.name, "-"],
                                     capture_output=True, check=True, timeout=60)
            except FileNotFoundError:
                raise ErroreCopione("Per leggere i PDF serve pdftotext (poppler): brew install poppler.", 500)
            except Exception:
                raise ErroreCopione("Non riesco a leggere questo PDF.")
        try:
            testo = converti(res.stdout.decode("utf-8", "replace"))
        except Exception:
            raise ErroreCopione(
                "Il PDF non ha l'impaginazione prevista (sezione PERSONAGGI e battute "
                "'NOME testo'). Prova con un file .txt nel formato indicato nell'aiuto."
            )
    else:
        for enc in ("utf-8-sig", "cp1252"):
            try:
                testo = dati.decode(enc)
                break
            except UnicodeDecodeError:
                continue

    opera = parse(testo)
    if not any(r["tipo"] == "battuta" and r["testo_tts"] for r in opera["righe"]):
        raise ErroreCopione("Non ho trovato battute. Ogni battuta deve iniziare con NOME: (vedi l'aiuto).")
    if len(opera["personaggi"]) < 2:
        raise ErroreCopione("Servono almeno due personaggi.")
    if not opera["titolo"]:
        opera["titolo"] = Path(nome_file).stem
    return testo, opera


def n_clip(opera: dict) -> int:
    return sum(1 for r in opera["righe"] if r["tipo"] == "battuta" and r["testo_tts"])


def cast_default(opera: dict) -> dict:
    # in ordine di prima apparizione, così chi dialoga di seguito ha voci diverse
    ordine = []
    for r in opera["righe"]:
        for p in r.get("parlanti") or []:
            if p not in ordine:
                ordine.append(p)
    speeds = [1.0, 0.92, 1.08, 0.97]
    return {
        p: {"engine": "kokoro", "voce": VOCI_IT[i % 2], "speed": speeds[(i // 2) % len(speeds)]}
        for i, p in enumerate(ordine)
    }


def genera(nome: str, testo: str, opera: dict, cast: dict | None = None, progresso=None) -> dict:
    """Genera le clip e scrive il copione in web/opere/<nome>/. Ritorna il cast usato."""
    if not SLUG_RE.match(nome):
        raise ErroreCopione("Nome non valido.")
    with lock:
        dest = OPERE_DIR / nome
        if not (dest / "opera.json").exists() and len(elenca()) >= MAX_COPIONI:
            raise ErroreCopione(f"Hai già {MAX_COPIONI} copioni: eliminane uno per aggiungerne un altro.", 409)
        cast = cast or cast_default(opera)
        mancanti = [p for p in opera["personaggi"] if p not in cast]
        if mancanti:
            raise ErroreCopione(f"Personaggi senza voce nel cast: {mancanti}")

        righe = [r for r in opera["righe"] if r["tipo"] == "battuta" and r["testo_tts"]]
        for i, r in enumerate(righe, 1):
            c = cast[r["personaggio"]]
            r["audio"], r["durata"] = _cache.get(
                c["engine"], r["testo_tts"], c["voce"], {"speed": c.get("speed", 1.0)}
            )
            r["durata"] = round(r["durata"], 2)
            if progresso:
                progresso(i, len(righe))

        dest.mkdir(parents=True, exist_ok=True)
        (dest / "copione.txt").write_text(testo, encoding="utf-8")
        (dest / "cast.json").write_text(json.dumps(cast, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp = dest / "opera.json.tmp"
        tmp.write_text(json.dumps(opera, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(dest / "opera.json")
        _pulisci_locked()
    return cast


def elimina(nome: str) -> None:
    if not SLUG_RE.match(nome):
        raise ErroreCopione("Nome non valido.")
    dest = OPERE_DIR / nome
    if not (dest / "opera.json").exists():
        raise ErroreCopione("Copione non trovato.", 404)
    shutil.rmtree(dest)
    # Se è in corso una generazione la pulizia verrà fatta alla sua fine.
    if lock.acquire(blocking=False):
        try:
            _pulisci_locked()
        finally:
            lock.release()


def pulisci() -> None:
    with lock:
        _pulisci_locked()


def _pulisci_locked() -> None:
    """Cancella clip non usate, cartelle incomplete e residui del vecchio formato."""
    OPERE_DIR.mkdir(parents=True, exist_ok=True)
    (OPERE_DIR / "index.json").unlink(missing_ok=True)
    usati = set()
    for d in OPERE_DIR.iterdir():
        if not d.is_dir():
            continue
        if not (d / "opera.json").exists():
            shutil.rmtree(d, ignore_errors=True)
            continue
        shutil.rmtree(d / "audio", ignore_errors=True)  # vecchio formato: le clip stanno in cache/
        usati |= {r["audio"] for r in _leggi(d / "opera.json")["righe"] if r.get("audio")}
    for f in CACHE_DIR.glob("*.wav"):
        if f.name not in usati:
            f.unlink()
