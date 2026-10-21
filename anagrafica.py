"""Anagrafica della società: ragazzi, dirigenti e allenatori, con i dati di tesseramento e le scadenze.

Una scheda per ragazzo, che resta negli anni: in ogni anno sportivo il ragazzo sta in un gruppo
squadra (Prima Squadra, Under 17...). Per i gruppi che hanno ragazzi in anagrafica, la rosa usata
dalla Distinta viene da qui. Il "tipo" distingue i calciatori da dirigenti, allenatori e staff (che
servono per le persone ammesse in panchina nella distinta da stampare); senza tipo è un calciatore.

Dati di minori: si salva solo il necessario. Del documento e del certificato medico solo tipo,
numero e scadenza, mai la scansione. Il file sta nello spazio privato di Supabase
(impostazioni/anagrafica.json) e non va mai sulla pagina pubblica.
"""
import json
import os
import re
import uuid
from datetime import date, datetime

import registro
from cronaca_manager import _cartella_dati, _carica_online, _leggi_file
from statistiche import chiave_giocatore

PERCORSO_ONLINE = "impostazioni/anagrafica.json"
# I ruoli generici (Difensore, Centrocampista, Attaccante) restano per le schede già salvate e per chi non vuole
# essere più preciso
RUOLI_CAMPO = ["", "Portiere",
               "Difensore", "Difensore centrale", "Terzino destro", "Terzino sinistro", "Esterno difensivo",
               "Centrocampista", "Centrocampista centrale", "Centrocampista destro", "Centrocampista sinistro",
               "Mediano", "Regista", "Mezzala destra", "Mezzala sinistra", "Trequartista",
               "Attaccante", "Ala destra", "Ala sinistra", "Seconda punta", "Centravanti"]
# Consenso dei genitori (o del giocatore maggiorenne) a foto e video sui canali della società
CONSENSO_SI, CONSENSO_NO = "Sì", "No"
CONSENSI_FOTO = ["", CONSENSO_SI, CONSENSO_NO]
TIPI_DOCUMENTO = ["", "Carta d'identità", "Passaporto", "Patente", "Altro"]
CALCIATORE = "Calciatore"
TIPI_PERSONA = [CALCIATORE, "Dirigente", "Allenatore", "Staff sanitario", "Altro staff"]
GIORNI_AVVISO = 30  # scadenze segnalate con un mese di anticipo
CAMPI_TESTO = ("cognome", "nome", "matricola", "documento_tipo", "documento_numero", "documento_rilascio",
               "ruolo", "genitore", "telefono", "tipo", "qualifica", "consenso_foto")
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
    pulita["tipo"] = pulita["tipo"] if pulita["tipo"] in TIPI_PERSONA else CALCIATORE
    pulita["consenso_foto"] = consenso(pulita["consenso_foto"])
    pulita["matricola"] = re.sub(r"\s+", "", pulita["matricola"]).upper()
    pulita["documento_numero"] = re.sub(r"\s+", "", pulita["documento_numero"]).upper()
    pulita.update({k: data_iso(scheda.get(k)) for k in CAMPI_DATA})
    # Solo l'anno di nascita (dalle vecchie rose), finché non si scrive la data completa
    anno = str(scheda.get("anno_nascita") or "").strip()
    pulita["anno_nascita"] = pulita["nascita"][:4] or (anno if re.fullmatch(r"(19|20)\d\d", anno) else "")
    pulita["gruppi"] = {s: g for s, g in (scheda.get("gruppi") or {}).items() if g}
    pulita["id"] = scheda.get("id") or uuid.uuid4().hex[:12]
    return pulita


def consenso(testo):
    """"si", "SI", "x", "1" -> "Sì"; "no", "0" -> "No"; altro -> "" (non ancora chiesto)."""
    t = str(testo or "").strip().lower()
    if t in ("sì", "si", "s", "x", "1", "true", "ok", "yes"):
        return CONSENSO_SI
    return CONSENSO_NO if t in ("no", "n", "0", "false") else ""


def tipo_di(r):
    return r.get("tipo") or CALCIATORE


def e_calciatore(r):
    return tipo_di(r) == CALCIATORE


def calciatori(persone):
    return [r for r in persone if e_calciatore(r)]


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
    tutti = elenco_ragazzi()
    prima = next((r for r in tutti if r["id"] == scheda["id"]), None)
    _scrivi([r for r in tutti if r["id"] != scheda["id"]] + [scheda])
    if prima is None:
        registro.segna("Anagrafica: scheda aggiunta", nome_completo(scheda))
    else:
        cambiati = registro.campi_cambiati(prima, scheda)
        if cambiati:
            registro.segna("Anagrafica: scheda modificata", f"{nome_completo(scheda)} ({', '.join(cambiati)})")
    return scheda


def elimina_scheda(id_ragazzo):
    tutti = elenco_ragazzi()
    tolta = next((r for r in tutti if r["id"] == id_ragazzo), None)
    _scrivi([r for r in tutti if r["id"] != id_ragazzo])
    if tolta:
        registro.segna("Anagrafica: scheda eliminata", nome_completo(tolta))


def ragazzi_del_gruppo(stagione, gruppo, ragazzi=None, solo_calciatori=True):
    return [r for r in (ragazzi if ragazzi is not None else elenco_ragazzi())
            if (r.get("gruppi") or {}).get(stagione) == gruppo and (e_calciatore(r) or not solo_calciatori)]


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
        registro.segna("Anagrafica: schede create dalle rose", f"{stagione}: {len(nuovi)} nuove")
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
        registro.segna("Anagrafica: importazione", f"{stagione}: {aggiunti} aggiunte, {aggiornati} completate")
    return aggiunti, aggiornati


