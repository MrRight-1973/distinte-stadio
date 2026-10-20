"""Presenze agli allenamenti, un file per anno sportivo nello spazio privato di Supabase.

presenze/<stagione>.json = {gruppo: {"yyyy-mm-dd": {id_ragazzo: stato}}}, con lo stato in STATI.
I ragazzi sono indicati con l'id della loro scheda in anagrafica, così un cambio di nome non perde lo storico.
"""
import json
import os
import re

from cronaca_manager import _cartella_dati, _carica_online, _leggi_file

STATI = ["presente", "differenziato", "infortunato", "assente", "giustificato"]
IN_CAMPO = ("presente", "differenziato")  # contano come presenze


def _nome_file(stagione):
    return "presenze_" + re.sub(r"[^0-9A-Za-z]+", "-", str(stagione)).strip("-") + ".json"


def _percorsi(stagione):
    nome = _nome_file(stagione)
    return os.path.join(_cartella_dati(), nome), f"presenze/{nome}"


def presenze_stagione(stagione):
    locale, online = _percorsi(stagione)
    try:
        dati = json.loads(_leggi_file(locale, online)) or {}
    except (OSError, ValueError):
        dati = {}
    return dati if isinstance(dati, dict) else {}


def presenze_gruppo(stagione, gruppo):
    """{data: {id_ragazzo: stato}} di un gruppo squadra."""
    return presenze_stagione(stagione).get(gruppo) or {}


def salva_allenamento(stagione, gruppo, giorno, segnati):
    """Scrive (o sostituisce) l'allenamento di un giorno; rilegge il file appena prima di scrivere,
    così due allenatori di squadre diverse non si cancellano a vicenda."""
    segnati = {i: s for i, s in segnati.items() if s in STATI}
    dati = presenze_stagione(stagione)
    allenamenti = dati.setdefault(gruppo, {})
    if segnati:
        allenamenti[giorno] = segnati
    else:
        allenamenti.pop(giorno, None)
    _scrivi(stagione, dati)


def elimina_allenamento(stagione, gruppo, giorno):
    salva_allenamento(stagione, gruppo, giorno, {})


def _scrivi(stagione, dati):
    locale, online = _percorsi(stagione)
    with open(locale, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1)
    _carica_online(online, locale, "application/json")


def sposta_allenamento(stagione, gruppo, giorno, nuovo_giorno, segnati):
    """Corregge un allenamento salvato, anche cambiandone la data (sostituisce quello del nuovo giorno)."""
    dati = presenze_stagione(stagione)
    allenamenti = dati.setdefault(gruppo, {})
    allenamenti.pop(giorno, None)
    allenamenti[nuovo_giorno] = {i: s for i, s in segnati.items() if s in STATI}
    _scrivi(stagione, dati)


def rinomina_gruppo(stagione, vecchio, nuovo):
    dati = presenze_stagione(stagione)
    if vecchio in dati:
        dati[nuovo] = {**dati.get(nuovo, {}), **dati.pop(vecchio)}
        _scrivi(stagione, dati)


def statistiche(allenamenti, dal=None, al=None):
    """{id_ragazzo: {uno per stato, "segnati", "percentuale"}} sugli allenamenti tra le due date (yyyy-mm-dd,
    comprese). La percentuale conta presenti e differenziati sulle volte in cui il ragazzo è stato segnato."""
    conti = {}
    for giorno, segnati in allenamenti.items():
        if (dal and giorno < dal) or (al and giorno > al):
            continue
        for id_ragazzo, stato in segnati.items():
            voce = conti.setdefault(id_ragazzo, {s: 0 for s in STATI})
            if stato in STATI:
                voce[stato] += 1
    for voce in conti.values():
        voce["segnati"] = sum(voce[s] for s in STATI)
        voce["percentuale"] = round(100 * sum(voce[s] for s in IN_CAMPO) / voce["segnati"]) if voce["segnati"] else 0
    return conti
