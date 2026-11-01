"""Aggiunge un copione da riga di comando (alternativa al pannello "Copioni" del player).

Uso:
    python -I src/build.py testi/esempio.txt [--cast testi/esempio.cast.json]

Accetta .txt (formato del progetto) o .pdf. Se il file cast non esiste viene
creato con voci assegnate in automatico (da modificare a mano). Vale il limite
di copioni di libreria.MAX_COPIONI; per sostituire un copione con lo stesso
nome basta rilanciare il comando (le clip già generate vengono riusate).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import libreria as lib  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("testo")
    ap.add_argument("--cast")
    args = ap.parse_args()

    src = Path(args.testo)
    try:
        testo, opera = lib.da_file(src.name, src.read_bytes())
        cast_path = Path(args.cast) if args.cast else src.with_suffix(".cast.json")
        cast = json.loads(cast_path.read_text(encoding="utf-8")) if cast_path.exists() else None
        totale = lib.n_clip(opera)
        cast = lib.genera(
            lib.slugify(src.stem), testo, opera, cast,
            progresso=lambda i, t: print(f"\r[{i}/{t}]", end="", flush=True),
        )
    except lib.ErroreCopione as e:
        sys.exit(f"Errore: {e}")
    if not cast_path.exists():
        cast_path.write_text(json.dumps(cast, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nCreato cast di default: {cast_path}")
    print(f"\nFatto: {totale} battute con audio.")


if __name__ == "__main__":
    main()
