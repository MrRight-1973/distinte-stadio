"""Risultati e calendario di tutte le giornate del girone, letti dalla pagina della LND (gare.lnd.it), e i numeri
di ogni squadra (anche degli avversari) calcolati da quelli.

La pagina della LND di una giornata ha in alto le partite ("18 OTT 2026 · ORE 15:30", il campo, "Turchese 0 1
Virtus Bagnoli Arre Asd" oppure "Union River VS Polisportiva Real Terme" se non è ancora giocata) e a fianco la
classifica. I nomi delle squadre si riconoscono grazie alla classifica, che li ha scritti allo stesso modo.
Le giornate si salvano in impostazioni/girone.json: sono dati pubblici (squadre, date, campi, risultati).
"""
import json
import os
import re
import time
from datetime import datetime

import archivio_cloud as cloud
from cronaca_manager import _cartella_dati, _carica_online, _leggi_file

PERCORSO_ONLINE = "impostazioni/girone.json"
MESI = ["GEN", "FEB", "MAR", "APR", "MAG", "GIU", "LUG", "AGO", "SET", "OTT", "NOV", "DIC"]
FASI = {"A": "Andata", "R": "Ritorno"}
_DATA = re.compile(r"(\d{1,2})\s+(GEN|FEB|MAR|APR|MAG|GIU|LUG|AGO|SET|OTT|NOV|DIC)[A-Z]*\.?\s+(\d{4})", re.I)
_ORA = re.compile(r"ORE\s+(\d{1,2})[:.](\d{2})", re.I)
_ETICHETTA = re.compile(r"(Andata|Ritorno)\s*[-–]\s*(\d{1,2})\s*[ªa°]?\s*giornata", re.I)
_IN_MEZZO = re.compile(r"^[\s.]*(?:(\d{1,2})\s*[-:]?\s*(\d{1,2})|VS|-)\s*$", re.I)
_RUMORE = re.compile(r"VARIAZIONE CONFERMATA|RINVIATA|SOSPESA", re.I)


# --- Lettura di una giornata -----------------------------------------------------------

def chiave(fase, numero):
    """("A", 6) -> "A06": si ordina da sola, andata prima del ritorno."""
    return f"{fase}{int(numero):02d}"


def etichetta(chiave_giornata):
    return f"{FASI.get(chiave_giornata[:1], '')} · {int(chiave_giornata[1:])}ª giornata"


def giornata_della_pagina(testo):
    """La chiave della giornata mostrata ("A06"), dalla scritta "Andata - 6ª giornata"; None se non c'è."""
    m = _ETICHETTA.search(testo or "")
    return chiave(m[1][0].upper(), m[2]) if m else None


def _squadre_nel_testo(testo, squadre):
    """[(inizio, fine, nome)] delle squadre trovate nel testo, senza sovrapposizioni (prima i nomi più lunghi).
    Un nome può essere attaccato ai gol ("Turchese0"): conta solo che prima e dopo non ci sia una lettera."""
    trovate, prese = [], []
    for nome in sorted(squadre, key=len, reverse=True):
        for m in re.finditer(r"(?<![^\W\d_])" + re.escape(nome) + r"(?![^\W\d_])", testo, re.I):
            if not any(m.start() < f and i < m.end() for i, f in prese):
                trovate.append((m.start(), m.end(), nome))
                prese.append((m.start(), m.end()))
    return sorted(trovate)


def leggi_giornata(testo, squadre):
    """Le partite della pagina: [{data, ora, campo, casa, ospite, gol_casa, gol_ospite}] (gol None se non giocata).
    Guarda solo il calendario, prima della classifica."""
    testo = (testo or "").replace("\xa0", " ")
    fine = re.search(r"\bCLASSIFICA\b", testo[200:] if len(testo) > 200 else "")
    calendario = testo[:fine.start() + 200] if fine else testo
    date = list(_DATA.finditer(calendario))
    partite = []
    for n, d in enumerate(date):
        blocco = calendario[d.end(): date[n + 1].start() if n + 1 < len(date) else len(calendario)]
        nomi = _squadre_nel_testo(blocco, squadre)
        if len(nomi) < 2:
            continue
        # le due squadre una dopo l'altra con in mezzo il risultato o "VS" (il nome del campo può
        # contenere quello della squadra di casa: "Comunale di Turchese")
        coppie = [(a, b) for a, b in zip(nomi, nomi[1:]) 
                  if a[2] != b[2] and _IN_MEZZO.match(blocco[a[1]:b[0]])]
        (i1, f1, casa), (i2, _, ospite) = coppie[0] if coppie else (nomi[-2], nomi[-1])
        ora = _ORA.search(blocco[:i1])
        prima = blocco[ora.end() if ora else 0: i1]
        campo = " ".join(r.strip(" ·-•") for r in prima.splitlines() if r.strip(" ·-•") and not _RUMORE.search(r))
        risultato = _IN_MEZZO.match(blocco[f1:i2])
        giocata = bool(risultato and risultato[1] is not None)
        gol = [int(risultato[1]), int(risultato[2])] if giocata else []
        partite.append({
            "data": f"{int(d[3]):04d}-{MESI.index(d[2][:3].upper()) + 1:02d}-{int(d[1]):02d}",
            "ora": f"{int(ora[1]):02d}:{ora[2]}" if ora else "", "campo": campo[:120],
            "casa": casa, "ospite": ospite,
            "gol_casa": gol[0] if giocata else None, "gol_ospite": gol[1] if giocata else None})
    return partite


