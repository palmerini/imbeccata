"""Converte un copione in formato Fountain (.fountain) nel formato del progetto.

Uso:
    python -I src/fountain2txt.py "testi/copione.fountain" testi/copione.txt

Regole applicate (sintassi Fountain, https://fountain.io):
- frontespizio (Title:, Subtitle:, ...): Title e Subtitle diventano il titolo, il resto è ignorato;
- NOME in maiuscolo da solo su una riga, preceduto da una riga vuota e seguito da testo
  (o @Nome forzato): inizia una battuta. Le righe successive, fino alla prima riga vuota,
  sono la battuta; una riga con soli spazi non interrompe la battuta. Le righe tra parentesi
  restano nella battuta come didascalie in linea (non vengono lette);
- "A E B" (con A e B personaggi che parlano anche da soli) diventa una battuta corale "A/B";
- ogni altro paragrafo è una didascalia; `.SCENA ...` è l'intestazione di una scena e viene
  unita alla sezione (`# ATTO I`) che la precede; gli altri `.LUOGO` sono didascalie;
- sezioni senza testo (ad esempio la sinossi), sinossi `= ...`, note `[[...]]`, boneyard
  `/* ... */` e interruzioni di pagina `===` sono ignorate.

Un paragrafo di testo staccato da una riga vuota dalla battuta che lo precede è, per Fountain,
una didascalia: se in realtà è la continuazione di un discorso va corretto a mano nel .txt.
"""
import re
import sys

CHIAVI_FRONTESPIZIO = {
    "title", "credit", "author", "authors", "source", "notes", "draft date", "date",
    "contact", "copyright", "revision", "subtitle",
}
RE_CHIAVE = re.compile(r"^([A-Za-z][A-Za-z ]*?)\s*:\s*(.*)$")
RE_ROMANO = re.compile(r"^(?=[IVX])(X{0,3})(IX|IV|V?I{0,3})$")
RE_SEP = re.compile(r"\s+[–—-]\s+")
RE_NOME = re.compile(r"^[A-ZÀ-ÖØ-Ý][A-ZÀ-ÖØ-Ý0-9 '.\-/]{0,80}$")
RE_PAGINA = re.compile(r"^={3,}\s*$")
LETTERE_MAIUSC = re.compile(r"[A-ZÀ-ÖØ-Ý]")
LETTERE_MINUSC = re.compile(r"[a-zß-öø-ÿ]")


def _pulisci(testo: str) -> list[str]:
    """Toglie boneyard e note; una riga che contiene solo una nota sparisce del tutto."""
    testo = testo.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    testo = re.sub(r"/\*.*?\*/", "\x00", testo, flags=re.S)
    testo = re.sub(r"\[\[.*?\]\]", "\x00", testo, flags=re.S)
    righe = []
    for riga in testo.split("\n"):
        if "\x00" in riga:
            riga = riga.replace("\x00", "")
            if not riga.strip():
                continue
        righe.append(riga)
    return righe


def _frontespizio(righe: list[str]) -> tuple[dict, int]:
    """Legge il frontespizio all'inizio del file; ritorna (campi, indice della prima riga dopo)."""
    campi: dict[str, str] = {}
    i = 0
    while i < len(righe) and not righe[i].strip():
        i += 1
    m = RE_CHIAVE.match(righe[i]) if i < len(righe) else None
    if not m or m.group(1).strip().lower() not in CHIAVI_FRONTESPIZIO:
        return {}, 0
    chiave = None
    while i < len(righe) and righe[i].strip():
        riga = righe[i]
        if riga[0] in " \t" and chiave:
            campi[chiave] += " " + riga.strip()
        elif m := RE_CHIAVE.match(riga):
            chiave = m.group(1).strip().lower()
            campi[chiave] = m.group(2).strip()
        i += 1
    return campi, i


def _formatta(testo: str) -> str:
    """'ATTO I – SCENA 01 – LA METROPOLI' -> 'Atto I – Scena 01 – La metropoli' (solo se tutto maiuscolo)."""
    def segmento(s: str) -> str:
        if LETTERE_MINUSC.search(s):
            return s
        parole = [p if RE_ROMANO.match(p) else p.lower() for p in s.split()]
        out = " ".join(parole)
        return out[:1].upper() + out[1:]

    parti = RE_SEP.split(testo.strip())
    return " – ".join(segmento(p) for p in parti)


def _senza_enfasi(testo: str) -> str:
    testo = re.sub(r"\*{1,3}([^*\n]+?)\*{1,3}", r"\1", testo)
    return re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", testo)


