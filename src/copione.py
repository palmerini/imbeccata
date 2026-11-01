"""Parser del copione.

Formato atteso (testo semplice):

    # Titolo dell'opera
    ## Scena 1            <- intestazione di scena (opzionale)
    (Didascalia su riga a sé, tra parentesi)
    MARIA: Buongiorno, come stai?
    GIORGIO: (sorridendo) Bene, grazie.
        Continuo la battuta su una riga rientrata.

Le battute continuano finché non compare un nuovo "PERSONAGGIO:",
una didascalia, una scena o una riga vuota. Le didascalie tra parentesi
dentro una battuta restano nel testo mostrato ma non vengono lette dal TTS.
"""
import json
import re
import sys
from dataclasses import dataclass, asdict

RE_BATTUTA = re.compile(r"^([A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ý0-9 '.\-/]{0,80}):\s*(.*)$")
RE_SCENA = re.compile(r"^##\s+(.*)$")
RE_TITOLO = re.compile(r"^#\s+(.*)$")
RE_DIDASCALIA = re.compile(r"^\((.*)\)\s*$")
RE_INLINE_DIDA = re.compile(r"\([^)]*\)")


@dataclass
class Riga:
    id: int
    tipo: str  # "battuta" | "didascalia" | "scena"
    personaggio: str | None
    testo: str  # testo mostrato
    testo_tts: str  # testo da sintetizzare (senza didascalie)
    scena: str
    parlanti: list[str] | None = None  # più personaggi se la battuta è corale ("A/B: ...")


def parse(text: str) -> dict:
    titolo = ""
    scena = ""
    righe: list[Riga] = []
    corrente: Riga | None = None

    def chiudi():
        nonlocal corrente
        corrente = None

    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s:
            chiudi()
            continue
        if m := RE_SCENA.match(s):
            chiudi()
            scena = m.group(1).strip()
            righe.append(Riga(len(righe), "scena", None, scena, "", scena))
        elif m := RE_TITOLO.match(s):
            chiudi()
            titolo = m.group(1).strip()
        elif m := RE_DIDASCALIA.match(s):
            chiudi()
            righe.append(Riga(len(righe), "didascalia", None, s, "", scena))
        elif m := RE_BATTUTA.match(s):
            chiudi()
            parlanti = [p.strip() for p in m.group(1).split("/") if p.strip()]
            corrente = Riga(len(righe), "battuta", parlanti[0], m.group(2).strip(), "", scena, parlanti)
            righe.append(corrente)
        elif corrente is not None:
            corrente.testo += " " + s
        else:
            chiudi()
            righe.append(Riga(len(righe), "didascalia", None, s, "", scena))

    for r in righe:
        if r.tipo == "battuta":
            t = RE_INLINE_DIDA.sub(" ", r.testo)
            t = re.sub(r"\s+", " ", t).strip()
            # niente da leggere se resta solo punteggiatura (es. "…")
            r.testo_tts = t if re.search(r"\w", t) else ""

    personaggi = sorted({p for r in righe if r.parlanti for p in r.parlanti})
    return {"titolo": titolo, "personaggi": personaggi, "righe": [asdict(r) for r in righe]}


if __name__ == "__main__":
    out = parse(open(sys.argv[1], encoding="utf-8").read())
    print(json.dumps(out, ensure_ascii=False, indent=2))
