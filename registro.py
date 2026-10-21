"""Registro delle modifiche: chi ha cambiato cosa, e quando, in anagrafica, distinte, allenamenti e utenti.

Un file al mese nello spazio privato di Supabase (registro/registro_<aaaa-mm>.json), una voce per modifica:
{"quando", "chi", "cosa", "dettaglio"}. Si segnano solo i nomi dei campi cambiati, mai i valori (niente numeri
di documento o date di nascita copiati qui). Lo vede solo l'admin; il backup settimanale lo include.
Un problema del registro non deve mai bloccare un salvataggio: ogni errore viene ignorato.
"""
import json
import os
from datetime import date, datetime

from cronaca_manager import _cartella_dati, _carica_online, _leggi_file

ETICHETTE_CAMPI = {
    "cognome": "cognome", "nome": "nome", "matricola": "matricola", "nascita": "data di nascita",
    "anno_nascita": "anno di nascita", "documento_tipo": "tipo documento", "documento_numero": "numero documento",
    "documento_rilascio": "rilascio documento", "documento_scadenza": "scadenza documento",
    "certificato_scadenza": "scadenza certificato", "gruppi": "squadra", "tipo": "tipo",
}


def _mese(giorno=None):
    return (giorno or date.today()).strftime("%Y-%m")


def _percorsi(mese):
    nome = f"registro_{mese}.json"
    return os.path.join(_cartella_dati(), nome), f"registro/{nome}"


def chi():
    """L'utente collegato all'app ("" fuori dall'app, ad esempio nei test o nelle Action)."""
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx() is None:
            return ""
        import streamlit as st
        return str(st.session_state.get("utente") or "segreteria")
    except Exception:  # noqa: BLE001 - il registro non deve mai fermare l'app
        return ""


def voci_del_mese(mese=None):
    locale, online = _percorsi(mese or _mese())
    try:
        voci = json.loads(_leggi_file(locale, online)) or []
    except (OSError, ValueError):
        return []
    return voci if isinstance(voci, list) else []


def segna(cosa, dettaglio="", utente=None):
    """Aggiunge una voce al registro del mese. Non solleva mai errori."""
    try:
        mese = _mese()
        voci = voci_del_mese(mese)  # riletto appena prima di scrivere
        voci.append({"quando": datetime.now().strftime("%Y-%m-%d %H:%M"), "chi": utente if utente is not None else chi(),
                     "cosa": cosa, "dettaglio": dettaglio})
        locale, online = _percorsi(mese)
        with open(locale, "w", encoding="utf-8") as f:
            json.dump(voci, f, ensure_ascii=False, indent=0)
        _carica_online(online, locale, "application/json")
    except Exception:  # noqa: BLE001
        pass


def campi_cambiati(prima, dopo):
    """I nomi (leggibili) dei campi diversi tra due schede, senza i valori."""
    chiavi = [k for k in dict.fromkeys(list(prima) + list(dopo)) if k != "id"]
    return [ETICHETTE_CAMPI.get(k, k) for k in chiavi if (prima.get(k) or "") != (dopo.get(k) or "")]


def mesi_disponibili(quanti=12, oggi=None):
    """Gli ultimi mesi ("aaaa-mm"), dal più recente."""
    giorno = oggi or date.today()
    anno, mese = giorno.year, giorno.month
    mesi = []
    for _ in range(quanti):
        mesi.append(f"{anno}-{mese:02d}")
        anno, mese = (anno, mese - 1) if mese > 1 else (anno - 1, 12)
    return mesi
