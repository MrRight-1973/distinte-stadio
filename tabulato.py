"""Tabulato calciatori dilettanti (PDF scaricato dal portale FIGC-LND della società): per ogni tesserato
matricola, cognome e nome, data di nascita. Serve a completare l'anagrafica e ad aggiungere chi manca.

Il codice fiscale nel tabulato si usa solo per separare il cognome dal nome (es. "D ALESSANDRO LORENZO",
"FOLTACHE SIMONE DANIELE") e non si salva: in anagrafica teniamo solo i dati che servono alla distinta.
"""
import re
import unicodedata

_RIGA = re.compile(r"^(?P<matricola>\d{5,9})\s+(?P<nome>.+?)\s+Calcio\b.*?(?P<nascita>\d{2}/\d{2}/\d{4})")
_CF = re.compile(r"^(?P<cf>[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b")
VOCALI = set("AEIOU")


def _lettere(testo):
    testo = unicodedata.normalize("NFKD", testo.upper())
    return "".join(c for c in testo if "A" <= c <= "Z")


def _codice_cognome(cognome):
    lettere = _lettere(cognome)
    consonanti = [c for c in lettere if c not in VOCALI]
    vocali = [c for c in lettere if c in VOCALI]
    return ("".join(consonanti + vocali) + "XXX")[:3]


def _codice_nome(nome):
    lettere = _lettere(nome)
    consonanti = [c for c in lettere if c not in VOCALI]
    if len(consonanti) >= 4:
        return consonanti[0] + consonanti[2] + consonanti[3]
    vocali = [c for c in lettere if c in VOCALI]
    return ("".join(consonanti + vocali) + "XXX")[:3]


def dividi_con_codice_fiscale(nome_completo, cf):
    """("D ALESSANDRO LORENZO", "DLSLNZ...") -> ("D ALESSANDRO", "LORENZO"). Senza codice fiscale (o se
    nessuna divisione torna) il nome è l'ultima parola."""
    parole = nome_completo.split()
    if len(parole) < 2:
        return nome_completo, ""
    if cf:
        for k in range(1, len(parole)):
            cognome, nome = " ".join(parole[:k]), " ".join(parole[k:])
            if _codice_cognome(cognome) == cf[:3] and _codice_nome(nome) == cf[3:6]:
                return cognome, nome
    return " ".join(parole[:-1]), parole[-1]


def leggi_tabulato(contenuto):
    """[{matricola, cognome, nome, nascita (yyyy-mm-dd)}] dal PDF del tabulato."""
    import pypdfium2 as pdfium
    righe = []
    documento = pdfium.PdfDocument(contenuto)
    try:
        for pagina in documento:
            righe += pagina.get_textpage().get_text_range().splitlines()
    finally:
        documento.close()
    tesserati, ultimo = [], None
    for riga in righe:
        riga = riga.strip()
        trovata = _RIGA.match(riga)
        if trovata:
            g, m, a = trovata["nascita"].split("/")
            ultimo = {"matricola": trovata["matricola"], "nome_completo": " ".join(trovata["nome"].split()),
                      "nascita": f"{a}-{m}-{g}"}
            tesserati.append(ultimo)
            continue
        cf = _CF.match(riga)
        if cf and ultimo is not None and "cf" not in ultimo:
            ultimo["cf"] = cf["cf"]
    risultato = []
    for t in tesserati:
        cognome, nome = dividi_con_codice_fiscale(t["nome_completo"], t.get("cf", ""))
        risultato.append({"matricola": t["matricola"], "cognome": cognome, "nome": nome, "nascita": t["nascita"]})
    return risultato
