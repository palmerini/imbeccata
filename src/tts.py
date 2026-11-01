"""Motori TTS sostituibili e cache delle clip.

Per aggiungere un motore (anche a pagamento) basta una classe con
`id`, `version` e `synthesize(testo, voce, params) -> (campioni float32, sample_rate)`
e registrarla in ENGINES.
"""
import hashlib
import json
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


ENGINES = {"kokoro": KokoroEngine}


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