# --- Salvataggio -------------------------------------------------------------------------

_letto = {"quando": 0.0, "dati": None}


def _percorso():
    return os.path.join(_cartella_dati(), "girone.json")


def tutti(fresco=False):
    """{gruppo squadra: {"stagione", "fonte", "aggiornato", "giornate": {"A06": [partite]}}}. Prima da Supabase
    (la aggiorna la GitHub Action "Classifiche"), al massimo una volta al minuto."""
    if not fresco and _letto["dati"] is not None and time.time() - _letto["quando"] < 60:
        return json.loads(json.dumps(_letto["dati"]))
    grezzi = None
    if cloud.attivo():
        try:
            grezzi = cloud.scarica_file(PERCORSO_ONLINE)
        except cloud.ArchivioErrore:
            grezzi = None
        if grezzi is not None:
            with open(_percorso(), "wb") as f:
                f.write(grezzi)
    try:
        dati = json.loads(grezzi if grezzi is not None else _leggi_file(_percorso(), PERCORSO_ONLINE)) or {}
    except (OSError, ValueError):
        dati = {}
    dati = dati if isinstance(dati, dict) else {}
    _letto.update(quando=time.time(), dati=dati)
    return json.loads(json.dumps(dati))


def salva(gruppo, stagione, giornate, fonte=""):
    """Unisce le giornate lette a quelle già salvate (una giornata letta sostituisce quella vecchia)."""
    dati = tutti(fresco=True)
    vecchio = dati.get(gruppo) or {}
    if vecchio.get("stagione") != stagione:
        vecchio = {}
    dati[gruppo] = {"stagione": stagione, "fonte": fonte or vecchio.get("fonte", ""),
                    "aggiornato": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "giornate": {**(vecchio.get("giornate") or {}), **giornate}}
    with open(_percorso(), "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1)
    _carica_online(PERCORSO_ONLINE, _percorso(), "application/json")
    _letto.update(quando=time.time(), dati=dati)
    return dati[gruppo]


def completa(partite):
    return bool(partite) and all(p.get("gol_casa") is not None for p in partite)


# --- Numeri delle squadre ------------------------------------------------------------------

def _vuoto():
    return {"g": 0, "v": 0, "n": 0, "p": 0, "gf": 0, "gs": 0, "pt": 0}


def _aggiungi(conto, fatti, subiti):
    esito = "v" if fatti > subiti else "n" if fatti == subiti else "p"
    conto["g"] += 1
    conto[esito] += 1
    conto["gf"] += fatti
    conto["gs"] += subiti
    conto["pt"] += {"v": 3, "n": 1, "p": 0}[esito]
    return esito.upper()


def partite_di(giornate, squadra):
    """[(chiave giornata, partita)] di una squadra, in ordine di giornata."""
    return [(k, p) for k in sorted(giornate) for p in giornate[k] if squadra in (p["casa"], p["ospite"])]


def scheda_squadra(giornate, squadra, ultime=5):
    """Numeri di una squadra dai risultati: totale, in casa, fuori, ultime partite (V/N/P), prossima partita."""
    totale, casa, fuori, forma, giocate, prossima = _vuoto(), _vuoto(), _vuoto(), [], [], None
    for k, p in partite_di(giornate, squadra):
        in_casa = p["casa"] == squadra
        if p.get("gol_casa") is None:
            prossima = prossima or (k, p)
            continue
        fatti, subiti = (p["gol_casa"], p["gol_ospite"]) if in_casa else (p["gol_ospite"], p["gol_casa"])
        esito = _aggiungi(totale, fatti, subiti)
        _aggiungi(casa if in_casa else fuori, fatti, subiti)
        forma.append(esito)
        giocate.append((k, p, esito))
    g = totale["g"] or 1
    return {"totale": totale, "casa": casa, "fuori": fuori, "forma": forma[-ultime:],
            "media_fatti": round(totale["gf"] / g, 2), "media_subiti": round(totale["gs"] / g, 2),
            "senza_subire": sum(1 for _, p, _ in giocate
                                if (p["gol_ospite"] if p["casa"] == squadra else p["gol_casa"]) == 0),
            "giocate": giocate, "prossima": prossima}


def squadre_del_girone(giornate):
    return sorted({p[lato] for partite in giornate.values() for p in partite for lato in ("casa", "ospite")})
