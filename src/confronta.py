"""Confronto d'ascolto fra motori TTS su alcune battute del copione.

Uso (con la chiave in GOOGLE_TTS_API_KEY, vedi README):
    python -I src/confronta.py [testi/copione.txt] [--voci 4] [--seed 4]

Sceglie 7 battute diverse (breve, domanda, esclamazione, lunga, esitazione, una femminile, una
maschile), le fa leggere da Kokoro e da alcune voci Chirp 3 HD dello stesso genere del personaggio
e scrive confronto/index.html: ogni battuta ha le letture in ordine casuale, con i nomi nascosti
finché non premi "Rivela". Le clip stanno in confronto/audio (non nella cache dei copioni).
Al servizio Google vengono inviati solo i testi di queste battute.

Per cambiare la voce di un solo personaggio:
    python -I src/confronta.py --personaggio TERESA [--voci 6]
legge due sue battute con la voce attuale (da testi/obiettivo_sul_lago_004.cast.json) e con altre
voci Chirp dello stesso genere non usate dagli altri personaggi, sempre alla cieca.
"""
import argparse
import html
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import libreria as lib  # noqa: E402
from tts import ClipCache, GoogleChirpEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "confronto"
KOKORO = {"F": "if_sara", "M": "im_nicola"}
PREFERITE = {
    "F": ["Aoede", "Kore", "Leda", "Zephyr", "Achernar", "Sulafat"],
    "M": ["Charon", "Puck", "Orus", "Algenib", "Fenrir", "Achird"],
}
ALIAS = {"MARTINA": "ASSISTENTE"}


def generi(cast_path: Path) -> dict[str, str]:
    """Genere dei personaggi dal cast già in libreria (voce femminile/maschile di Kokoro)."""
    cast = json.loads(cast_path.read_text(encoding="utf-8"))
    out = {p: ("F" if c["voce"] == "if_sara" else "M") for p, c in cast.items()}
    for nuovo, vecchio in ALIAS.items():
        if vecchio in out:
            out[nuovo] = out[vecchio]
    return out


