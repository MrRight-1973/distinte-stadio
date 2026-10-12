"""Nomi "parlanti" per i file generati: tipo, data e squadre della gara.

Esempio: Resoconto_2026-10-11_Due-Stelle_vs_Azzurra-Duecarrare.pdf
"""
import re
import unicodedata

# Sigle societarie che allungano il nome senza aiutare a riconoscere la squadra
_SIGLE = {"ASD", "SSD", "AS", "AC", "US", "SS", "AP", "FC", "SC", "SRL", "ARL", "CALCIO"}


def _squadra(nome):
    parole = []
    for parola in str(nome or "").split():
        pulita = re.sub(r"[^\w]", "", parola)
        if not pulita or pulita.upper() in _SIGLE or ("." in parola and len(pulita) <= 4):
            continue
        parole.append(pulita.capitalize())
    testo = "-".join(parole)
    return unicodedata.normalize("NFKD", testo).encode("ascii", "ignore").decode() or ""


def _data(testo):
    """'11/10/2026 ore 15:30' -> '2026-10-11'; '11/10/26' -> '2026-10-11'; altrimenti ''."""
    m = re.search(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", str(testo or ""))
    if not m:
        return ""
    g, mese, anno = m.groups()
    if len(anno) == 2:
        anno = "20" + anno
    return f"{anno}-{int(mese):02d}-{int(g):02d}"


def nome_file_gara(tipo, data="", casa="", ospite="", estensione="pdf"):
    parti = [tipo, _data(data)]
    squadre = [s for s in (_squadra(casa), _squadra(ospite)) if s]
    parti.append("_vs_".join(squadre))
    return "_".join(p for p in parti if p) + f".{estensione}"
