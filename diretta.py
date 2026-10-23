"""Diretta sulla pagina spettatori: risultato, tempo di gioco, gol, cartellini e sostituzioni.

A ogni salvataggio della cronaca si scrive live.json nello spazio pubblico di Supabase (solo se è
cambiato qualcosa). La pagina lo rilegge ogni pochi secondi e lo mostra solo se riguarda la distinta
pubblicata in quel momento. Nel file vanno solo gli eventi con i giocatori scelti dai menu: niente
commenti, foto o note vocali.
"""
import hashlib
import json
import time
from datetime import datetime, timezone

import archivio_cloud as cloud

NOME_FILE = "live.json"
_ultimo = {"firma": None, "errore": 0.0}
PAUSA_DOPO_ERRORE = 60  # secondi: con Supabase giù non si rallenta ogni salvataggio


def dati_diretta(cronaca):
    from cronaca_manager import eventi_correnti, fase_in_corso, punteggio, stato_gara

    distinta = cronaca.get("distinta") or {}
    if not distinta or cronaca.get("diretta") is False:
        return {"distinta": None}
    fase = fase_in_corso(cronaca)
    # I commenti scritti nelle note non vanno in pubblico: senza giocatore scelto dal menu resta vuoto
    senza_testo = {**cronaca, "note": [{**n, "testo": ""} for n in cronaca.get("note") or []]}
    # I nomi come nella distinta pubblica (giovanili: cognome e iniziale; senza consenso: niente nome)
    from nomi_pubblici import evento_pubblico, giorno_partita, modo_partita, persone_anagrafica
    modo = modo_partita(distinta.get("info_gara"))
    persone = persone_anagrafica()
    giorno = giorno_partita(distinta.get("info_gara"))
    anni = {str(g.get("GIOCATORE") or "").strip(): g.get("ANNO") for lato in ("casa", "ospite")
            for g in (distinta.get(lato) or {}).get("giocatori") or [] if str(g.get("GIOCATORE") or "").strip()}
    eventi = []
    for e in eventi_correnti(senza_testo):
        if e.get("tipo") not in ("gol", "ammonizione", "espulsione", "sostituzione"):
            continue
        if e.get("squadra") not in ("casa", "ospite"):
            continue
        eventi.append({"tipo": e["tipo"], "squadra": e["squadra"], "minuto": str(e.get("minuto") or ""),
                       "giocatore": evento_pubblico(e.get("giocatore"), modo, persone, anni, giorno)[:80], "nota": str(e.get("nota") or "")[:40]})
    gol = punteggio(cronaca)
    return {
        "distinta": distinta.get("aggiornato"),
        "stato": stato_gara(cronaca),
        "fase": fase[0] if fase else None,
        "inizio": fase[2] if fase else None,  # secondi epoch: la pagina calcola il minuto da sola
        "durata": int(cronaca.get("durata_tempo") or 45),
        "gol": [gol[0], gol[1]],
        "eventi": eventi,
    }


def pubblica_diretta(cronaca):
    """Aggiorna live.json se è cambiato; non solleva mai eccezioni (la cronaca non deve bloccarsi)."""
    try:
        if not cloud.attivo():
            return
        dati = dati_diretta(cronaca)
        firma = hashlib.sha1(json.dumps(dati, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if firma == _ultimo["firma"] or time.time() - _ultimo["errore"] < PAUSA_DOPO_ERRORE:
            return
        dati["aggiornato"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if cloud.carica_pubblico(NOME_FILE, json.dumps(dati, ensure_ascii=False).encode("utf-8")):
            _ultimo["firma"] = firma
        else:
            _ultimo["errore"] = time.time()
    except Exception:
        _ultimo["errore"] = time.time()


def url_diretta():
    return cloud.url_pubblico(NOME_FILE)
