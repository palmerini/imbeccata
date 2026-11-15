"""Motori TTS sostituibili e cache delle clip.

Per aggiungere un motore (anche a pagamento) basta una classe con
`id`, `version` e `synthesize(testo, voce, params) -> (campioni float32, sample_rate)`
e registrarla in ENGINES.
"""
import base64
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf


class KokoroEngine:
    id = "kokoro"
    version = "82M-v1"
    sample_rate = 24000

    def __init__(self):
        self._pipe = None

    def synthesize(self, testo: str, voce: str, params: dict):
        if self._pipe is None:
            from kokoro import KPipeline

            self._pipe = KPipeline(lang_code="i", repo_id="hexgrad/Kokoro-82M")
        speed = params.get("speed", 1.0)
        chunks = [np.asarray(a) for _, _, a in self._pipe(testo, voice=voce, speed=speed)]
        return np.concatenate(chunks).astype("float32"), self.sample_rate


def _spezza(testo: str, massimo: int) -> list[str]:
    """Divide un testo lungo in pezzi di al più `massimo` caratteri, andando a capo fra le frasi."""
    frasi = re.split(r"(?<=[.!?…])\s+", testo.strip())
    pezzi, corrente = [], ""
    for f in frasi:
        while len(f) > massimo:  # frase lunghissima: taglia sull'ultimo spazio utile
            taglio = f.rfind(" ", 0, massimo) or massimo
            if taglio <= 0:
                taglio = massimo
            if corrente:
                pezzi.append(corrente)
                corrente = ""
            pezzi.append(f[:taglio].strip())
            f = f[taglio:].strip()
        if corrente and len(corrente) + 1 + len(f) > massimo:
            pezzi.append(corrente)
            corrente = ""
        corrente = f"{corrente} {f}".strip()
    if corrente:
        pezzi.append(corrente)
    return [p for p in pezzi if p]


class GoogleChirpEngine:
    """Google Cloud Text-to-Speech, voci Chirp 3 HD (a pagamento oltre la quota gratuita).

    Serve la chiave API nella variabile d'ambiente GOOGLE_TTS_API_KEY (mai nei file del progetto).
    La voce è il nome completo, es. "it-IT-Chirp3-HD-Charon"; `speed` è lo speakingRate (0.25-2.0).
    Il testo delle battute viene inviato a Google.
    """

    id = "google-chirp3-hd"
    version = "v1"
    sample_rate = 24000  # indicativo: quello reale è nell'intestazione del WAV restituito
    LINGUA = "it-IT"
    MAX_CHARS = 900
    URL = "https://texttospeech.googleapis.com/v1"

    def _chiama(self, percorso: str, corpo: dict | None = None) -> dict:
        chiave = os.environ.get("GOOGLE_TTS_API_KEY", "").strip()
        if not chiave:
            raise RuntimeError("Manca la variabile d'ambiente GOOGLE_TTS_API_KEY.")
        dati = json.dumps(corpo).encode() if corpo is not None else None
        for tentativo in range(4):
            req = urllib.request.Request(
                self.URL + percorso, data=dati, method="POST" if dati else "GET",
                headers={"Content-Type": "application/json", "x-goog-api-key": chiave},
            )
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and tentativo < 3:
                    time.sleep(2 * 2 ** tentativo)
                    continue
                try:
                    msg = json.load(e).get("error", {}).get("message", "")
                except Exception:
                    msg = ""
                raise RuntimeError(f"Google TTS: errore {e.code}. {msg}".strip()) from None
            except urllib.error.URLError as e:
                if tentativo < 3:
                    time.sleep(2 * 2 ** tentativo)
                    continue
                raise RuntimeError(f"Google TTS: connessione non riuscita ({e.reason}).") from None
        raise RuntimeError("Google TTS: troppi tentativi.")

    def voci(self) -> list[tuple[str, str]]:
        """[(nome, genere)] delle voci Chirp 3 HD disponibili per l'italiano."""
        r = self._chiama(f"/voices?languageCode={self.LINGUA}")
        return sorted((v["name"], v.get("ssmlGender", "")) for v in r.get("voices", [])
                      if "Chirp3-HD" in v["name"])

    def synthesize(self, testo: str, voce: str, params: dict):
        speed = min(2.0, max(0.25, float(params.get("speed", 1.0))))
        pezzi, sr = [], self.sample_rate
        for parte in _spezza(testo, self.MAX_CHARS):
            r = self._chiama("/text:synthesize", {
                "input": {"text": parte},
                "voice": {"languageCode": self.LINGUA, "name": voce},
                "audioConfig": {"audioEncoding": "LINEAR16", "speakingRate": speed},
            })
            audio, sr = sf.read(io.BytesIO(base64.b64decode(r["audioContent"])), dtype="float32")
            pezzi.append(audio if audio.ndim == 1 else audio.mean(axis=1))
        silenzio = np.zeros(int(sr * 0.15), dtype="float32")
        unito = pezzi[0]
        for p in pezzi[1:]:
            unito = np.concatenate([unito, silenzio, p])
        return unito, sr


ENGINES = {"kokoro": KokoroEngine, "google-chirp3-hd": GoogleChirpEngine}


def cache_key(engine, testo: str, voce: str, params: dict) -> str:
    payload = json.dumps(
        [engine.id, engine.version, voce, params, testo], ensure_ascii=False, sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


class ClipCache:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._engines = {}
        self.generate_count = 0
        self.hit_count = 0

    def engine(self, name: str):
        if name not in self._engines:
            self._engines[name] = ENGINES[name]()
        return self._engines[name]

    def get(self, engine_name: str, testo: str, voce: str, params: dict) -> tuple[str, float]:
        """Ritorna (nome file, durata in secondi); genera la clip solo se manca."""
        eng = self.engine(engine_name)
        key = cache_key(eng, testo, voce, params)
        path = self.folder / f"{key}.wav"
        if path.exists():
            self.hit_count += 1
            info = sf.info(path)
            return path.name, info.frames / info.samplerate
        audio, sr = eng.synthesize(testo, voce, params)
        sf.write(path, audio, sr)
        self.generate_count += 1
        return path.name, len(audio) / sr
