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
CAMPI_TESTO = ("cognome", "nome", "matricola", "documento_tipo", "documento_numero", "documento_rilascio",
               "ruolo", "genitore", "telefono")
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
    """Testi in ordine (cognome e nome in maiuscolo), date in formato yyyy-mm-dd."""
    pulita = {k: _testo(scheda.get(k)) for k in CAMPI_TESTO}
    pulita["cognome"], pulita["nome"] = pulita["cognome"].upper(), pulita["nome"].upper()
    pulita["matricola"] = re.sub(r"\s+", "", pulita["matricola"]).upper()
    pulita["documento_numero"] = re.sub(r"\s+", "", pulita["documento_numero"]).upper()
    pulita.update({k: data_iso(scheda.get(k)) for k in CAMPI_DATA})
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
    """La rosa nel formato della Distinta ([{giocatore, anno, numero}]); [] se il gruppo non ha ragazzi.
    Il numero di maglia non sta in anagrafica: si sceglie partita per partita."""
    return [{"giocatore": nome_completo(r), "anno": r.get("anno_nascita") or (r.get("nascita") or "")[:4], "numero": None}
            for r in ragazzi_del_gruppo(stagione, gruppo)]


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
            nuovi.append(pulisci_scheda({"cognome": cognome, "nome": nome,
                                         "anno_nascita": g.get("anno"), "gruppi": {stagione: gruppo}}))
    if nuovi:
        _scrivi(ragazzi + nuovi)
    return len(nuovi)


def tipo_documento(testo):
    """"C.I.", "CI", "carta identità" -> "Carta d'identità"; "PAT" -> "Patente"; ecc."""
    t = re.sub(r"[^a-z]", "", str(testo or "").lower())
    if not t:
        return ""
    if t.startswith(("ci", "carta", "cie")):
        return "Carta d'identità"
    if t.startswith("pat"):
        return "Patente"
    if t.startswith("pas"):
        return "Passaporto"
    return "Altro"


def _stessa_persona(r, scheda):
    if scheda["matricola"] and r.get("matricola"):
        return r["matricola"] == scheda["matricola"]
    if chiave_giocatore(nome_completo(r)) != chiave_giocatore(nome_completo(scheda)):
        return False
    return not r.get("nascita") or not scheda["nascita"] or r["nascita"] == scheda["nascita"]


def importa_schede(righe, stagione, gruppo):
    """Unisce all'anagrafica un elenco di schede (da CSV o dalle distinte).
    Un ragazzo già presente (stessa matricola, oppure stesso nome con la stessa data di nascita o senza)
    riceve solo i dati che gli mancano; gli altri sono aggiunti. Chi non ha ancora una squadra
    nell'anno va nella squadra della riga ("gruppo") oppure in quella indicata.
    Restituisce (aggiunti, aggiornati)."""
    ragazzi = elenco_ragazzi()
    aggiunti = aggiornati = 0
    for riga in righe:
        squadra = _testo(riga.get("gruppo")) or gruppo
        scheda = pulisci_scheda({**riga, "documento_tipo": tipo_documento(riga.get("documento_tipo"))
                                 or riga.get("documento_tipo"), "gruppi": {}, "id": None})
        if not scheda["cognome"]:
            continue
        r = next((r for r in ragazzi if _stessa_persona(r, scheda)), None)
        if r is None:
            scheda["gruppi"] = {stagione: squadra} if squadra else {}
            ragazzi.append(scheda)
            aggiunti += 1
            continue
        prima = dict(r)
        for campo in CAMPI_TESTO + CAMPI_DATA + ("anno_nascita",):
            if scheda.get(campo) and not r.get(campo):
                r[campo] = scheda[campo]
        r["gruppi"] = r.get("gruppi") or {}
        if squadra and not r["gruppi"].get(stagione):
            r["gruppi"][stagione] = squadra
        if r != prima:
            aggiornati += 1
    if aggiunti or aggiornati:
        _scrivi(ragazzi)
    return aggiunti, aggiornati


def trova_per_nome(nome, anno, ragazzi):
    """Il ragazzo che corrisponde a un nome scritto a mano ("ANDERSON PIVA MILANES" trova PIVA ANDERSON):
    stesse parole in qualsiasi ordine, oppure tutte le parole della scheda dentro il nome (una sola scheda).
    Se l'anno di nascita c'è da tutte e due le parti, deve essere lo stesso. None se non è sicuro."""
    chiave = chiave_giocatore(nome)
    parole = set(chiave.split())

    def anno_ok(r):
        suo = r.get("anno_nascita") or (r.get("nascita") or "")[:4]
        return not anno or not suo or str(anno) == suo

    candidati = [r for r in ragazzi if anno_ok(r)]
    uguali = [r for r in candidati if chiave_giocatore(nome_completo(r)) == chiave]
    if len(uguali) == 1:
        return uguali[0]
    dentro = [r for r in candidati if set(chiave_giocatore(nome_completo(r)).split()) <= parole]
    return dentro[0] if len(dentro) == 1 and len(uguali) == 0 else None


def nuova_da_nome(nome, anno, stagione, gruppo):
    """Scheda nuova da un nome "COGNOME NOME" di una tabella (il nome è l'ultima parola, da controllare)."""
    cognome, nome_proprio = dividi_nome(nome)
    return salva_scheda({"cognome": cognome, "nome": nome_proprio, "anno_nascita": anno,
                         "gruppi": {stagione: gruppo} if gruppo else {}})
