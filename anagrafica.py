"""Anagrafica dei ragazzi della società: dati di tesseramento e scadenze.

Una scheda per ragazzo, che resta negli anni: in ogni anno sportivo il ragazzo sta in un gruppo
squadra (Prima Squadra, Under 17...). Per i gruppi che hanno ragazzi in anagrafica, la rosa usata
dalla Distinta viene da qui.

Dati di minori: si salva solo il necessario. Del documento e del certificato medico solo tipo,
numero e scadenza, mai la scansione. Il file sta nello spazio privato di Supabase
(impostazioni/anagrafica.json) e non va mai sulla pagina pubblica.
"""
import json
import os
import re
import uuid
from datetime import date, datetime

from cronaca_manager import _cartella_dati, _carica_online, _leggi_file
from statistiche import chiave_giocatore

PERCORSO_ONLINE = "impostazioni/anagrafica.json"
RUOLI_CAMPO = ["", "Portiere", "Difensore", "Centrocampista", "Attaccante"]
TIPI_DOCUMENTO = ["", "Carta d'identità", "Passaporto", "Patente", "Altro"]
GIORNI_AVVISO = 30  # scadenze segnalate con un mese di anticipo
CAMPI_TESTO = ("cognome", "nome", "matricola", "documento_tipo", "documento_numero", "ruolo",
               "genitore", "telefono")
CAMPI_DATA = ("nascita", "documento_scadenza", "certificato_scadenza")


def _percorso():
    return os.path.join(_cartella_dati(), "anagrafica.json")


def elenco_ragazzi():
    """[{id, cognome, nome, nascita, ..., gruppi: {stagione: gruppo}}] in ordine alfabetico."""
    try:
        ragazzi = json.loads(_leggi_file(_percorso(), PERCORSO_ONLINE)) or []
    except (OSError, ValueError):
        ragazzi = []
    return sorted(ragazzi, key=lambda r: (r.get("cognome", ""), r.get("nome", "")))


def _scrivi(ragazzi):
    with open(_percorso(), "w", encoding="utf-8") as f:
        json.dump(ragazzi, f, ensure_ascii=False, indent=1)
    _carica_online(PERCORSO_ONLINE, _percorso(), "application/json")


def _testo(valore, massimo=60):
    return re.sub(r"\s+", " ", str(valore or "")).strip()[:massimo]


def data_iso(valore):
    """date, "dd/mm/yyyy" o "yyyy-mm-dd" -> "yyyy-mm-dd"; "" se non è una data."""
    if isinstance(valore, (date, datetime)):
        return valore.strftime("%Y-%m-%d")
    testo = str(valore or "").strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(testo, formato).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def data_da_iso(valore):
    try:
        return datetime.strptime(valore, "%Y-%m-%d").date() if valore else None
    except ValueError:
        return None


def pulisci_scheda(scheda):
    """Testi in ordine (cognome e nome in maiuscolo), date in formato yyyy-mm-dd, numero 1-99."""
    pulita = {k: _testo(scheda.get(k)) for k in CAMPI_TESTO}
    pulita["cognome"], pulita["nome"] = pulita["cognome"].upper(), pulita["nome"].upper()
    pulita["matricola"] = re.sub(r"\s+", "", pulita["matricola"]).upper()
    pulita["documento_numero"] = re.sub(r"\s+", "", pulita["documento_numero"]).upper()
    pulita.update({k: data_iso(scheda.get(k)) for k in CAMPI_DATA})
    try:
        numero = int(scheda.get("numero"))
        pulita["numero"] = numero if 1 <= numero <= 99 else None
    except (TypeError, ValueError):
        pulita["numero"] = None
    # Solo l'anno di nascita (dalle vecchie rose), finché non si scrive la data completa
    anno = str(scheda.get("anno_nascita") or "").strip()
    pulita["anno_nascita"] = pulita["nascita"][:4] or (anno if re.fullmatch(r"(19|20)\d\d", anno) else "")
    pulita["gruppi"] = {s: g for s, g in (scheda.get("gruppi") or {}).items() if g}
    pulita["id"] = scheda.get("id") or uuid.uuid4().hex[:12]
    return pulita


def nome_completo(r):
    return f"{r.get('cognome', '')} {r.get('nome', '')}".strip()


