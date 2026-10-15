"""Anno sportivo e campionati/categorie impostati dalla segreteria (sezione ⚙️ Opzioni).

Il campionato non si legge più dalle distinte: si sceglie dall'elenco dell'anno sportivo in corso,
così le partite di più squadre della società restano separate in archivio e nelle statistiche.
Salvato in impostazioni/stagioni.json (disco dell'app e Supabase), uguale per tutti i dispositivi.
"""
import json
import os
import re
from datetime import date

from cronaca_manager import _cartella_dati, _carica_online, _leggi_file

PERCORSO_ONLINE = "impostazioni/stagioni.json"


def stagione_da_data(data):
    """Anno sportivo della data "dd/mm/yyyy ...": da luglio a giugno ("12/10/2026" -> "2026/27"); "" se manca."""
    numeri = re.findall(r"\d+", str(data or ""))
    if len(numeri) < 3:
        return ""
    mese, anno = int(numeri[1]), int(numeri[2]) + (2000 if len(numeri[2]) == 2 else 0)
    inizio = anno if mese >= 7 else anno - 1
    return f"{inizio}/{(inizio + 1) % 100:02d}"


def stagione_di_oggi():
    oggi = date.today()
    return stagione_da_data(f"{oggi.day}/{oggi.month}/{oggi.year}")


def stagione_partita(partita):
    """Anno sportivo di una partita: quello scelto alla pubblicazione, altrimenti dalla data."""
    return (partita or {}).get("stagione") or stagione_da_data((partita or {}).get("data"))


def normalizza_stagione(testo):
    """"2026/27", "2026-2027", "26/27" -> "2026/27"; "" se non è un anno sportivo."""
    numeri = re.findall(r"\d+", str(testo or ""))
    if not numeri:
        return ""
    inizio = int(numeri[0]) + (2000 if len(numeri[0]) == 2 else 0)
    return f"{inizio}/{(inizio + 1) % 100:02d}" if 2000 <= inizio <= 2100 else ""


def _percorso():
    return os.path.join(_cartella_dati(), "stagioni.json")


def impostazioni_stagioni():
    """{"corrente": "2026/27", "stagioni": {"2026/27": ["Prima Categoria girone E", ...]}}"""
    try:
        salvate = json.loads(_leggi_file(_percorso(), PERCORSO_ONLINE))
    except (OSError, ValueError):
        salvate = {}
    stagioni = {s: [c for c in elenco if c] for s, elenco in (salvate.get("stagioni") or {}).items()}
    return {"corrente": salvate.get("corrente") or stagione_di_oggi(), "stagioni": stagioni}


def salva_stagioni(corrente, stagioni):
    pulite = {}
    for s, elenco in stagioni.items():
        visti = []
        for c in elenco:
            c = re.sub(r"\s+", " ", str(c or "")).strip()
            if c and c.lower() not in (v.lower() for v in visti):
                visti.append(c)
        pulite[s] = visti
    with open(_percorso(), "w", encoding="utf-8") as f:
        json.dump({"corrente": corrente, "stagioni": pulite}, f, ensure_ascii=False, indent=1)
    _carica_online(PERCORSO_ONLINE, _percorso(), "application/json")


def campionati_correnti():
    """(anno sportivo in corso, i suoi campionati)."""
    imp = impostazioni_stagioni()
    return imp["corrente"], imp["stagioni"].get(imp["corrente"], [])
