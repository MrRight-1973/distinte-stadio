"""Archivio online su Supabase: le partite nel database, foto e note vocali nello spazio file.

Si attiva con SUPABASE_URL e SUPABASE_KEY nei secrets (la chiave segreta "service_role" o
"sb_secret_...": resta solo sul server dell'app). Senza, l'app lavora come prima solo sul disco.
Il disco resta comunque la copia di lavoro veloce; l'archivio online è quella che sopravvive
ai riavvii. Se Supabase non risponde, l'errore resta in ultimo_errore() e la copia online si
riallinea al salvataggio successivo.
"""
import requests

TABELLA = "partite"
SPAZIO = "archivio"  # nome dello spazio file (bucket) privato
TIMEOUT = 15

_config = {"url": "", "key": ""}
_stato = {"errore": None}


class ArchivioErrore(Exception):
    pass


def configura(url, key):
    _config["url"] = str(url or "").strip().rstrip("/")
    _config["key"] = str(key or "").strip()


def attivo():
    return bool(_config["url"] and _config["key"])


def ultimo_errore():
    return _stato["errore"]


def _intestazioni(extra=None):
    key = _config["key"]
    h = {"apikey": key}
    if not key.startswith("sb_"):  # le chiavi "legacy" (JWT) vanno anche in Authorization
        h["Authorization"] = f"Bearer {key}"
    h.update(extra or {})
    return h


def _chiama(metodo, percorso, ammetti_404=False, intestazioni=None, **kwargs):
    try:
        r = requests.request(metodo, f"{_config['url']}{percorso}", headers=_intestazioni(intestazioni),
                             timeout=TIMEOUT, **kwargs)
    except requests.RequestException as e:
        _stato["errore"] = "Archivio online non raggiungibile."
        raise ArchivioErrore(_stato["errore"]) from e
    if ammetti_404 and (r.status_code == 404 or (r.status_code == 400 and "not found" in r.text.lower())):
        _stato["errore"] = None  # lo spazio file risponde 400 "Object not found" per un file assente
        return r
    if r.status_code in (401, 403):
        _stato["errore"] = "Supabase rifiuta la chiave: controlla SUPABASE_KEY (serve la chiave segreta)."
    elif r.status_code >= 400:
        _stato["errore"] = f"Archivio online: errore {r.status_code} ({r.text[:200]})"
    else:
        _stato["errore"] = None
        return r
    raise ArchivioErrore(_stato["errore"])


# --- Partite --------------------------------------------------------------------

def salva_partita(cronaca, corrente, gol=(None, None)):
    p = cronaca.get("partita") or {}
    riga = {
        "id": cronaca["id"],
        "casa": p.get("casa", ""),
        "ospite": p.get("ospite", ""),
        "campionato": p.get("campionato", ""),
        "data": p.get("data", ""),
        "gol_casa": gol[0],
        "gol_ospite": gol[1],
        "corrente": bool(corrente),
        "dati": cronaca,
        "aggiornato": cronaca.get("aggiornato"),
    }
    _chiama("POST", f"/rest/v1/{TABELLA}", json=riga,
            intestazioni={"Prefer": "resolution=merge-duplicates,return=minimal"})


def partita_corrente():
    """La cronaca segnata come in corso, oppure None."""
    r = _chiama("GET", f"/rest/v1/{TABELLA}",
                params={"corrente": "eq.true", "order": "aggiornato.desc", "limit": "1", "select": "dati"})
    righe = r.json()
    return righe[0]["dati"] if righe else None


def elenco_partite(esclusa=""):
    """Tutte le partite salvate tranne quella aperta (esclusa), dalla più recente."""
    r = _chiama("GET", f"/rest/v1/{TABELLA}", params={
        "id": f"neq.{esclusa}", "order": "aggiornato.desc",
        "select": "id,casa,ospite,campionato,data,gol_casa,gol_ospite,aggiornato"})
    return r.json()


def leggi_partita(id_partita):
    r = _chiama("GET", f"/rest/v1/{TABELLA}", params={"id": f"eq.{id_partita}", "select": "dati"})
    righe = r.json()
    return righe[0]["dati"] if righe else None


def elimina_partita(id_partita):
    _chiama("DELETE", f"/rest/v1/{TABELLA}", params={"id": f"eq.{id_partita}"})


def togli_corrente_alle_altre(id_partita):
    """Una sola partita in corso: le altre passano in archivio."""
    _chiama("PATCH", f"/rest/v1/{TABELLA}", params={"corrente": "eq.true", "id": f"neq.{id_partita}"},
            json={"corrente": False}, intestazioni={"Prefer": "return=minimal"})


# --- File (foto, note vocali) ----------------------------------------------------

def carica_file(percorso, dati, tipo="image/jpeg"):
    _chiama("POST", f"/storage/v1/object/{SPAZIO}/{percorso}", data=dati,
            intestazioni={"Content-Type": tipo, "x-upsert": "true"})


def scarica_file(percorso):
    """bytes del file, oppure None se non esiste."""
    r = _chiama("GET", f"/storage/v1/object/authenticated/{SPAZIO}/{percorso}", ammetti_404=True)
    return None if r.status_code >= 400 else r.content


def elimina_file(percorsi):
    percorsi = [p for p in percorsi if p]
    if percorsi:
        _chiama("DELETE", f"/storage/v1/object/{SPAZIO}", json={"prefixes": percorsi})