def doppione(scheda, ragazzi):
    """Un altro ragazzo con lo stesso nome (accenti e doppie a parte) e la stessa data di nascita."""
    chiave = chiave_giocatore(nome_completo(scheda))
    for r in ragazzi:
        if r["id"] != scheda.get("id") and chiave_giocatore(nome_completo(r)) == chiave \
                and (r.get("nascita") or "") == (scheda.get("nascita") or ""):
            return r
    return None


def salva_scheda(scheda):
    """Aggiunge o aggiorna una scheda; rilegge l'elenco appena prima di scrivere, così due persone
    che lavorano insieme non si cancellano a vicenda le modifiche su ragazzi diversi."""
    scheda = pulisci_scheda(scheda)
    ragazzi = [r for r in elenco_ragazzi() if r["id"] != scheda["id"]]
    _scrivi(ragazzi + [scheda])
    return scheda


def elimina_scheda(id_ragazzo):
    _scrivi([r for r in elenco_ragazzi() if r["id"] != id_ragazzo])


def ragazzi_del_gruppo(stagione, gruppo, ragazzi=None):
    return [r for r in (ragazzi if ragazzi is not None else elenco_ragazzi())
            if (r.get("gruppi") or {}).get(stagione) == gruppo]


def rosa_da_anagrafica(stagione, gruppo):
    """La rosa nel formato della Distinta ([{giocatore, anno, numero}]); [] se il gruppo non ha ragazzi."""
    return [{"giocatore": nome_completo(r), "anno": r.get("anno_nascita") or (r.get("nascita") or "")[:4], "numero": r.get("numero")}
            for r in sorted(ragazzi_del_gruppo(stagione, gruppo), key=lambda r: (r.get("numero") or 99, nome_completo(r)))]


def rinomina_gruppo(stagione, vecchio, nuovo):
    ragazzi = elenco_ragazzi()
    cambiati = False
    for r in ragazzi:
        if (r.get("gruppi") or {}).get(stagione) == vecchio:
            r["gruppi"][stagione] = nuovo
            cambiati = True
    if cambiati:
        _scrivi(ragazzi)


def stato_scadenza(valore, oggi=None):
    """"scaduto", "in scadenza" (entro GIORNI_AVVISO), "ok" oppure "" se la data manca."""
    giorno = data_da_iso(valore)
    if not giorno:
        return ""
    giorni = (giorno - (oggi or date.today())).days
    return "scaduto" if giorni < 0 else "in scadenza" if giorni <= GIORNI_AVVISO else "ok"


def scadenze(ragazzi, oggi=None):
    """[(ragazzo, cosa, data, stato)] per documenti e certificati scaduti o in scadenza, dal più urgente."""
    voci = []
    for r in ragazzi:
        for campo, cosa in (("certificato_scadenza", "Certificato medico"), ("documento_scadenza", "Documento")):
            stato = stato_scadenza(r.get(campo), oggi)
            if stato in ("scaduto", "in scadenza"):
                voci.append((r, cosa, r[campo], stato))
    return sorted(voci, key=lambda v: v[2])


def dividi_nome(giocatore):
    """"DE ROSSI LUCA" -> ("DE ROSSI", "LUCA"): nelle liste il nome è l'ultima parola (da controllare)."""
    parti = _testo(giocatore).upper().split(" ")
    return (" ".join(parti[:-1]), parti[-1]) if len(parti) > 1 else (parti[0], "")


def importa_rose(stagione, gruppi, rosa_di):
    """Crea le schede dei giocatori delle rose dell'anno che non sono ancora in anagrafica.
    rosa_di(stagione, gruppo) -> [{giocatore, anno, numero}]. Restituisce quanti ne ha aggiunti."""
    ragazzi = elenco_ragazzi()
    presenti = {chiave_giocatore(nome_completo(r)) for r in ragazzi}
    nuovi = []
    for gruppo in gruppi:
        for g in rosa_di(stagione, gruppo):
            chiave = chiave_giocatore(g.get("giocatore"))
            if not chiave or chiave in presenti:
                continue
            presenti.add(chiave)
            cognome, nome = dividi_nome(g["giocatore"])
            nuovi.append(pulisci_scheda({"cognome": cognome, "nome": nome, "numero": g.get("numero"),
                                         "anno_nascita": g.get("anno"), "gruppi": {stagione: gruppo}}))
    if nuovi:
        _scrivi(ragazzi + nuovi)
    return len(nuovi)