def confronta_tabulato(tesserati, ragazzi):
    """Per ogni tesserato del tabulato FIGC: {"tesserato", "id" (la scheda che è già in anagrafica o None),
    "mancanti" (i dati che il tabulato aggiunge o corregge), "diverso" (avviso se la data di nascita non torna:
    vale quella del tabulato)}.
    Stessa persona: stessa matricola, oppure stessa data di nascita e stesso nome (anche con un nome in più,
    es. PIVA ANDERSON e PIVA ANDERSON MILANES), oppure stesso nome se la data manca."""
    risultato = []
    for t in tesserati:
        chiave = chiave_giocatore(nome_completo(t))
        parole = set(chiave.split())
        trovato = next((r for r in ragazzi if t["matricola"] and r.get("matricola") == t["matricola"]), None)
        if trovato is None:
            def stesso_nome(r):
                altre = set(chiave_giocatore(nome_completo(r)).split())
                return altre == parole or (len(min(altre, parole, key=len)) >= 2 and (altre <= parole or parole <= altre))
            simili = [r for r in ragazzi if e_calciatore(r) and stesso_nome(r)
                      and not (r.get("matricola") and t["matricola"] and r["matricola"] != t["matricola"])]
            trovato = next((r for r in simili if r.get("nascita") == t["nascita"]), None) or \
                next((r for r in simili if not r.get("nascita") and anno_di(r) in ("", t["nascita"][:4])), None)
        mancanti = [campo for campo in ("matricola", "nascita") if trovato and t.get(campo) and not trovato.get(campo)]
        diverso = ""
        if trovato and trovato.get("nascita") and trovato["nascita"] != t["nascita"]:
            # vale il tabulato della FIGC: applicando, la data dell'anagrafica si corregge
            diverso = f"in anagrafica è nato il {data_da_iso(trovato['nascita']):%d/%m/%Y}"
            mancanti.append("nascita")
        risultato.append({"tesserato": t, "id": trovato["id"] if trovato else None, "mancanti": mancanti,
                          "diverso": diverso})
    return risultato


def applica_tabulato(scelte, stagione):
    """scelte: [(confronto, squadra per i nuovi)]. Le schede esistenti ricevono solo i dati mancanti
    (matricola, data di nascita, o la data corretta); i nuovi tesserati diventano schede nuove di calciatori.
    Restituisce (aggiunti, completati)."""
    ragazzi = elenco_ragazzi()
    per_id = {r["id"]: r for r in ragazzi}
    aggiunti = completati = 0
    for confronto, squadra in scelte:
        t = confronto["tesserato"]
        r = per_id.get(confronto["id"]) if confronto["id"] else None
        if r is None:
            ragazzi.append(pulisci_scheda({"cognome": t["cognome"], "nome": t["nome"], "matricola": t["matricola"],
                                           "nascita": t["nascita"], "tipo": CALCIATORE,
                                           "gruppi": {stagione: squadra} if squadra else {}}))
            aggiunti += 1
        elif confronto["mancanti"]:
            for campo in confronto["mancanti"]:
                r[campo] = t[campo]
            if "nascita" in confronto["mancanti"]:
                r["anno_nascita"] = t["nascita"][:4]
            completati += 1
    if aggiunti or completati:
        _scrivi(ragazzi)
        registro.segna("Anagrafica: tabulato FIGC", f"{stagione}: {aggiunti} aggiunte, {completati} completate")
    return aggiunti, completati


def anno_di(r):
    return r.get("anno_nascita") or (r.get("nascita") or "")[:4]


def trova_per_nome(nome, anno, ragazzi, preferiti=()):
    """Il ragazzo che corrisponde a un nome scritto a mano ("ANDERSON PIVA MILANES" trova PIVA ANDERSON):
    stesse parole in qualsiasi ordine, oppure tutte le parole della scheda dentro il nome. Prima con lo
    stesso anno di nascita, poi senza; tra più schede uguali sceglie quella con l'id in "preferiti"
    (es. i ragazzi della squadra). None se resta il dubbio."""
    chiave = chiave_giocatore(nome)
    parole = set(chiave.split())

    def una(lista):
        if len(lista) == 1:
            return lista[0]
        scelti = [r for r in lista if r["id"] in preferiti]
        return scelti[0] if len(scelti) == 1 else None

    for con_anno in (True, False):
        candidati = [r for r in ragazzi if not con_anno or not anno or not anno_di(r) or anno_di(r) == str(anno)]
        uguali = [r for r in candidati if chiave_giocatore(nome_completo(r)) == chiave]
        if uguali:
            return una(uguali)
        trovato = una([r for r in candidati if set(chiave_giocatore(nome_completo(r)).split()) <= parole])
        if trovato:
            return trovato
    return None


def nuova_da_nome(nome, anno, stagione, gruppo):
    """Scheda nuova da un nome "COGNOME NOME" di una tabella (il nome è l'ultima parola, da controllare)."""
    cognome, nome_proprio = dividi_nome(nome)
    return salva_scheda({"cognome": cognome, "nome": nome_proprio, "anno_nascita": anno,
                         "gruppi": {stagione: gruppo} if gruppo else {}})
