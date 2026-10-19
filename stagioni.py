"""Anno sportivo, gruppi squadra e competizioni impostati dalla segreteria (sezione ⚙️ Opzioni).

Tre livelli: anno sportivo → gruppo squadra (es. Prima Squadra, Under 17: una rosa ciascuno)
→ competizioni del gruppo (campionato, coppa...). Il campionato non si legge più dalle distinte: si sceglie dall'elenco dell'anno sportivo in corso,
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


def _gruppi(elenco):
    """[{"gruppo", "competizioni": [...]}]; il vecchio formato (solo campionati) diventa un gruppo per campionato."""
    gruppi = []
    for voce in elenco or []:
        if isinstance(voce, str):
            voce = {"gruppo": voce, "competizioni": [voce]}
        competizioni = [c for c in voce.get("competizioni") or [] if c]
        if voce.get("gruppo") and competizioni:
            gruppi.append({"gruppo": voce["gruppo"], "competizioni": competizioni})
    return gruppi


def impostazioni_stagioni():
    """{"corrente": "2026/27", "stagioni": {"2026/27": [{"gruppo": "Prima Squadra",
    "competizioni": ["Prima Categoria girone E", "Coppa Veneto"]}, ...]}}"""
    try:
        salvate = json.loads(_leggi_file(_percorso(), PERCORSO_ONLINE))
    except (OSError, ValueError):
        salvate = {}
    stagioni = {s: _gruppi(elenco) for s, elenco in (salvate.get("stagioni") or {}).items()}
    return {"corrente": salvate.get("corrente") or stagione_di_oggi(), "stagioni": stagioni}


def _pulito(testo):
    return re.sub(r"\s+", " ", str(testo or "")).strip()


def salva_stagioni(corrente, stagioni):
    """stagioni: {anno: [{"gruppo", "competizioni"}]}. Una competizione sta in un solo gruppo."""
    pulite = {}
    for s, gruppi in stagioni.items():
        uniti, viste = {}, set()
        for g in _gruppi(gruppi):
            nome = _pulito(g["gruppo"])
            for c in map(_pulito, g["competizioni"]):
                if c and c.lower() not in viste:
                    viste.add(c.lower())
                    chiave = next((k for k in uniti if k.lower() == (nome or c).lower()), nome or c)
                    uniti.setdefault(chiave, []).append(c)
        pulite[s] = [{"gruppo": k, "competizioni": v} for k, v in uniti.items()]
    with open(_percorso(), "w", encoding="utf-8") as f:
        json.dump({"corrente": corrente, "stagioni": pulite}, f, ensure_ascii=False, indent=1)
    _carica_online(PERCORSO_ONLINE, _percorso(), "application/json")


def gruppi_correnti():
    """(anno sportivo in corso, i suoi gruppi squadra con le competizioni)."""
    imp = impostazioni_stagioni()
    return imp["corrente"], imp["stagioni"].get(imp["corrente"], [])


def gruppo_di(campionato, stagione=None):
    """Il gruppo squadra di una competizione: cercato nell'anno indicato, poi negli altri.
    Se non è in nessun gruppo, il gruppo è la competizione stessa."""
    if not campionato:
        return ""
    stagioni = impostazioni_stagioni()["stagioni"]
    ordine = ([stagione] if stagione in stagioni else []) + sorted(stagioni, reverse=True)
    for s in ordine:
        for g in stagioni[s]:
            if campionato in g["competizioni"]:
                return g["gruppo"]
    return campionato


def campionati_correnti():
    """(anno sportivo in corso, tutte le competizioni dei suoi gruppi)."""
    stagione, gruppi = gruppi_correnti()
    return stagione, [c for g in gruppi for c in g["competizioni"]]
