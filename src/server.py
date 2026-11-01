"""Server locale di Imbeccata: serve il player e le API per gestire i copioni.

Uso:
    python -I src/server.py [porta]      # default 8766, solo su 127.0.0.1

API:
    GET    /api/opere          -> {max, opere: [...], in_corso}
    POST   /api/opere          -> corpo = file .txt/.pdf, header X-Nome = nome del file (url-encoded)
    GET    /api/jobs/<id>      -> avanzamento della generazione audio
    DELETE /api/opere/<nome>   -> elimina il copione e le clip non più usate
    GET    /audio/<hash>.wav   -> clip audio (da cache/, con supporto Range per Safari)
"""
import json
import re
import sys
import threading
import traceback
import urllib.parse
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import libreria as lib  # noqa: E402
from libreria import ErroreCopione  # noqa: E402

WEB = lib.ROOT / "web"
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
corrente: str | None = None  # id del job in corso


def job_in_corso() -> dict | None:
    if corrente and JOBS[corrente]["stato"] == "in_corso":
        return {"job": corrente, **JOBS[corrente]}
    return None


def lavora(job: str, nome: str, testo: str, opera: dict) -> None:
    st = JOBS[job]
    try:
        lib.genera(nome, testo, opera, progresso=lambda i, tot: st.update(fatte=i, totale=tot))
        st["stato"] = "finito"
    except ErroreCopione as e:
        st.update(stato="errore", errore=str(e))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        st.update(stato="errore", errore=f"Errore imprevisto: {e}")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def end_headers(self):
        if not getattr(self, "_immutabile", False):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/api/jobs/" not in str(args[0] if args else ""):
            super().log_message(fmt, *args)

    def json(self, codice: int, obj) -> None:
        corpo = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(codice)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    # ---------- GET
    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == "/api/opere":
            return self.json(200, {"max": lib.MAX_COPIONI, "opere": lib.elenca(), "in_corso": job_in_corso()})
        if p.startswith("/api/jobs/"):
            st = JOBS.get(p.rsplit("/", 1)[1])
            return self.json(200, st) if st else self.json(404, {"errore": "Job sconosciuto."})
        if p.startswith("/audio/"):
            return self.audio(p[len("/audio/"):])
        super().do_GET()

    def audio(self, nome: str) -> None:
        f = lib.CACHE_DIR / nome
        if not re.fullmatch(r"[0-9a-f]{20}\.wav", nome) or not f.exists():
            return self.json(404, {"errore": "Clip non trovata."})
        dati = f.read_bytes()
        n = len(dati)
        start, end, codice = 0, n - 1, 200
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
        if m and (m.group(1) or m.group(2)):
            a, b = m.groups()
            if a == "":
                start, end = max(0, n - int(b)), n - 1
            else:
                start, end = int(a), min(int(b) if b else n - 1, n - 1)
            if start > end or start >= n:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{n}")
                self.end_headers()
                return
            codice = 206
        self._immutabile = True
        self.send_response(codice)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        if codice == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{n}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self.wfile.write(dati[start:end + 1])

    # ---------- POST: carica un copione
    def do_POST(self):
        global corrente
        if urllib.parse.urlparse(self.path).path != "/api/opere":
            return self.json(404, {"errore": "Non trovato."})
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return self.json(400, {"errore": "File vuoto."})
        if n > lib.MAX_BYTES:
            return self.json(413, {"errore": f"File troppo grande (massimo {lib.MAX_BYTES // 2**20} MB)."})
        nome_file = urllib.parse.unquote(self.headers.get("X-Nome") or "copione.txt")
        dati = self.rfile.read(n)

        with JOBS_LOCK:
            if job_in_corso():
                return self.json(409, {"errore": "Sto già elaborando un copione: aspetta che finisca."})
            if len(lib.elenca()) >= lib.MAX_COPIONI:
                return self.json(409, {"errore": f"Hai già {lib.MAX_COPIONI} copioni: eliminane uno per aggiungerne un altro."})
            try:
                testo, opera = lib.da_file(nome_file, dati)
            except ErroreCopione as e:
                return self.json(e.codice, {"errore": str(e)})
            nome = lib.slugify(Path(nome_file).stem)
            if (lib.OPERE_DIR / nome / "opera.json").exists():
                return self.json(409, {"errore": "Esiste già un copione con questo nome: eliminalo prima o rinomina il file."})
            job = uuid.uuid4().hex[:8]
            JOBS[job] = {"stato": "in_corso", "nome": nome, "fatte": 0, "totale": lib.n_clip(opera), "errore": None}
            corrente = job
        threading.Thread(target=lavora, args=(job, nome, testo, opera), daemon=True).start()
        self.json(202, {"job": job, "nome": nome})

    # ---------- DELETE: elimina un copione
    def do_DELETE(self):
        p = urllib.parse.urlparse(self.path).path
        if not p.startswith("/api/opere/"):
            return self.json(404, {"errore": "Non trovato."})
        try:
            lib.elimina(urllib.parse.unquote(p[len("/api/opere/"):]))
        except ErroreCopione as e:
            return self.json(e.codice, {"errore": str(e)})
        self.json(200, {"ok": True})


if __name__ == "__main__":
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else 8766
    lib.pulisci()
    print(f"Imbeccata su http://localhost:{porta}  (massimo {lib.MAX_COPIONI} copioni)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", porta), Handler).serve_forever()
