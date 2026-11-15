"""Normalizzazione del testo da sintetizzare (cosa legge il TTS, non cosa si vede a schermo).

Si applica a ogni battuta dopo aver tolto le didascalie in linea:
- numeri, ordinali (39º) e percentuali scritti in lettere (1977 -> millenovecentosettantasette);
- nomi dei personaggi scritti in maiuscolo (OLIVIERO) in forma normale (Oliviero);
- apostrofi e virgolette tipografiche ('’' -> "'"), così le elisioni (l'anno) non si spezzano;
- puntini di sospensione ridotti a "..." (mai a inizio battuta), punti esclamativi/interrogativi
  ripetuti ridotti a uno, trattini e spazi prima della punteggiatura ripuliti.

Le parole in maiuscolo che non sono nomi (parole urlate) restano come sono.
Cambiare queste regole cambia il testo di alcune battute, e quindi la loro chiave di cache:
le clip già generate per quelle battute non vengono più riusate.
"""
import re

_UNITA = ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci",
          "undici", "dodici", "tredici", "quattordici", "quindici", "sedici", "diciassette",
          "diciotto", "diciannove"]
_DECINE = ["", "", "venti", "trenta", "quaranta", "cinquanta", "sessanta", "settanta", "ottanta", "novanta"]
_ORDINALI = ["", "primo", "secondo", "terzo", "quarto", "quinto", "sesto", "settimo", "ottavo", "nono", "decimo"]


def _sotto_cento(n: int) -> str:
    if n < 20:
        return _UNITA[n]
    d, u = divmod(n, 10)
    base = _DECINE[d]
    if u in (1, 8):  # ventuno, ventotto
        base = base[:-1]
    if u == 0:
        return base
    return base + ("tré" if u == 3 else _UNITA[u])


def _sotto_mille(n: int) -> str:
    c, r = divmod(n, 100)
    if c == 0:
        return _sotto_cento(r)
    prefisso = "cento" if c == 1 else _UNITA[c] + "cento"
    if r == 0:
        return prefisso
    if r == 8 or 80 <= r < 90:  # centotto, centottanta
        prefisso = prefisso[:-1]
    return prefisso + _sotto_cento(r)


def cardinale(n: int) -> str:
    """Numero in lettere fino a 999.999 (oltre, resta in cifre)."""
    if n >= 1_000_000:
        return str(n)
    if n < 1000:
        return _sotto_mille(n)
    k, r = divmod(n, 1000)
    testa = "mille" if k == 1 else _sotto_mille(k) + "mila"
    return testa + (_sotto_mille(r) if r else "")


def ordinale(n: int, femminile: bool = False) -> str:
    if 1 <= n <= 10:
        parola = _ORDINALI[n]
    else:
        c = cardinale(n)
        if c.endswith("mila"):
            c = c[:-4] + "mill"
        elif c.endswith(("tré", "tre")):
            c = c.replace("é", "e")
        elif not c.endswith("sei"):
            c = c[:-1]
        parola = c + "esimo"
    return parola[:-1] + "a" if femminile else parola


def _numeri(t: str) -> str:
    t = re.sub(r"(\d+)\s*([º°ª])", lambda m: ordinale(int(m.group(1)), m.group(2) == "ª"), t)
    t = re.sub(r"(\d+)\s*%", lambda m: cardinale(int(m.group(1))) + " per cento", t)
    return re.sub(r"\d+", lambda m: cardinale(int(m.group(0))), t)


def normalizza(testo: str, nomi: list[str] | None = None) -> str:
    """`nomi`: nomi dei personaggi (anche composti, es. 'DON BRUNO')."""
    t = testo
    t = t.replace("’", "'").replace("‘", "'").replace("`", "'").replace("´", "'")
    t = re.sub(r"[“”«»„\"]", "", t)
    t = _numeri(t)

    parole = {p for n in (nomi or []) for p in re.findall(r"[A-ZÀ-ÖØ-Ý]{3,}", n)}
    if parole:
        t = re.sub(r"\b(" + "|".join(sorted(parole, key=len, reverse=True)) + r")\b",
                   lambda m: m.group(1).capitalize(), t)

    t = re.sub(r"\s*[–—]\s*|\s-\s", ", ", t)  # trattini usati come incisi
    t = re.sub(r"[.…](?:\s*[.…])+|…", "...", t)  # anche ". ..." o ".…"
    t = re.sub(r"[,;:]\s*\.\.\.", "...", t)  # niente virgola prima dei puntini
    t = re.sub(r"\.\.\.(?=[^\s.,;:!?])", "... ", t)
    t = re.sub(r"([?!])\1+", r"\1", t)
    t = re.sub(r"\s+([,;:.!?])", r"\1", t)
    t = re.sub(r"([,;:])(\s*[,;:])+", r"\1", t)
    t = re.sub(r"^[\s.,;:]+", "", t)  # niente pausa o virgola a inizio battuta
    return re.sub(r"\s+", " ", t).strip()
