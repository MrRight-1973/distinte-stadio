"""Lettura del calendario gare LND (PDF del Comitato): giornate di andata e ritorno con data e ora, e
l'elenco dei campi di gioco. Serve a preparare in anticipo le distinte vuote di tutte le partite.

Il PDF del Comitato è scritto con un carattere a passo fisso: si ricostruiscono le righe mettendo ogni
carattere nella sua colonna, così le colonne del calendario (tre giornate affiancate) e quelle dell'elenco
campi si separano per posizione.
"""
import re
from statistics import median

ANDATA, RITORNO = "andata", "ritorno"


def _righe(pagina):
    """Le righe di testo della pagina, con gli spazi che rispettano le colonne del modulo."""
    testo = pagina.get_textpage()
    caratteri = []
    for i in range(testo.count_chars()):
        c = testo.get_text_range(i, 1)
        if c in ("\r", "\n", ""):
            continue
        sinistra, sotto, destra, sopra = testo.get_charbox(i)
        caratteri.append((round(sotto), sinistra, c))
    if not caratteri:
        return []
    caratteri.sort(key=lambda x: (-x[0], x[1]))
    # passo del carattere: distanza tipica fra due caratteri consecutivi della stessa riga
    passi = [b[1] - a[1] for a, b in zip(caratteri, caratteri[1:]) if a[0] == b[0] and 0 < b[1] - a[1] < 15]
    passo = median(passi) if passi else 5
    inizio = min(c[1] for c in caratteri)
    righe, attuale, y = [], {}, None
    for riga_y, x, c in caratteri:
        if y is not None and abs(riga_y - y) > 2:
            righe.append(attuale)
            attuale = {}
        y = riga_y
        if c.strip():
            attuale[round((x - inizio) / passo)] = c
    righe.append(attuale)
    return ["".join(r.get(i, " ") for i in range(max(r) + 1)) if r else "" for r in righe]


def _data(testo):
    g, m, a = (int(x) for x in testo.split("/"))
    return f"{2000 + a if a < 100 else a:04d}-{m:02d}-{g:02d}"


def _ora(testo):
    h, m = re.split(r"[:.]", testo)
    return f"{int(h):02d}:{m}"


def leggi_calendario(contenuto):
    """Dal PDF: {"titolo", "partite": [{giornata, fase, data, ora, casa, ospite}], "campi": {società: {...}}}."""
    import pypdfium2 as pdfium
    righe, titolo = [], ""
    for pagina in pdfium.PdfDocument(contenuto):
        righe += _righe(pagina)
        # il titolo ("1^ CATEGORIA Girone e") è scritto con un altro carattere: si prende dal testo semplice
        for riga in pagina.get_textpage().get_text_range().splitlines():
            if not titolo and "CATEGORIA" in riga.upper() and "|" not in riga:
                titolo = " ".join(riga.split())
    partite, campi = [], {}
    blocchi, colonne_campi = [], None
    for riga in righe:
        date = re.findall(r"ANDATA:\s*(\d{1,2}/\d{1,2}/\d{2,4}).*?RITORNO:\s*(\d{1,2}/\d{1,2}/\d{2,4})", riga)
        if date:
            blocchi = [{"andata": a, "ritorno": r, "colonna": riga.find(f"ANDATA: {a}")} for a, r in date]
            continue
        ore = re.findall(r"ORE\.*:\s*(\d{1,2}[:.]\d{2})\s*!\s*(\d+)\s*G\s*I\s*O\s*R\s*N\s*A\s*T\s*A\s*!\s*"
                         r"ORE\.*:\s*(\d{1,2}[:.]\d{2})", riga)
        if ore and len(ore) == len(blocchi):
            for b, (ora_a, giornata, ora_r) in zip(blocchi, ore):
                b.update(ora_andata=_ora(ora_a), ora_ritorno=_ora(ora_r), giornata=int(giornata))
            continue
        if "DENOMINAZIONE" in riga and "LOCALITA" in riga:
            colonne_campi = {n: riga.find(n) for n in ("CAMPO|", "DENOMINAZIONE", "LOCALITA", "ORA", "INDIRIZZO",
                                                        "TELEFONO")}
            continue
        if colonne_campi and riga.lstrip().startswith("|"):
            societa = riga[:colonne_campi["CAMPO|"]].strip(" |")
            if societa and not set(societa) <= set("-|"):
                pezzo = lambda da, a: re.sub(r"\s+", " ", riga[colonne_campi[da]:colonne_campi[a]]).strip(" |")
                campi[societa] = {"campo": pezzo("DENOMINAZIONE", "LOCALITA"),
                                  "localita": pezzo("LOCALITA", "ORA"),
                                  "indirizzo": pezzo("INDIRIZZO", "TELEFONO")}
            continue
        # righe delle partite: "I CASA - OSPITE I I CASA - OSPITE I ..." una per ogni giornata del blocco
        if blocchi and all("giornata" in b for b in blocchi) and riga.lstrip().startswith("I ") and " - " in riga:
            pezzi = [p.strip() for p in re.split(r"\s+I\s+I\s+", riga.strip()[1:-1].strip())]
            if len(pezzi) != len(blocchi):
                continue
            for b, pezzo in zip(blocchi, pezzi):
                if " - " not in pezzo:
                    continue
                casa, ospite = (" ".join(x.split()) for x in pezzo.split(" - ", 1))
                partite.append({"giornata": b["giornata"], "fase": ANDATA, "data": _data(b["andata"]),
                                "ora": b["ora_andata"], "casa": casa, "ospite": ospite})
                partite.append({"giornata": b["giornata"], "fase": RITORNO, "data": _data(b["ritorno"]),
                                "ora": b["ora_ritorno"], "casa": ospite, "ospite": casa})
    partite.sort(key=lambda p: (p["data"], p["casa"]))
    return {"titolo": titolo, "partite": partite, "campi": campi}