def _nome_battuta(riga: str) -> str | None:
    """Nome del personaggio se la riga è una battuta Fountain ("NOME", "@Nome", "NOME (V.O.)"), altrimenti None."""
    s = riga.strip()
    if s.startswith("@"):
        s = s[1:].strip().upper()
    else:
        s = s.rstrip("^").strip()
        if s != s.upper() or not LETTERE_MAIUSC.search(s):
            return None
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s).strip().replace("’", "'")
    return s if RE_NOME.match(s) else None


def _e_inizio_speciale(riga: str) -> bool:
    s = riga.strip()
    return (s.startswith("#") or bool(RE_PAGINA.match(s)) or s.startswith(">")
            or (s.startswith(".") and not s.startswith("..")) or (s.startswith("=") and not RE_PAGINA.match(s)))


def converti(testo: str) -> str:
    righe = _pulisci(testo)
    campi, i = _frontespizio(righe)

    # primo passaggio: i personaggi che parlano da soli (per riconoscere "A E B")
    soli = set()
    for k, riga in enumerate(righe):
        if k and righe[k - 1] == "" or k == 0:
            nome = _nome_battuta(riga) if riga.strip() and not _e_inizio_speciale(riga) else None
            if nome and k + 1 < len(righe) and righe[k + 1].strip():
                soli.add(nome)

    out: list[str] = []
    titolo = campi.get("title", "")
    sub = campi.get("subtitle", "")
    if titolo:
        out.append(f"# {titolo}" + (f"{' ' if sub.startswith('(') else ' – '}{sub}" if sub else ""))

    sezione = ""
    scena = ""
    intestato = False  # l'intestazione "## ..." di sezione/scena correnti è già stata scritta

    def intestazione(testo: str):
        nonlocal intestato
        out.extend(["", f"## {testo}"])
        intestato = True

    def assicura_intestazione():
        if not intestato and sezione and not scena:
            intestazione(sezione)

    n = len(righe)
    while i < n:
        riga = righe[i]
        s = riga.strip()
        if not s:
            i += 1
            continue

        if RE_PAGINA.match(s) or (s.startswith("=") and not s.startswith("==")):
            i += 1  # interruzione di pagina o sinossi
            continue

        if m := re.match(r"^#+\s*(.*)$", s):
            sezione, scena, intestato = _formatta(m.group(1)), "", False
            i += 1
            continue

        if s.startswith(".") and not s.startswith(".."):
            titolo_scena = s[1:].strip()
            i += 1
            if re.match(r"(?i)scena\b", titolo_scena):
                scena = _formatta(titolo_scena)
                intestazione(f"{sezione} – {scena}" if sezione else scena)
            elif LETTERE_MAIUSC.search(titolo_scena) or re.search(r"\w", titolo_scena):
                assicura_intestazione()
                out.append(f"({_formatta(titolo_scena)})")
            continue

        if m := re.match(r"^>\s*(.*?)\s*<$", s):
            i += 1
            if re.search(r"\w", m.group(1)):
                assicura_intestazione()
                out.append(f"({_formatta(m.group(1))})")
            continue

        nome = _nome_battuta(riga)
        if nome and i + 1 < n and righe[i + 1].strip():
            parti = re.split(r"\s+E\s+", nome)
            if len(parti) > 1 and all(p in soli for p in parti):
                nome = "/".join(parti)
            i += 1
            blocco = []
            while i < n and righe[i] != "":
                if righe[i].strip():
                    blocco.append(righe[i].strip())
                i += 1
            parlato = _senza_enfasi(" ".join(re.sub(r"^-\s+", "", r) for r in blocco))
            if re.search(r"\w", parlato) or "(" in parlato:
                assicura_intestazione()
                out.append(f"{nome}: {parlato}")
            continue

        # paragrafo di azione -> didascalia
        blocco = []
        while i < n and righe[i].strip():
            blocco.append(righe[i].strip())
            i += 1
        azione = _senza_enfasi(" ".join(blocco))
        if re.search(r"\w", azione):
            assicura_intestazione()
            out.append(azione if azione.startswith("(") and azione.endswith(")") else f"({azione})")

    # una riga vuota prima di ogni intestazione di scena, non all'inizio
    testo_out = "\n".join(out).strip("\n") + "\n"
    return re.sub(r"\n{3,}", "\n\n", testo_out)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    with open(sys.argv[1], encoding="utf-8-sig") as f:
        risultato = converti(f.read())
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(risultato)
    print(f"Scritto {sys.argv[2]}")
