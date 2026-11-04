"""Esporta copioni già generati come sito statico di sola lettura (da pubblicare su Cloudflare).

Uso:
    python -I src/esporta.py [nome_copione ...] [--out dist] [--bitrate 64k]

Senza nomi esporta tutti i copioni presenti in web/opere/. Il risultato in dist/ contiene
solo il player (senza pannello Copioni né Voci), il manifest di ogni copione e le clip
convertite in MP3: non c'è nessun server e non si possono generare nuovi audio.
Richiede ffmpeg.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

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


def converti_mp3(wav: Path, mp3: Path, bitrate: str) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-map_metadata", "-1",
         "-ac", "1", "-codec:a", "libmp3lame", "-b:a", bitrate, str(mp3)],
        check=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("nomi", nargs="*")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--bitrate", default="64k")
    args = ap.parse_args()

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

    indice, convertite = [], set()
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
            mp3_nome = wav.stem + ".mp3"
            if mp3_nome not in convertite:
                converti_mp3(wav, out / "audio" / mp3_nome, args.bitrate)
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

    byte = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    n_file = sum(1 for f in out.rglob("*") if f.is_file())
    print(f"\nEsportato in {out}: {n_file} file, {byte / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
