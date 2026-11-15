"""Esporta copioni già generati come sito statico di sola lettura (da pubblicare su Cloudflare).

Uso:
    python -I src/esporta.py [nome_copione ...] [--out dist] [--bitrate 96k]
                             [--livello -20 | --senza-livellamento]

Senza nomi esporta tutti i copioni presenti in web/opere/. Il risultato in dist/ contiene
solo il player (senza pannello Copioni né Voci), il manifest di ogni copione e le clip
convertite in MP3: non c'è nessun server e non si possono generare nuovi audio.
Richiede ffmpeg.

Livellamento del volume: ogni clip viene portata allo stesso volume medio del parlato
(RMS dei soli tratti di voce, default -20 dBFS) senza superare un picco di -1,5 dBFS, così i
personaggi hanno volumi simili e la conversione in MP3 non satura. Si applica solo all'esportazione:
le clip in cache/ non vengono modificate. Il nome dei file MP3 contiene una sigla delle
impostazioni di esportazione, perché il sito li serve con cache "immutable": cambiando bitrate o
livello i nomi cambiano e i browser scaricano i file nuovi.
"""
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent.parent
OPERE_DIR = ROOT / "web" / "opere"
CACHE_DIR = ROOT / "cache"

HEADERS = """\
/*
  X-Robots-Tag: noindex, nofollow

/
  Cache-Control: no-cache

/index.html
  Cache-Control: no-cache

/opere/*
  Cache-Control: no-cache

/audio/*
  Cache-Control: public, max-age=31536000, immutable
"""


PICCO_MAX_DB = -1.5  # margine per il superamento del picco che la codifica MP3 può causare
SOGLIA_VOCE_DB = -45  # frame di 20 ms sotto questa soglia sono pausa, non parlato
GUADAGNO_LIMITI_DB = (-12.0, 12.0)


def guadagno_db(wav: Path, livello: float) -> float:
    """Guadagno (dB) che porta il parlato della clip a `livello` dBFS RMS senza superare il picco massimo."""
    audio, sr = sf.read(wav, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    n = int(sr * 0.02)
    frame = audio[: len(audio) // n * n].reshape(-1, n)
    rms = np.sqrt((frame ** 2).mean(axis=1)) if len(frame) else np.array([])
    voce = rms[rms > 10 ** (SOGLIA_VOCE_DB / 20)]
    if voce.size == 0:
        return 0.0
    g = livello - 20 * math.log10(float(np.sqrt((voce ** 2).mean())))
    picco = float(np.abs(audio).max())
    if picco > 0:
        g = min(g, PICCO_MAX_DB - 20 * math.log10(picco))
    return max(GUADAGNO_LIMITI_DB[0], min(GUADAGNO_LIMITI_DB[1], g))


def converti_mp3(wav: Path, mp3: Path, bitrate: str, guadagno: float = 0.0) -> None:
    filtro = ["-filter:a", f"volume={guadagno:.2f}dB"] if abs(guadagno) >= 0.05 else []
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-map_metadata", "-1", *filtro,
         "-ac", "1", "-codec:a", "libmp3lame", "-b:a", bitrate, str(mp3)],
        check=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("nomi", nargs="*")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--bitrate", default="96k")
    ap.add_argument("--livello", type=float, default=-20.0, help="volume medio del parlato in dBFS (default -20)")
    ap.add_argument("--senza-livellamento", action="store_true")
    args = ap.parse_args()
    livello = None if args.senza_livellamento else args.livello
    if livello is not None and not -40 <= livello <= -6:
        sys.exit("--livello deve essere fra -40 e -6 dBFS.")
    sigla = hashlib.sha1(f"{args.bitrate}|{livello}|v1".encode()).hexdigest()[:6]

    if not shutil.which("ffmpeg"):
        sys.exit("Serve ffmpeg (brew install ffmpeg).")
    nomi = args.nomi or sorted(p.parent.name for p in OPERE_DIR.glob("*/opera.json"))
    if not nomi:
        sys.exit("Nessun copione in web/opere/.")

    out = (ROOT / args.out).resolve()
    if out == ROOT or ROOT not in out.parents:
        sys.exit(f"Cartella di output non valida: {out}")
    shutil.rmtree(out, ignore_errors=True)
    (out / "audio").mkdir(parents=True)

    indice, convertite, guadagni = [], set(), []
    for nome in nomi:
        src = OPERE_DIR / nome / "opera.json"
        if not src.exists():
            sys.exit(f"Copione non trovato: {nome}")
        opera = json.loads(src.read_text(encoding="utf-8"))
        for r in opera["righe"]:
            if not r.get("audio"):
                continue
            wav = CACHE_DIR / r["audio"]
            if not wav.exists():
                sys.exit(f"Clip mancante in cache/: {r['audio']} ({nome})")
            mp3_nome = f"{wav.stem}-{sigla}.mp3"
            if mp3_nome not in convertite:
                g = guadagno_db(wav, livello) if livello is not None else 0.0
                guadagni.append(g)
                converti_mp3(wav, out / "audio" / mp3_nome, args.bitrate, g)
                convertite.add(mp3_nome)
            r["audio"] = mp3_nome
        dest = out / "opere" / nome
        dest.mkdir(parents=True)
        (dest / "opera.json").write_text(json.dumps(opera, ensure_ascii=False, indent=1), encoding="utf-8")
        indice.append({
            "nome": nome,
            "titolo": opera.get("titolo") or nome,
            "personaggi": opera["personaggi"],
            "battute": sum(1 for r in opera["righe"] if r["tipo"] == "battuta"),
        })
        print(f"{nome}: {sum(1 for r in opera['righe'] if r.get('audio'))} clip")

    (out / "opere" / "index.json").write_text(json.dumps({"opere": indice}, ensure_ascii=False), encoding="utf-8")

    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "const STATICO = false;" in html, "marcatore STATICO non trovato in web/index.html"
    (out / "index.html").write_text(html.replace("const STATICO = false;", "const STATICO = true;"), encoding="utf-8")
    (out / "_headers").write_text(HEADERS, encoding="utf-8")
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")

    if guadagni:
        print(f"Livellamento a {livello:g} dBFS: guadagno da {min(guadagni):+.1f} a {max(guadagni):+.1f} dB "
              f"(media {sum(guadagni) / len(guadagni):+.1f} dB)")

    byte = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    n_file = sum(1 for f in out.rglob("*") if f.is_file())
    print(f"\nEsportato in {out}: {n_file} file, {byte / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