def squadre(calendario):
    return sorted({p["casa"] for p in calendario["partite"]} | {p["ospite"] for p in calendario["partite"]})


def _parole(nome):
    return set(re.sub(r"[^A-Z0-9 ]", " ", nome.upper()).split()) - {"ASD", "A", "S", "D", "SSD", "ARL", "US", "AC"}


def nostra_squadra(calendario, nome_societa):
    """La squadra del calendario che somiglia di più al nome della società (o "" se nessuna)."""
    nostre = _parole(nome_societa)
    punteggi = [(len(_parole(s) & nostre) / max(len(_parole(s)), 1), s) for s in squadre(calendario)]
    migliore = max(punteggi, default=(0, ""))
    return migliore[1] if migliore[0] >= 0.5 else ""


def partite_di(calendario, squadra, dal=""):
    """Le partite della squadra, dalla data indicata in poi, in ordine di data (non di giornata: i recuperi e le
    partite spostate finiscono al loro posto)."""
    return sorted((p for p in calendario["partite"] if squadra in (p["casa"], p["ospite"]) and p["data"] >= dal),
                  key=lambda p: (p["data"], p.get("ora", "")))


def distinte_da_calendario(calendario, nostra, partite, modello, distinte):
    """(righe da mostrare, distinte nuove, per ogni riga l'id della distinta che c'è già o quella nuova) per le
    partite scelte. modello: i dati uguali per tutte (gruppo,
    squadra come si scrive in distinta, competizione, ruoli, autore). Una partita che ha già la sua distinta
    (stesso gruppo, data e avversario) si salta."""
    gia = {(d.get("gruppo"), d.get("data"), " ".join(str(d.get("avversario", "")).upper().split())): d.get("id")
           for d in distinte.values()}
    squadra = modello["squadra"]
    righe, nuove, per_riga = [], [], []
    for p in partite:
        in_casa = p["casa"] == nostra
        avversario = p["ospite"] if in_casa else p["casa"]
        campo = calendario["campi"].get(p["casa"], {})
        presente = gia.get((modello["gruppo"], p["data"], avversario))
        giornata = f"{p['giornata']}ª {p['fase']}"
        g, m, a = p["data"][8:10], p["data"][5:7], p["data"][:4]
        righe.append({"Giornata": giornata, "Data": f"{g}/{m}/{a}", "Ore": p["ora"],
                      "Avversario": f"{'🏠' if in_casa else '🚌'} {avversario}", "Campo": campo.get("localita", ""),
                      "Distinta": "già presente" if presente else "da creare"})
        if presente:
            per_riga.append(presente)
        else:
            nuove.append({**modello, "in_casa": in_casa, "avversario": avversario,
                          "casa": squadra if in_casa else avversario, "ospite": avversario if in_casa else squadra,
                          "data": p["data"], "ora": p["ora"], "localita": campo.get("localita", ""),
                          "campo": campo.get("campo", ""), "giornata": giornata, "giocatori": [], "panchina": []})
            per_riga.append(nuove[-1])
    return righe, nuove, per_riga
