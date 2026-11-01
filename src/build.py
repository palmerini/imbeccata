"""Costruisce il pacchetto di un'opera: parsing + clip audio + manifest.

Uso:
    python -I src/build.py testi/esempio.txt [--cast testi/esempio.cast.json]

Se il file cast non esiste viene creato con voci assegnate in automatico
(da modificare a mano). Le clip finiscono in cache/ e vengono riusate.
Il pacchetto per il player web è scritto in web/opere/<nome>/.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from copione import parse  # noqa: E402
from tts import ClipCache  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VOCI_IT = ["if_sara", "im_nicola"]


def default_cast(personaggi):
    # alterna le due voci e varia la velocità per distinguere i personaggi
    speeds = [1.0, 0.92, 1.08, 0.97]
    return {
        p: {"engine": "kokoro", "voce": VOCI_IT[i % 2], "speed": speeds[(i // 2) % len(speeds)]}
        for i, p in enumerate(personaggi)
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("testo")
    ap.add_argument("--cast")
    args = ap.parse_args()

    src = Path(args.testo)
    nome = src.stem
    opera = parse(src.read_text(encoding="utf-8"))

    cast_path = Path(args.cast) if args.cast else src.with_suffix(".cast.json")
    if cast_path.exists():
        cast = json.loads(cast_path.read_text(encoding="utf-8"))
    else:
        # in ordine di prima apparizione, così chi dialoga di seguito ha voci diverse
        ordine = []
        for r in opera["righe"]:
            for p in r.get("parlanti") or []:
                if p not in ordine:
                    ordine.append(p)
        cast = default_cast(ordine)
        cast_path.write_text(json.dumps(cast, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Creato cast di default: {cast_path}")
    mancanti = [p for p in opera["personaggi"] if p not in cast]
    if mancanti:
        sys.exit(f"Personaggi senza voce nel cast: {mancanti}")

    cache = ClipCache(ROOT / "cache")
    out_dir = ROOT / "web" / "opere" / nome
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    n_battute = sum(1 for r in opera["righe"] if r["tipo"] == "battuta")
    done = 0
    for r in opera["righe"]:
        if r["tipo"] != "battuta" or not r["testo_tts"]:
            continue
        c = cast[r["personaggio"]]
        params = {"speed": c.get("speed", 1.0)}
        fname, dur = cache.get(c["engine"], r["testo_tts"], c["voce"], params)
        shutil.copyfile(ROOT / "cache" / fname, audio_dir / fname)
        r["audio"], r["durata"] = fname, round(dur, 2)
        done += 1
        print(f"[{done}/{n_battute}] {r['personaggio']}: {r['testo_tts'][:50]}", flush=True)

    (out_dir / "opera.json").write_text(json.dumps(opera, ensure_ascii=False, indent=1), encoding="utf-8")

    elenco = ROOT / "web" / "opere" / "index.json"
    opere = sorted(p.parent.name for p in (ROOT / "web" / "opere").glob("*/opera.json"))
    elenco.write_text(json.dumps(opere), encoding="utf-8")
    print(f"\nFatto: {cache.generate_count} clip generate, {cache.hit_count} riusate dalla cache.")


if __name__ == "__main__":
    main()
