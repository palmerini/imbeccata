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


def converti_zwsp(testo_pdf: str) -> str:
    """Formato 1: 'NOME<zero-width space> battuta', righe rientrate di continuazione."""
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


RE_PAGINA = re.compile(r"^\s+\d+\s*$")  # numero di pagina da solo su una riga, rientrato
RE_SCENA = re.compile(r"^(ATTO\s+[IVX]+)\s*[–—-]+\s*(scena\s*\d+)\s*[–—-]+\s*(.+)$", re.I)


def _senza_parentesi(testo: str) -> str:
    return re.sub(r"\([^)]*(\)|$)", "", testo).strip()


def _accoda(testo: str, riga: str) -> str:
    """Aggiunge una riga di continuazione, ricomponendo le parole spezzate con il trattino."""
    if len(testo) > 1 and testo.endswith("-") and testo[-2].isalpha() and riga[:1].islower():
        return testo[:-1] + riga
    return testo + " " + riga


def converti_due_punti(testo_pdf: str) -> str:
    """Formato 2: 'NOME: battuta' (anche 'NOME' / 'NOME (didascalia)' su una riga e battuta sotto),
    didascalie come paragrafi liberi, righe lunghe spezzate senza rientro.

    Euristiche: una riga a capo senza rientro continua il blocco precedente se la riga prima
    era "piena" (vicina alla larghezza massima), se inizia con una minuscola, oppure se la
    battuta finora contiene solo una didascalia. Altrimenti è una nuova didascalia.
    """
    grezze = [r.replace("\f", "").replace(ZW, " ").rstrip() for r in testo_pdf.splitlines()]
    # i salti pagina (numero di pagina + righe vuote attorno) devono essere trasparenti
    righe, salta = [], False
    for r in grezze:
        if RE_PAGINA.match(r):
            while righe and not righe[-1].strip():
                righe.pop()
            salta = True
            continue
        if salta and not r.strip():
            continue
        salta = False
        righe.append(r)
    non_vuote = [r.strip() for r in righe if r.strip()]
    titolo = non_vuote[0]
    if len(non_vuote) > 1 and non_vuote[1].startswith("(") and non_vuote[1].endswith(")"):
        titolo += " " + non_vuote[1]

    inizio = next(
        (i for i, r in enumerate(righe) if r.strip() == "INTRODUZIONE" or RE_SCENA.match(r.strip())), None
    )
    p0 = next((i for i, r in enumerate(righe) if r.strip().lower() == "personaggi"), None)
    if inizio is None or p0 is None:
        raise ValueError("struttura non riconosciuta")

    # personaggi dall'elenco puntato (e alias tipo "ASSISTENTE (Martina)")
    noti, alias = [], {}
    for r in righe[p0 + 1:inizio]:
        if not re.match(r"^\s*[•*-]", r):
            continue
        m = re.search(r"\b(DON [A-ZÀ-Ý]{3,}|[A-ZÀ-Ý]{3,})\b", r)
        if m and m.group(1) not in noti:
            noti.append(m.group(1))
            a = re.match(r"\s*\(([A-ZÀ-Ý][a-zà-ÿ]+)\)", r[m.end():])
            if a:
                alias[a.group(1).upper()] = m.group(1)
    # personaggi "di servizio" (es. "VOCE dal telefono:") che parlano più volte ma non sono nell'elenco
    extra = {}
    for r in righe[inizio:]:
        m = re.match(r"^([A-ZÀ-Ý]{3,})((?: [a-zà-ÿ]+){1,3}):", r.strip())
        if m:
            extra[m.group(1)] = extra.get(m.group(1), 0) + 1
    extra_nomi = [n for n, c in extra.items() if c >= 2 and n not in noti]
    if not noti:
        raise ValueError("nessun personaggio")

    nomi_tutti = noti + extra_nomi + list(alias)
    alt = "|".join(re.escape(n) for n in sorted(nomi_tutti, key=len, reverse=True))
    N = f"(?:{alt})"
    re_colon = re.compile(rf"^({N}(?: e {N})*)((?: [a-zà-ÿ]+){{0,3}})(?: \(([^)]*)\))?\s*:\s*(.*)$")
    re_nome = re.compile(rf"^({N})(?=\s|$)")
    re_alias = re.compile(r"^\((" + "|".join(a.capitalize() for a in alias) + r")\)\s*", re.I) if alias else None

    def risolvi(nome: str) -> str:
        return alias.get(nome, nome)

    larghezza = max(len(r) for r in righe)
    soglia = larghezza - 20

    blocchi = []  # [tipo, nomi, testo]
    cur = None
    prev_len, blank = 0, True
    intro = None  # personaggio che parla nell'INTRODUZIONE (testo senza etichetta)
    intro_dida = False

    def nuovo(tipo, nomi, testo):
        nonlocal cur
        cur = [tipo, nomi, testo]
        blocchi.append(cur)

    for r in righe[inizio:]:
        s = r.strip()
        if re.sub(r"\s+", "", s).upper() == "INTERVALLO":  # spesso scritto con le lettere spaziate
            cur = None
            blocchi.append(["dida", [], "Intervallo"])
            continue
        if not s:
            blank = True
            if cur and not (cur[0] == "bat" and not _senza_parentesi(cur[2])):
                cur = None
            continue
        blank_prima, blank = blank, False
        prima_lunga = prev_len >= soglia
        prev_len = len(r)

        if s == "INTRODUZIONE" or (m := RE_SCENA.match(s)):
            cur, intro, intro_dida = None, None, False
            if s == "INTRODUZIONE":
                blocchi.append(["scena", [], "Introduzione"])
                intro_dida = True  # il prossimo paragrafo è la didascalia di apertura
            else:
                atto, scena, nome = m.groups()
                atto = "Atto " + atto.split()[-1].upper()
                blocchi.append(["scena", [], f"{atto} – {scena.lower()} – {nome.strip().capitalize()}"])
            continue

        # INTRODUZIONE: didascalia di apertura, poi testo senza etichetta detto dal personaggio nominato
        if intro_dida and cur is None:
            nuovo("dida", [], s)
            intro_dida = False
            intro = risolvi(s.split()[0].upper())
            intro = intro if intro in noti else None
            continue
        if intro:
            if s.startswith("Parte"):
                intro = None
                nuovo("dida", [], s)
            else:
                s = re.sub(r"^-\s+", "", s)
                if cur is None or blank_prima:
                    nuovo("bat", [intro], s)
                else:
                    cur[2] = _accoda(cur[2], s)
            continue

        m = re_colon.match(s)
        if m and m.group(2) and m.group(1).split(" e ")[-1] not in extra_nomi:
            m = None  # parole minuscole dopo un nome dell'elenco: è una didascalia, non una battuta
        if m:
            nomi = [risolvi(n) for n in m.group(1).split(" e ")]
            testo = " ".join(p for p in ((m.group(2) or "").strip() and f"({m.group(2).strip()})", m.group(3) and f"({m.group(3)})", m.group(4)) if p)
            nuovo("bat", nomi, testo)
            continue

        continua = cur is not None and (
            (cur[0] == "bat" and not _senza_parentesi(cur[2]))
            or (not blank_prima and (prima_lunga or s[0].islower()))
        )
        if continua:
            cur[2] = _accoda(cur[2], s)
            continue

        mn = re_nome.match(s)
        if mn:
            resto = s[mn.end():].strip()
            if re_alias:
                resto = re_alias.sub("", resto)
            if resto == "" or resto.startswith("("):
                nuovo("bat", [risolvi(mn.group(1))], resto)
                continue
            if re.match(r"[A-ZÀ-Ý“\"‘]", resto):
                nuovo("bat", [risolvi(mn.group(1))], resto)
                continue
        nuovo("dida", [], s)

    out = [f"# {titolo}", ""]
    for tipo, nomi, testo in blocchi:
        testo = re.sub(r"\s+", " ", testo).strip()
        if tipo == "scena":
            out += ["", f"## {testo}"]
        elif tipo == "dida":
            out.append(testo if testo.startswith("(") and testo.endswith(")") else f"({testo})")
        else:
            # i nomi dei personaggi in maiuscolo vengono letti male dal TTS: "ROSSI" -> "Rossi"
            # (le altre parole in maiuscolo, cioè gridate, restano come sono)
            testo = re.sub(rf"\b{N}\b", lambda mm: mm.group(0).capitalize(), testo)
            out.append(f"{'/'.join(nomi)}: {testo}")
    return "\n".join(out) + "\n"


def converti(testo_pdf: str) -> str:
    """Sceglie il formato in base all'impaginazione del PDF."""
    if re.search(r"^[A-ZÀ-Ý]{3,}(?: \d+)?(?: e \d+)?[ \t]*" + ZW, testo_pdf, re.M):
        return converti_zwsp(testo_pdf)
    return converti_due_punti(testo_pdf)


if __name__ == "__main__":
    pdf, dest = sys.argv[1], sys.argv[2]
    testo = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True, check=True).stdout
    open(dest, "w", encoding="utf-8").write(converti(testo))
    print("scritto", dest)