def scegli(battute: list[dict], gen: dict[str, str], rng: random.Random) -> list[tuple[str, dict]]:
    def ok(r, lo, hi, extra=lambda r: True):
        t = r["testo_tts"]
        return lo <= len(t) <= hi and r["personaggio"] in gen and extra(r)

    criteri = [
        ("battuta breve", lambda r: ok(r, 30, 80, lambda r: gen[r["personaggio"]] == "M")),
        ("domanda", lambda r: ok(r, 90, 170, lambda r: r["testo_tts"].rstrip().endswith("?"))),
        ("esclamazione", lambda r: ok(r, 90, 170, lambda r: "!" in r["testo_tts"])),
        ("battuta lunga", lambda r: ok(r, 300, 450)),
        ("esitazione (puntini)", lambda r: ok(r, 100, 220, lambda r: r["testo_tts"].count("...") >= 2)),
        ("personaggio femminile", lambda r: ok(r, 120, 220, lambda r: gen[r["personaggio"]] == "F")),
        ("personaggio maschile", lambda r: ok(r, 120, 220, lambda r: r["personaggio"] in ("DON BRUNO", "BEPPE", "ISAIA"))),
    ]
    scelte, usate = [], set()
    for nome, f in criteri:
        cand = [r for r in battute if f(r) and r["id"] not in usate]
        if cand:
            r = rng.choice(cand)
            usate.add(r["id"])
            scelte.append((nome, r))
    return scelte


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("testo", nargs="?", default=str(ROOT / "testi" / "obiettivo_sul_lago_004.txt"))
    ap.add_argument("--voci", type=int, default=4, help="voci Chirp per genere (default 4)")
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--cast", default=str(ROOT / "web" / "opere" / "obiettivo_sul_lago" / "cast.json"))
    ap.add_argument("--personaggio", help="confronta solo le voci per questo personaggio")
    ap.add_argument("--cast-chirp", default=str(ROOT / "testi" / "obiettivo_sul_lago_004.cast.json"))
    args = ap.parse_args()

    src = Path(args.testo)
    _, opera = lib.da_file(src.name, src.read_bytes())
    rng = random.Random(args.seed)
    battute = [r for r in opera["righe"] if r["tipo"] == "battuta" and r["testo_tts"]]
    gen = {} if args.personaggio else generi(Path(args.cast))
    campioni = [] if args.personaggio else scegli(battute, gen, rng)

    google = GoogleChirpEngine()
    try:
        disponibili = google.voci()
    except RuntimeError as e:
        sys.exit(f"Errore: {e}")
    if not disponibili:
        sys.exit("Errore: nessuna voce Chirp 3 HD per l'italiano.")
    nomi_g = {"F": [n for n, g in disponibili if g == "FEMALE"], "M": [n for n, g in disponibili if g == "MALE"]}
    print(f"Voci Chirp 3 HD italiane disponibili: {len(disponibili)} "
          f"({len(nomi_g['F'])} femminili, {len(nomi_g['M'])} maschili)")

    scelta_voci = {}
    if args.personaggio:
        pers = args.personaggio.strip().upper()
        cast = json.loads(Path(args.cast_chirp).read_text(encoding="utf-8"))
        if pers not in cast:
            sys.exit(f"Errore: {pers} non è nel cast ({', '.join(sorted(cast))}).")
        attuale = cast[pers]["voce"]
        genere = dict(disponibili).get(attuale)
        if genere not in ("FEMALE", "MALE"):
            sys.exit(f"Errore: non conosco il genere della voce attuale ({attuale}).")
        g = "F" if genere == "FEMALE" else "M"
        usate = {c["voce"] for p, c in cast.items() if p != pers}
        altre = [n for n in nomi_g[g] if n not in usate and n != attuale]
        rng.shuffle(altre)
        scelta_voci[g] = [attuale] + altre[: args.voci]
        gen[pers] = g
        prop = [r for r in battute if r["personaggio"] == pers and 80 <= len(r["testo_tts"]) <= 260]
        if len(prop) < 2:
            prop = [r for r in battute if r["personaggio"] == pers and len(r["testo_tts"]) >= 30]
        rng.shuffle(prop)
        # una battuta con domanda o esclamazione, se c'è, e una "normale"
        prop.sort(key=lambda r: not any(c in r["testo_tts"] for c in "?!"))
        campioni = [(f"{pers}: battuta {i}", r) for i, r in enumerate(prop[:2], 1)]
        if not campioni:
            sys.exit(f"Errore: nessuna battuta di {pers}.")
        print(f"Voce attuale di {pers}: {attuale.split('-')[-1]}; "
              f"alternative: {', '.join(n.split('-')[-1] for n in scelta_voci[g][1:])}")
    else:
        for g in "FM":
            pref = [f"{google.LINGUA}-Chirp3-HD-{n}" for n in PREFERITE[g]]
            elenco = [n for n in pref if n in nomi_g[g]] + [n for n in nomi_g[g] if n not in pref]
            scelta_voci[g] = elenco[: args.voci]

    cache = ClipCache(OUT / "audio")
    caratteri_google = 0
    righe_html = []
    for titolo, r in campioni:
        g = gen[r["personaggio"]]
        letture = [] if args.personaggio else [("Kokoro", KOKORO[g], "kokoro", KOKORO[g])]
        letture += [("Google Chirp 3 HD", v.split("-")[-1], "google-chirp3-hd", v) for v in scelta_voci[g]]
        rng.shuffle(letture)
        voci_html = []
        for i, (motore, nome, eng, voce) in enumerate(letture):
            try:
                file, _dur = cache.get(eng, r["testo_tts"], voce, {"speed": 1.0})
            except RuntimeError as e:
                print(f"  saltata {nome}: {e}")
                continue
            if eng != "kokoro":
                caratteri_google += len(r["testo_tts"])
            etichetta = chr(ord("A") + i)
            voci_html.append(
                f'<div class="lettura"><b>{etichetta}</b> <audio controls preload="none" src="audio/{file}"></audio>'
                f' <span class="chi" hidden>{html.escape(motore)} · {html.escape(nome)}</span></div>'
            )
            print(f"  {titolo}: {etichetta} = {motore} {nome}")
        righe_html.append(
            f'<section><h2>{html.escape(titolo)}</h2>'
            f'<p class="meta">{html.escape(r["personaggio"])} ({"donna" if g == "F" else "uomo"})</p>'
            f'<p class="testo">{html.escape(r["testo"])}</p>{"".join(voci_html)}</section>'
        )

    pagina = f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Confronto voci</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
body {{ max-width: 760px; margin: 0 auto; padding: 16px; line-height: 1.45; }}
section {{ border-top: 1px solid #8884; padding: 12px 0; }}
h2 {{ margin: 0; font-size: 1.05rem; }}
.meta {{ margin: 2px 0 6px; opacity: .7; font-size: .9rem; }}
.testo {{ margin: 0 0 8px; }}
.lettura {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 4px 0; }}
audio {{ height: 34px; }}
button {{ font: inherit; padding: 6px 12px; }}
</style></head><body>
<h1>Confronto voci</h1>
<p>Ascolta ogni battuta con le diverse letture (l'ordine è casuale) e annota le tue preferite.</p>
<button id="rivela">Rivela i nomi</button>
{"".join(righe_html)}
<script>
document.getElementById('rivela').onclick = () => document.querySelectorAll('.chi').forEach(e => e.hidden = !e.hidden);
</script></body></html>"""
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(pagina, encoding="utf-8")
    print(f"\nCaratteri di testo letti da Chirp (al massimo, se non già in confronto/audio): {caratteri_google}")
    print(f"Pagina pronta: {OUT / 'index.html'}")


if __name__ == "__main__":
    main()
