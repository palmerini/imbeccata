"""Converte un copione PDF (impaginato "NOME<spazio> battuta") nel formato del progetto.

Uso:
    python -I src/pdf2txt.py "testi/copione.pdf" testi/copione.txt

Assunzioni sul PDF:
- una sezione PERSONAGGI con un nome in maiuscolo all'inizio di ogni riga;
- le battute iniziano a margine sinistro con il nome (anche abbreviato,
  es. "PART 1" per "PARTECIPANTE 1") seguito da uno spazio zero-width;
- le righe rientrate continuano la battuta;
- le didascalie sono righe a margine sinistro che iniziano con "(".
"""
import re
import subprocess
import sys

ZW = "​"
RE_NOME = re.compile(r"^([A-ZÀ-Ý]{2,}(?: \d+)?)")
RE_LABEL = re.compile(r"^([A-ZÀ-Ý]{3,}(?: \d+)?(?: e \d+)?)[ \t]*" + ZW + r"?[ \t]*(.*)$")


def risolvi(label: str, noti: list[str]) -> list[str] | None:
    """'PART 1 e 2' -> ['PARTECIPANTE 1', 'PARTECIPANTE 2']; None se non è un personaggio."""
    base = re.match(r"^([A-ZÀ-Ý]+)(?: (\d+))?(?: e (\d+))?$", label)
    if not base:
        return None
    parola, n1, n2 = base.groups()
    out = []
    for num in [n1] + ([n2] if n2 else []):
        trovato = None
        for nome in noti:
            m = re.match(r"^([A-ZÀ-Ý]+)(?: (\d+))?$", nome)
            if m and m.group(1).startswith(parola) and m.group(2) == num:
                trovato = nome
                break
        if not trovato:
            return None
        out.append(trovato)
    return out


def aperta(s: str) -> bool:
    return s.count("(") > s.count(")")


def converti(testo_pdf: str) -> str:
    righe = [r.replace("\f", "") for r in testo_pdf.splitlines()]
    titolo = next((r.strip() for r in righe if r.strip()), "")

    # inizio corpo: primo margine sinistro "NOME" + ZWSP
    inizio = next(i for i, r in enumerate(righe) if re.match(r"^[A-ZÀ-Ý]{3,}(?: \d+)?(?: e \d+)?[ \t]*" + ZW, r))
    # sezione personaggi: dopo la riga "PERSONAGGI"
    p0 = next(i for i, r in enumerate(righe) if r.strip().upper() == "PERSONAGGI")
    noti = []
    for r in righe[p0 + 1:inizio]:
        if m := RE_NOME.match(r):
            if m.group(1) not in noti:
                noti.append(m.group(1))

    out = [f"# {titolo}", ""]
    ultima = None  # ("battuta"|"dida", indice in out)
    for r in righe[inizio:]:
        s = r.replace(ZW, " ").strip()
        if not s:
            continue
        indentata = r[:1] in (" ", "\t")
        # didascalia a più righe ancora aperta
        if ultima and ultima[0] == "dida" and aperta(out[ultima[1]]) and not indentata:
            out[ultima[1]] += " " + s
            continue
        if indentata:
            if ultima:
                out[ultima[1]] += " " + s
            continue
        if s.startswith("("):
            out.append(s)
            ultima = ("dida", len(out) - 1)
            continue
        m = RE_LABEL.match(r.rstrip())
        chi = risolvi(m.group(1), noti) if m else None
        if chi:
            corpo = m.group(2).replace(ZW, " ").strip()
            out.append(f"{'/'.join(chi)}: {corpo}")
            ultima = ("battuta", len(out) - 1)
        elif s == "FINE":
            out.append("")
            out.append("## FINE")
            ultima = None
        elif ultima:  # riga a margine non riconosciuta: continuazione
            out[ultima[1]] += " " + s
    return "\n".join(re.sub(r"\s+", " ", l).strip() if l else l for l in out) + "\n"


if __name__ == "__main__":
    pdf, dest = sys.argv[1], sys.argv[2]
    testo = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True, check=True).stdout
    open(dest, "w", encoding="utf-8").write(converti(testo))
    print("scritto", dest)
