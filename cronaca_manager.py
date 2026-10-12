"""Cronaca della partita: cronometro, note (vocali o scritte) e resoconto per i giornalisti.

Il cronometro si basa sull'orario del server, non sul telefono: se lo schermo si
spegne o la pagina si ricarica, il minuto resta giusto. Le note sono salvate su
file a ogni modifica, così non si perdono se la connessione cade durante la gara.
Con Supabase configurato (archivio_cloud) ogni salvataggio va anche nell'archivio online,
che sopravvive ai riavvii dell'app e conserva lo storico delle partite.
"""
import io
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone

from openai import OpenAI

import archivio_cloud as cloud
from nomi_file import nome_file_gara

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELLO_TESTO = "gpt-4o"
MODELLI_TRASCRIZIONE = ("gpt-4o-transcribe", "whisper-1")  # il secondo è la riserva

TIPI_NOTA = ["Nota", "Gol", "Occasione", "Ammonizione", "Espulsione", "Sostituzione", "Infortunio", "Rigore"]
FASI = [("primo", "1° tempo"), ("secondo", "2° tempo")]


def _cartella_dati():
    """Cartella dove salvare la cronaca (quella dell'app, oppure la temporanea se non scrivibile)."""
    for base in (os.path.join(BASE_DIR, "cronaca_dati"), os.path.join(tempfile.gettempdir(), "cronaca_dati")):
        try:
            os.makedirs(os.path.join(base, "audio"), exist_ok=True)
            prova = os.path.join(base, ".scrivibile")
            with open(prova, "w") as f:
                f.write("ok")
            return base
        except OSError:
            continue
    raise OSError("Nessuna cartella scrivibile per salvare la cronaca.")


def _percorso_file():
    return os.path.join(_cartella_dati(), "cronaca_corrente.json")


def cronaca_vuota(casa="", ospite="", campionato="", data=""):
    return {
        "id": uuid.uuid4().hex,
        "creata": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "partita": {"casa": casa, "ospite": ospite, "campionato": campionato, "data": data},
        "durata_tempo": 45,
        "tempi": {},          # chiave fase -> {"inizio": ts, "fine": ts | None}
        "note": [],
        "resoconto": None,
        "distinta": None,     # distinta pubblicata (info_gara, casa, ospite)
        "referto": [],        # nomi dei file delle foto del referto
    }


ELENCHI_FOTO = ("referto", "foto_distinte", "foto_partita")
_ultimo_tentativo_cloud = {"t": 0.0}
_da_caricare = {}  # percorso online -> (percorso locale, tipo): file da riprovare a caricare


def _completa(dati):
    base = cronaca_vuota()
    base.pop("creata")  # le cronache salvate prima di questo campo non ce l'hanno: restano senza
    base.update(dati or {})
    return base


def distinta_per_cronaca(cronaca, distinta):
    """Una nuova partita prende solo una distinta pubblicata dopo la sua apertura:
    dopo l'archiviazione si riparte da una nuova acquisizione delle liste."""
    if not distinta or not cronaca.get("creata"):
        return bool(distinta)
    return (distinta.get("aggiornato") or "") >= cronaca["creata"]


def _scrivi_locale(cronaca):
    percorso = _percorso_file()
    temporaneo = percorso + ".tmp"
    with open(temporaneo, "w", encoding="utf-8") as f:
        json.dump(cronaca, f, ensure_ascii=False, indent=2)
    os.replace(temporaneo, percorso)  # scrittura atomica: il file non resta mai a metà


def _online(funzione, *argomenti):
    """Prova un'operazione sull'archivio online; se non va, l'app continua sul disco."""
    if not cloud.attivo():
        return False
    try:
        funzione(*argomenti)
        return True
    except cloud.ArchivioErrore:
        return False


def carica_cronaca():
    """La cronaca aperta: dal disco dell'app; dopo un riavvio (disco vuoto) dall'archivio online."""
    try:
        with open(_percorso_file(), encoding="utf-8") as f:
            return _completa(json.load(f))
    except (OSError, ValueError):
        pass
    if not cloud.attivo():
        return cronaca_vuota()
    if time.time() - _ultimo_tentativo_cloud["t"] < 30:
        return cronaca_vuota()  # Supabase non ha risposto da poco: non bloccare il cronometro
    try:
        dati = cloud.partita_corrente()
    except cloud.ArchivioErrore:
        _ultimo_tentativo_cloud["t"] = time.time()
        return cronaca_vuota()
    cronaca = _completa(dati) if dati else cronaca_vuota()
    _scrivi_locale(cronaca)
    return cronaca


def salva_cronaca(cronaca):
    cronaca.setdefault("id", uuid.uuid4().hex)
    cronaca["aggiornato"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _scrivi_locale(cronaca)
    if _online(cloud.salva_partita, cronaca, True, punteggio(cronaca)):
        _riprova_caricamenti()


def stato_archivio_online():
    """None se non configurato, altrimenti (ok, messaggio)."""
    if not cloud.attivo():
        return None
    errore = cloud.ultimo_errore()
    return (errore is None, errore or "Archivio online attivo: le partite restano salvate anche se l'app si riavvia.")


def ha_contenuto(cronaca):
    """Note, foto aggiunte a mano o resoconto (le foto delle distinte si copiano da sole: non contano)."""
    return bool(cronaca.get("note") or cronaca.get("referto") or cronaca.get("foto_partita") or cronaca.get("resoconto"))


def _metti_in_archivio(cronaca):
    """La cronaca aperta passa in archivio (se ha qualcosa); quella vuota si scarta."""
    if cronaca.get("note"):
        nome = datetime.now().strftime("cronaca_%Y%m%d_%H%M%S.json")
        with open(os.path.join(_cartella_dati(), nome), "w", encoding="utf-8") as f:
            json.dump(cronaca, f, ensure_ascii=False, indent=2)
    if ha_contenuto(cronaca):
        _online(cloud.salva_partita, cronaca, False, punteggio(cronaca))
    elif cronaca.get("id"):
        _online(cloud.elimina_partita, cronaca["id"])
        _cancella_foto(cronaca.get("foto_distinte") or [])  # solo le copie delle distinte: la partita era vuota


def archivia_e_azzera(cronaca, **partita):
    """Conserva la cronaca attuale (se ha note) nell'archivio, poi ne apre una nuova vuota."""
    _metti_in_archivio(cronaca)
    togli_distinte_caricate()
    nuova = cronaca_vuota(**partita)
    salva_cronaca(nuova)
    _online(cloud.togli_corrente_alle_altre, nuova["id"])
    return nuova


def cancella_e_azzera(cronaca):
    """Butta via la partita aperta senza archiviarla (note, foto, note vocali, foto delle
    distinte caricate) e ne apre una nuova vuota, in attesa delle nuove distinte."""
    _cancella_foto([n for e in ELENCHI_FOTO for n in cronaca.get(e) or []])
    audio = [n["audio"] for n in cronaca.get("note") or [] if n.get("audio")]
    for nome in audio:
        try:
            os.remove(os.path.join(_cartella_dati(), "audio", nome))
        except OSError:
            pass
        _da_caricare.pop(f"audio/{nome}", None)
    _online(cloud.elimina_file, [f"audio/{n}" for n in audio])
    if cronaca.get("id"):
        _online(cloud.elimina_partita, cronaca["id"])
    cartella = _cartella_distinte_pubblicate()
    for vecchio in os.listdir(cartella):
        os.remove(os.path.join(cartella, vecchio))
    for lato in ("casa", "ospite"):
        _da_caricare.pop(f"distinte_pubblicate/{lato}.jpg", None)
    _online(cloud.elimina_file, [f"distinte_pubblicate/{lato}.jpg" for lato in ("casa", "ospite")])
    togli_distinte_caricate()
    nuova = cronaca_vuota()
    salva_cronaca(nuova)
    _online(cloud.togli_corrente_alle_altre, nuova["id"])
    return nuova


# --- Archivio delle partite (solo con Supabase) ---------------------------------

def partite_archiviate(cronaca_aperta):
    """Elenco per l'archivio: tutte le partite salvate online tranne quella aperta."""
    return cloud.elenco_partite(cronaca_aperta.get("id", ""))


def riapri_partita(cronaca_aperta, id_partita):
    """Riapre una partita dell'archivio; quella aperta finisce in archivio, non si perde."""
    dati = cloud.leggi_partita(id_partita)
    if not dati:
        raise cloud.ArchivioErrore("Partita non trovata nell'archivio.")
    _metti_in_archivio(cronaca_aperta)
    cronaca = _completa(dati)
    salva_cronaca(cronaca)
    cloud.togli_corrente_alle_altre(cronaca["id"])
    return cronaca


def elimina_partita_archiviata(id_partita):
    """Elimina definitivamente una partita dell'archivio con le sue foto e note vocali."""
    dati = cloud.leggi_partita(id_partita) or {}
    file = [f"foto/{n}" for e in ELENCHI_FOTO for n in dati.get(e) or []]
    file += [f"audio/{n['audio']}" for n in dati.get("note") or [] if n.get("audio")]
    cloud.elimina_file(file)
    cloud.elimina_partita(id_partita)


def _file_della_partita(dati):
    """[(percorso online, percorso nello ZIP)] di foto e note vocali di una partita."""
    file = [(f"foto/{n}", f"foto/{n}") for e in ELENCHI_FOTO for n in dati.get(e) or []]
    file += [(f"audio/{n['audio']}", f"audio/{n['audio']}") for n in dati.get("note") or [] if n.get("audio")]
    return file


def conta_file(dati):
    """(foto, note vocali) ancora presenti nella partita."""
    foto = sum(len(dati.get(e) or []) for e in ELENCHI_FOTO)
    return foto, sum(1 for n in dati.get("note") or [] if n.get("audio"))


def file_collegati(tutte):
    """Percorsi online usati dalle partite: {"archivio": set, "aperta": set} (tutte: {id: dati}),
    più la partita aperta letta dal disco."""
    aperta = carica_cronaca()
    usati = {"archivio": set(), "aperta": {o for o, _ in _file_della_partita(aperta)}}
    for id_partita, dati in tutte.items():
        if id_partita != aperta.get("id"):
            usati["archivio"] |= {o for o, _ in _file_della_partita(dati)}
    return usati


def pulisci_file_orfani(orfani):
    """Elimina dall'archivio online file che nessuna partita usa più."""
    cloud.elimina_file(list(orfani))


def _nome_cartella(dati):
    p = dati.get("partita") or {}
    testo = " ".join(x for x in (p.get("data"), p.get("casa"), "-", p.get("ospite")) if x) or dati.get("id", "partita")
    pulito = re.sub(r"[^\w\-. ]+", "-", testo).strip(" -")
    return f"{pulito[:80]} [{dati.get('id', '')[:6]}]"


def crea_backup(id_partite, genera_pdf=None):
    """ZIP con, per ogni partita, i dati (partita.json), il resoconto PDF, le foto e le note vocali."""
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for id_partita in id_partite:
            dati = cloud.leggi_partita(id_partita)
            if not dati:
                continue
            cartella = _nome_cartella(dati)
            z.writestr(f"{cartella}/partita.json", json.dumps(dati, ensure_ascii=False, indent=2))
            if genera_pdf:
                p = dati.get("partita") or {}
                try:
                    z.writestr(f"{cartella}/{nome_file_gara('Resoconto', p.get('data'), p.get('casa'), p.get('ospite'))}",
                               genera_pdf(_completa(dati)))
                except Exception:
                    pass  # un PDF non riuscito non deve bloccare il backup di foto e dati
            for online, nello_zip in _file_della_partita(dati):
                contenuto = cloud.scarica_file(online)
                if contenuto is not None:
                    z.writestr(f"{cartella}/{nello_zip}", contenuto)
    return buffer.getvalue()


def alleggerisci_partita(id_partita):
    """Toglie foto e note vocali dall'archivio online; note, tabellino e articolo restano."""
    dati = cloud.leggi_partita(id_partita)
    if not dati:
        return
    foto, audio = conta_file(dati)
    cloud.elimina_file([online for online, _ in _file_della_partita(dati)])
    for e in ELENCHI_FOTO:
        dati[e] = []
    for n in dati.get("note") or []:
        n["audio"] = None
    dati["alleggerita"] = {"il": datetime.now().strftime("%d/%m/%Y"), "foto": foto, "audio": audio}
    cloud.salva_partita(dati, False, punteggio(_completa(dati)))


def ripristina_backup(dati_zip, id_aperta=""):
    """Rimette nell'archivio online le partite di uno ZIP di backup.
    Restituisce (nomi ripristinati, quante saltate perché aperte nella Cronaca)."""
    import zipfile

    ripristinate, saltate = [], 0
    with zipfile.ZipFile(io.BytesIO(dati_zip)) as z:
        for nome in z.namelist():
            if not nome.endswith("/partita.json"):
                continue
            cartella = nome[: -len("partita.json")]
            dati = json.loads(z.read(nome).decode("utf-8"))
            if not dati.get("id"):
                continue
            if dati["id"] == id_aperta:
                saltate += 1  # la partita aperta nell'app non si sovrascrive
                continue
            rimessi = 0
            for online, nello_zip in _file_della_partita(dati):
                if f"{cartella}{nello_zip}" in z.namelist():
                    tipo = "image/jpeg" if online.startswith("foto/") else "audio/wav"
                    cloud.carica_file(online, z.read(f"{cartella}{nello_zip}"), tipo)
                    rimessi += 1
            if rimessi:
                dati.pop("alleggerita", None)
            cloud.salva_partita(dati, False, punteggio(_completa(dati)))
            p = dati.get("partita") or {}
            ripristinate.append(f"{p.get('casa', '')} - {p.get('ospite', '')}".strip(" -"))
    return ripristinate, saltate


# --- File: copia sul disco dell'app e copia online ------------------------------

def _carica_online(percorso_online, percorso_locale, tipo):
    def carica():
        with open(percorso_locale, "rb") as f:
            cloud.carica_file(percorso_online, f.read(), tipo)
    if cloud.attivo() and not _online(carica):
        _da_caricare[percorso_online] = (percorso_locale, tipo)  # riprova al prossimo salvataggio


def _riprova_caricamenti():
    for percorso_online, (percorso_locale, tipo) in list(_da_caricare.items()):
        _da_caricare.pop(percorso_online)
        if os.path.exists(percorso_locale):
            _carica_online(percorso_online, percorso_locale, tipo)


def _leggi_file(percorso_locale, percorso_online):
    """Il file dal disco; se manca (app riavviata) lo riprende dall'archivio online."""
    if not os.path.exists(percorso_locale) and cloud.attivo():
        try:
            dati = cloud.scarica_file(percorso_online)
        except cloud.ArchivioErrore:
            dati = None
        if dati is not None:
            with open(percorso_locale, "wb") as f:
                f.write(dati)
            return dati
    with open(percorso_locale, "rb") as f:
        return f.read()


# --- Cronometro ---------------------------------------------------------------

def fase_in_corso(cronaca):
    """(chiave, etichetta, inizio) del tempo in corso, oppure None."""
    for chiave, etichetta in FASI:
        t = cronaca["tempi"].get(chiave)
        if t and t.get("inizio") and not t.get("fine"):
            return chiave, etichetta, t["inizio"]
    return None


def stato_gara(cronaca):
    """Una tra: prepartita, primo, intervallo, secondo, finita."""
    tempi = cronaca["tempi"]
    if "secondo" in tempi:
        return "finita" if tempi["secondo"].get("fine") else "secondo"
    if "primo" in tempi:
        return "intervallo" if tempi["primo"].get("fine") else "primo"
    return "prepartita"


def minuto_di_gioco(cronaca, adesso=None):
    """Minuto come si scrive nelle cronache: 23', 45+2', 90+4'; fuori dal gioco una parola."""
    adesso = adesso or time.time()
    fase = fase_in_corso(cronaca)
    if not fase:
        return {"prepartita": "Pre-gara", "intervallo": "Intervallo", "finita": "Fine gara"}[stato_gara(cronaca)]
    chiave, _, inizio = fase
    durata = int(cronaca.get("durata_tempo") or 45)
    offset = 0 if chiave == "primo" else durata
    trascorsi = max(0, int((adesso - inizio) // 60)) + 1
    if trascorsi > durata:
        return f"{offset + durata}+{trascorsi - durata}'"
    return f"{offset + trascorsi}'"


def orologio(cronaca, adesso=None):
    """Tempo trascorso nel tempo in corso, mm:ss (per il display)."""
    adesso = adesso or time.time()
    fase = fase_in_corso(cronaca)
    if not fase:
        return "--:--"
    secondi = max(0, int(adesso - fase[2]))
    return f"{secondi // 60:02d}:{secondi % 60:02d}"


def avvia_tempo(cronaca, chiave):
    cronaca["tempi"][chiave] = {"inizio": time.time(), "fine": None}
    salva_cronaca(cronaca)


def chiudi_tempo(cronaca, chiave):
    if chiave in cronaca["tempi"]:
        cronaca["tempi"][chiave]["fine"] = time.time()
        salva_cronaca(cronaca)


# Per ogni tipo di nota, i giocatori da scegliere dai menu: (campo, etichetta)
CAMPI_GIOCATORE = {
    "Gol": [("giocatore", "Marcatore"), ("assist", "Assist (facoltativo)")],
    "Rigore": [("giocatore", "Tiratore")],
    "Sostituzione": [("esce", "Esce"), ("entra", "Entra")],
    "Ammonizione": [("giocatore", "Giocatore")],
    "Espulsione": [("giocatore", "Giocatore")],
    "Occasione": [("giocatore", "Giocatore (facoltativo)")],
    "Infortunio": [("giocatore", "Giocatore")],
}
ESITI_RIGORE = ["Segnato", "Parato", "Fuori / palo"]

# Per ogni tipo, una scelta a tocco che descrive l'evento senza doverlo scrivere: (campo, domanda, opzioni)
SCELTE_DETTAGLIO = {
    # Il rigore non c'è: ha il suo evento "Rigore" con l'esito
    "Gol": ("come", "Come?", ["Azione", "Tiro da fuori", "Colpo di testa", "Punizione", "Calcio d'angolo",
                              "Contropiede", "Autogol"]),
    "Rigore": ("esito", "Esito", ESITI_RIGORE),
    "Ammonizione": ("motivo", "Motivo", ["Fallo", "Proteste", "Simulazione", "Perdita di tempo", "Comportamento"]),
    "Espulsione": ("motivo", "Motivo", ["Doppia ammonizione", "Fallo grave", "Chiara occasione da gol",
                                        "Condotta violenta", "Proteste"]),
    "Occasione": ("esito", "Com'è finita?", ["Parata", "Palo", "Traversa", "Fuori di poco", "Salvataggio sulla linea",
                                             "Fuorigioco"]),
    "Infortunio": ("esito", "Esito", ["Rientra in campo", "Esce dal campo"]),
}
ICONE_TIPO = {"Gol": "⚽", "Rigore": "🎯", "Ammonizione": "🟨", "Espulsione": "🟥", "Sostituzione": "🔄",
              "Occasione": "💥", "Infortunio": "🚑", "Nota": "📝"}


def e_autogol(nota):
    return nota.get("tipo") == "Gol" and (nota.get("dettagli") or {}).get("come") == "Autogol"


def pulisci_nome(nome):
    """Nome del giocatore senza le sigle di capitano e vice: "AGGIO KEVIN (C)" -> "AGGIO KEVIN"."""
    return re.sub(r"\s*\((C|VC)\)\s*$", "", str(nome or "")).strip()


def rosa(cronaca, lato):
    """[(numero, nome)] della squadra dalla distinta collegata, nell'ordine della distinta."""
    elenco = (((cronaca.get("distinta") or {}).get(lato) or {}).get("giocatori")) or []
    risultato = []
    for i, g in enumerate(elenco, start=1):
        nome = pulisci_nome(g.get("GIOCATORE"))
        if nome:
            risultato.append((g.get("N°") or i, nome))
    return risultato


def e_gol(nota):
    d = nota.get("dettagli") or {}
    return nota.get("tipo") == "Gol" or (nota.get("tipo") == "Rigore" and d.get("esito") == "Segnato")


def _con_numero(d, campo):
    if not d.get(campo):
        return ""
    numero = d.get(f"{campo}_n")
    return f"{d[campo]} ({numero})" if numero else d[campo]


def descrizione_nota(nota):
    """I giocatori e le scelte dei menu, in parole: "ROSSI ANDREA (9), punizione, assist BIANCHI LUCA (7)"."""
    d = nota.get("dettagli") or {}
    tipo = nota.get("tipo")
    scelta = SCELTE_DETTAGLIO.get(tipo)
    dettaglio = (d.get(scelta[0]) or "").lower() if scelta else ""
    if tipo == "Sostituzione":
        parti = [f"esce {_con_numero(d, 'esce')}" if d.get("esce") else "",
                 f"entra {_con_numero(d, 'entra')}" if d.get("entra") else ""]
    elif e_autogol(nota):
        parti = [f"autogol di {_con_numero(d, 'giocatore')}" if d.get("giocatore") else "autogol"]
    else:
        parti = [_con_numero(d, "giocatore"), dettaglio,
                 f"assist {_con_numero(d, 'assist')}" if d.get("assist") else ""]
    return ", ".join(p for p in parti if p)


def punteggio(cronaca):
    """Gol contati dalle note di tipo Gol o Rigore segnato (squadra 'casa' o 'ospite')."""
    gol = {"casa": 0, "ospite": 0}
    for n in cronaca["note"]:
        if e_gol(n) and n.get("squadra") in gol:
            gol[n["squadra"]] += 1
    return gol["casa"], gol["ospite"]


# --- Note ---------------------------------------------------------------------

def aggiungi_nota(cronaca, testo, tipo="Nota", squadra="", origine="testo", audio=None, minuto=None, dettagli=None):
    """dettagli: giocatori scelti dai menu, es. {"giocatore": "ROSSI ANDREA", "giocatore_n": 9, "assist": ...}."""
    nota = {
        "id": uuid.uuid4().hex[:10],
        "ts": time.time(),
        "minuto": minuto or minuto_di_gioco(cronaca),
        "tipo": tipo,
        "squadra": squadra,
        "testo": testo.strip(),
        "origine": origine,
        "audio": audio,  # nome del file audio, se la trascrizione va rifatta
        "dettagli": {k: v for k, v in (dettagli or {}).items() if v},
    }
    cronaca["note"].append(nota)
    salva_cronaca(cronaca)
    return nota


def salva_audio(dati_audio, estensione="wav"):
    nome = f"{uuid.uuid4().hex[:10]}.{estensione}"
    percorso = os.path.join(_cartella_dati(), "audio", nome)
    with open(percorso, "wb") as f:
        f.write(dati_audio)
    _carica_online(f"audio/{nome}", percorso, f"audio/{estensione}")
    return nome


def leggi_audio(nome):
    return _leggi_file(os.path.join(_cartella_dati(), "audio", nome), f"audio/{nome}")


def _suggerimento_nomi(cronaca, giocatori=None):
    """Nomi utili al riconoscimento vocale (squadre e giocatori), così li scrive giusti."""
    nomi = [cronaca["partita"].get("casa", ""), cronaca["partita"].get("ospite", "")]
    for elenco in (giocatori or {}).values():
        nomi += [g for g in elenco if g]
    testo = ", ".join(n for n in nomi if n)
    return ("Cronaca di una partita di calcio. Nomi: " + testo)[:800]


def trascrivi(api_key, dati_audio, cronaca, giocatori=None, nome_file="nota.wav"):
    """Testo della nota vocale. Prova il modello migliore, poi quello di riserva."""
    client = OpenAI(api_key=api_key, timeout=60.0, max_retries=1)
    ultimo_errore = None
    for modello in MODELLI_TRASCRIZIONE:
        try:
            file_audio = io.BytesIO(dati_audio)
            file_audio.name = nome_file
            risposta = client.audio.transcriptions.create(
                model=modello,
                file=file_audio,
                language="it",
                prompt=_suggerimento_nomi(cronaca, giocatori),
            )
            return (risposta.text or "").strip()
        except Exception as e:  # modello non disponibile, rete, ecc.: si prova il successivo
            ultimo_errore = e
    raise RuntimeError(f"Trascrizione non riuscita: {ultimo_errore}")


# --- Resoconto per i giornalisti ----------------------------------------------

LUNGHEZZE = {
    "Breve (circa 1.500 battute)": 1500,
    "Standard (circa 3.000 battute)": 3000,
    "Lungo (circa 5.000 battute)": 5000,
}


def _note_per_prompt(cronaca):
    nomi = {"casa": cronaca["partita"].get("casa") or "Casa", "ospite": cronaca["partita"].get("ospite") or "Ospite"}
    righe = []
    for n in note_in_ordine(cronaca):
        squadra = f" [{nomi[n['squadra']]}]" if n.get("squadra") in nomi else ""
        dettagli = descrizione_nota(n)
        commento = n.get("testo", "")
        testo = f"{dettagli}. {commento}" if dettagli and commento else (dettagli or commento)
        righe.append(f"{n.get('minuto', '')} – {n.get('tipo', 'Nota')}{squadra}: {testo}")
    return "\n".join(righe)


TIPI_EVENTO = ["gol", "ammonizione", "espulsione", "sostituzione"]
_TIPO_DA_NOTA = {"Gol": "gol", "Ammonizione": "ammonizione", "Espulsione": "espulsione"}


_MINUTI_A_PAROLE = {"pre": (-1, 0), "inter": (45, 99), "fine": (999, 0)}


def _minuti(minuto):
    """Chiave d'ordine per 23', 45+2', Pre-gara, Intervallo, Fine gara."""
    numeri = [int(x) for x in "".join(c if c.isdigit() else " " for c in str(minuto)).split()]
    if numeri:
        return (numeri[0], numeri[1] if len(numeri) > 1 else 0)
    testo = str(minuto or "").strip().lower()
    return next((v for k, v in _MINUTI_A_PAROLE.items() if testo.startswith(k)), (999, 0))


def note_in_ordine(cronaca):
    """Le note in ordine di minuto di gioco (a parità di minuto, nell'ordine in cui sono state prese),
    non nell'ordine in cui sono state scritte o corrette."""
    return sorted(cronaca.get("note") or [], key=lambda n: (_minuti(n.get("minuto")), n.get("ts", 0)))


def pulisci_eventi(eventi):
    """Eventi validi (gol, ammonizioni, espulsioni, sostituzioni), ordinati per tipo e minuto."""
    puliti = []
    for e in eventi or []:
        if not isinstance(e, dict):
            continue
        tipo = str(e.get("tipo") or "").strip().lower()
        squadra = str(e.get("squadra") or "").strip().lower()
        if tipo not in TIPI_EVENTO or squadra not in ("casa", "ospite"):
            continue
        puliti.append({
            "tipo": tipo,
            "squadra": squadra,
            "minuto": str(e.get("minuto") or "").strip(),
            "giocatore": str(e.get("giocatore") or "").strip().upper(),
            "nota": str(e.get("nota") or "").strip(),
        })
    return sorted(puliti, key=lambda e: (TIPI_EVENTO.index(e["tipo"]), _minuti(e["minuto"])))


def _sostituzione(n):
    """"ENTRA LOZZI FILIPPO, ESCE ZONZIN SEBASTIANO" dai giocatori scelti nella nota."""
    d = n.get("dettagli") or {}
    parti = [f"entra {d['entra']}" if d.get("entra") else "", f"esce {d['esce']}" if d.get("esce") else ""]
    return ", ".join(p for p in parti if p)


def _sigla_evento(n):
    """La sigla del tabellino: rig., aut., 2ª amm."""
    d = n.get("dettagli") or {}
    if n.get("tipo") == "Rigore" or (n.get("tipo") == "Gol" and d.get("come") == "Rigore"):
        return "rig."
    if e_autogol(n):
        return "aut."
    if n.get("tipo") == "Espulsione" and d.get("motivo") == "Doppia ammonizione":
        return "2ª amm."
    return ""


def _tipo_evento(n):
    if e_gol(n):
        return "gol"
    if n.get("tipo") == "Sostituzione":
        return "sostituzione" if _sostituzione(n) else None
    return _TIPO_DA_NOTA.get(n.get("tipo"))


def eventi_da_note(cronaca):
    """Bozza degli eventi prima del resoconto. Il giocatore è quello scelto dal menu; se manca, il
    testo della nota (da correggere)."""
    eventi = []
    for n in cronaca.get("note") or []:
        d = n.get("dettagli") or {}
        tipo = _tipo_evento(n)
        if not tipo:
            continue
        giocatore = _sostituzione(n) if tipo == "sostituzione" else d.get("giocatore") or (n.get("testo") or "")[:40]
        eventi.append({"tipo": tipo, "squadra": n.get("squadra"), "minuto": n.get("minuto"), "giocatore": giocatore,
                       "nota": _sigla_evento(n)})
    return pulisci_eventi(eventi)


def eventi_correnti(cronaca):
    """Gli eventi da stampare: quelli del resoconto (corretti a mano), altrimenti quelli delle note."""
    r = cronaca.get("resoconto") or {}
    return r["eventi"] if "eventi" in r else eventi_da_note(cronaca)


def gol_da_eventi(eventi):
    gol = {"casa": 0, "ospite": 0}
    for e in eventi:
        if e["tipo"] == "gol":
            gol[e["squadra"]] += 1
    return gol


def _distanza_minuti(a, b):
    (m1, r1), (m2, r2) = _minuti(a), _minuti(b)
    return abs(m1 - m2) * 100 + abs(r1 - r2)


def _unisci_eventi(cronaca, letti_da_ai):
    """Gli eventi sono quelli delle note, uno per nota: niente gol doppi, nessun cartellino perso.
    L'AI dà solo il nome a quelli senza giocatore scelto dal menu (stessa squadra, minuto più vicino)
    e aggiunge i cartellini citati in note generiche; i gol li decidono solo le note.
    Un evento dell'AI va con una nota solo se il minuto è vicino (entro 5'), per non mangiarne un altro."""
    ai = list(letti_da_ai or [])
    eventi = []
    for n in note_in_ordine(cronaca):
        tipo = _tipo_evento(n)
        squadra = n.get("squadra")
        if not tipo or squadra not in ("casa", "ospite"):
            continue
        candidati = [e for e in ai if e["tipo"] == tipo and e["squadra"] == squadra
                     and _distanza_minuti(e["minuto"], n.get("minuto")) <= 500]
        letto = min(candidati, key=lambda e: _distanza_minuti(e["minuto"], n.get("minuto"))) if candidati else {}
        if letto:
            ai.remove(letto)
        d = n.get("dettagli") or {}
        if tipo == "sostituzione":
            eventi.append({"tipo": tipo, "squadra": squadra, "minuto": n.get("minuto"),
                           "giocatore": _sostituzione(n), "nota": ""})
            continue
        eventi.append({"tipo": tipo, "squadra": squadra, "minuto": n.get("minuto"),
                       "giocatore": d.get("giocatore") or letto.get("giocatore") or "",
                       "nota": _sigla_evento(n) or letto.get("nota", "")})
    eventi += [e for e in ai if e["tipo"] in ("ammonizione", "espulsione")]
    return pulisci_eventi(eventi)


def ricalcola_eventi(cronaca):
    """Rifà marcatori e cartellini dalle note attuali (es. dopo averle corrette), senza chiamare l'AI."""
    r = cronaca.get("resoconto")
    if r:
        r["eventi"] = _unisci_eventi(cronaca, r.get("eventi_ai"))
        salva_cronaca(cronaca)


def genera_resoconto(api_key, cronaca, giocatori=None, battute=3000):
    """Articolo in stile giornalistico ed elenco di gol e cartellini, scritti a partire dalle note."""
    p = cronaca["partita"]
    gol_casa, gol_ospite = punteggio(cronaca)
    formazioni = ""
    for lato in ("casa", "ospite"):
        giocatori_lato = rosa(cronaca, lato)
        if not giocatori_lato:  # senza distinta collegata si usano i nomi passati
            giocatori_lato = [(i, pulisci_nome(g)) for i, g in enumerate((giocatori or {}).get(lato, []), 1) if g]
        if giocatori_lato:
            elenco = [f"{num} {nome}" for num, nome in giocatori_lato]
            formazioni += (f"\n{p.get(lato) or lato} – titolari: {', '.join(elenco[:11])}"
                           f"; a disposizione: {', '.join(elenco[11:]) or '—'}")

    prompt = (
        "Sei un giornalista sportivo che scrive per i quotidiani locali e i siti di calcio dilettantistico veneto. "
        "Scrivi il resoconto della partita usando SOLO i fatti presenti negli appunti presi a bordo campo dalla "
        "società: non inventare gol, nomi, minuti o episodi. Gli appunti sono stati in parte dettati a voce e "
        "trascritti in automatico: correggi gli errori evidenti di trascrizione e scrivi i nomi dei giocatori "
        "come nelle formazioni, se presenti. Nelle formazioni ogni nome è preceduto dal numero di maglia: se un "
        "appunto cita un numero ('il 9', 'numero 9') usa il giocatore con quel numero della squadra indicata. "
        "I giocatori scritti prima del punto negli appunti sono stati scelti da un menu e sono certi. Tono giornalistico, equilibrato e rispettoso degli avversari, in "
        "italiano corretto; nessun commento offensivo verso arbitro o avversari. "
        f"L'articolo deve essere di circa {battute} battute, con un attacco che dica risultato e chiave della gara, "
        "poi lo sviluppo in ordine cronologico.\n\n"
        f"Partita: {p.get('casa') or 'Casa'} - {p.get('ospite') or 'Ospite'}\n"
        f"Campionato: {p.get('campionato') or '—'}\nData: {p.get('data') or '—'}\n"
        f"Risultato secondo gli appunti: {gol_casa}-{gol_ospite}\n"
        f"Formazioni dalla distinta:{formazioni or ' non disponibili'}\n\n"
        f"APPUNTI (minuto – tipo – testo):\n{_note_per_prompt(cronaca) or '(nessuna nota)'}\n\n"
        "Rispondi SOLO con questo JSON:\n"
        "{\n"
        '  "titolo": "titolo breve e incisivo",\n'
        '  "articolo": "testo dell\'articolo, paragrafi separati da una riga vuota",\n'
        '  "eventi": [\n'
        '    {"tipo": "gol", "squadra": "casa", "minuto": "23\'", "giocatore": "ROSSI ANDREA", "nota": ""},\n'
        '    {"tipo": "ammonizione", "squadra": "ospite", "minuto": "40\'", "giocatore": "BIANCHI LUCA", "nota": ""}\n'
        "  ]\n"
        "}\n"
        "In eventi metti SOLO gol, ammonizioni ed espulsioni presenti negli appunti. tipo è gol, ammonizione o "
        "espulsione; squadra è casa o ospite (per un autogol: la squadra che ne beneficia, con nota 'aut.'); "
        "giocatore scritto come nelle formazioni (COGNOME NOME) o \"\" se non si sa; nota per 'rig.', 'aut.' "
        "o doppia ammonizione, altrimenti \"\"."
    )

    client = OpenAI(api_key=api_key, timeout=120.0, max_retries=2)
    risposta = client.chat.completions.create(
        model=MODELLO_TESTO,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    dati = json.loads(risposta.choices[0].message.content or "{}")
    resoconto = {
        "titolo": str(dati.get("titolo") or "").strip(),
        "articolo": str(dati.get("articolo") or "").strip(),
        "eventi_ai": pulisci_eventi(dati.get("eventi")),
        "risultato": f"{gol_casa}-{gol_ospite}",
        "generato": time.time(),
    }
    resoconto["eventi"] = _unisci_eventi(cronaca, resoconto["eventi_ai"])
    cronaca["resoconto"] = resoconto
    salva_cronaca(cronaca)
    return resoconto


def testo_semplice(cronaca):
    """Il resoconto come testo da copiare in una mail ai giornalisti."""
    r = cronaca.get("resoconto") or {}
    p = cronaca["partita"]
    eventi = eventi_correnti(cronaca)
    gol = gol_da_eventi(eventi)
    nomi = {"casa": p.get("casa") or "Casa", "ospite": p.get("ospite") or "Ospite"}
    righe = [
        f"{nomi['casa']} - {nomi['ospite']} {gol['casa']}-{gol['ospite']}",
        " · ".join(x for x in (p.get("campionato"), p.get("data")) if x),
        "",
    ]
    for tipo, etichetta in (("gol", "Marcatori"), ("ammonizione", "Ammoniti"), ("espulsione", "Espulsi"),
                            ("sostituzione", "Sostituzioni")):
        voci = [f"{e['minuto']} {e['giocatore']}{' (' + e['nota'] + ')' if e['nota'] else ''} ({nomi[e['squadra']]})".strip()
                for e in eventi if e["tipo"] == tipo]
        if voci:
            righe.append(f"{etichetta}: " + ", ".join(voci))
    righe += ["", r.get("titolo", "").upper(), "", r.get("articolo", "")]
    return "\n".join(righe).strip() + "\n"


# --- Distinta e referto -------------------------------------------------------

def giocatori_da_distinta(distinta):
    """{"casa": [nomi riga 1-20], "ospite": [...]} dalla distinta pubblicata."""
    giocatori = {}
    for lato in ("casa", "ospite"):
        elenco = ((distinta or {}).get(lato) or {}).get("giocatori") or []
        giocatori[lato] = [str(g.get("GIOCATORE") or "").strip() for g in elenco]
    return giocatori


def imposta_distinta(cronaca, distinta):
    """Collega alla cronaca la distinta della partita e ne riprende squadre, campionato e data.
    Le foto delle distinte si copiano la prima volta o se la distinta è cambiata (non si rimettono
    quelle tolte a mano)."""
    nuova = ((cronaca.get("distinta") or {}).get("aggiornato") != distinta.get("aggiornato")
             or "foto_distinte" not in cronaca)
    cronaca["distinta"] = distinta
    info = distinta.get("info_gara") or {}
    p = cronaca["partita"]
    # I dati della distinta pubblicata valgono più di quelli scritti a mano
    p["casa"] = (distinta.get("casa") or {}).get("squadra") or p.get("casa", "")
    p["ospite"] = (distinta.get("ospite") or {}).get("squadra") or p.get("ospite", "")
    p["campionato"] = info.get("campionato") or p.get("campionato", "")
    p["data"] = info.get("data") or p.get("data", "")
    if nuova:
        _copia_foto_distinte(cronaca)
    salva_cronaca(cronaca)


def _cartella_referto():
    cartella = os.path.join(_cartella_dati(), "referto")
    os.makedirs(cartella, exist_ok=True)
    return cartella


def aggiungi_foto_referto(cronaca, dati_immagine, elenco="referto"):
    """Salva la foto ridotta (max 1800 px, orientamento corretto) in JPEG e la aggiunge all'elenco
    della cronaca: "referto" (referto dell'arbitro) o "foto_distinte"."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(dati_immagine)))
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((1800, 1800))
    nome = f"{uuid.uuid4().hex[:10]}.jpg"
    percorso = os.path.join(_cartella_referto(), nome)
    img.save(percorso, format="JPEG", quality=85)
    _carica_online(f"foto/{nome}", percorso, "image/jpeg")
    cronaca.setdefault(elenco, []).append(nome)
    salva_cronaca(cronaca)
    return nome


def leggi_foto_referto(nome):
    return _leggi_file(os.path.join(_cartella_referto(), nome), f"foto/{nome}")


def togli_foto_referto(cronaca, nome, elenco="referto"):
    cronaca[elenco] = [n for n in cronaca.get(elenco, []) if n != nome]
    salva_cronaca(cronaca)
    if not any(nome in (cronaca.get(e) or []) for e in ELENCHI_FOTO):
        _cancella_foto([nome])


def _cancella_foto(nomi):
    """Toglie le foto dal disco dell'app e dall'archivio online (così lo spazio si libera davvero)."""
    for nome in nomi:
        try:
            os.remove(os.path.join(_cartella_referto(), nome))
        except OSError:
            pass
        _da_caricare.pop(f"foto/{nome}", None)
    _online(cloud.elimina_file, [f"foto/{n}" for n in nomi])


# --- Foto delle distinte pubblicate --------------------------------------------
# Restano solo sul disco dell'app (mai sul repository pubblico: contengono documenti
# e date di nascita) e passano alla cronaca quando questa si collega alla distinta.

def _cartella_distinte_pubblicate():
    cartella = os.path.join(_cartella_dati(), "distinte_pubblicate")
    os.makedirs(cartella, exist_ok=True)
    return cartella


def salva_foto_distinte_pubblicate(foto):
    """foto: {"casa": bytes, "ospite": bytes} come caricati (foto o PDF: vale la prima pagina)."""
    from pdf_immagini import immagini_jpeg

    cartella = _cartella_distinte_pubblicate()
    for vecchio in os.listdir(cartella):
        os.remove(os.path.join(cartella, vecchio))
    for lato in ("casa", "ospite"):
        if foto.get(lato):
            percorso = os.path.join(cartella, f"{lato}.jpg")
            with open(percorso, "wb") as f:
                f.write(immagini_jpeg(foto[lato])[0])
            _carica_online(f"distinte_pubblicate/{lato}.jpg", percorso, "image/jpeg")
        else:
            _online(cloud.elimina_file, [f"distinte_pubblicate/{lato}.jpg"])


def _copia_foto_distinte(cronaca):
    cartella = _cartella_distinte_pubblicate()
    nuove = []
    for lato in ("casa", "ospite"):
        try:
            nuove.append(_leggi_file(os.path.join(cartella, f"{lato}.jpg"), f"distinte_pubblicate/{lato}.jpg"))
        except OSError:
            pass  # foto di quella squadra non caricata
    if nuove:
        _cancella_foto(cronaca.get("foto_distinte") or [])  # le copie vecchie non servono più
        cronaca["foto_distinte"] = []
        for dati in nuove:
            aggiungi_foto_referto(cronaca, dati, "foto_distinte")


# --- Foto delle distinte caricate (partita in lavorazione) ---------------------
# Le foto appena caricate nella sezione Distinta restano sul disco e su Supabase finché la
# partita non si archivia o si cancella: si ritrovano dopo un riavvio o da un altro dispositivo.

def _cartella_in_lavorazione():
    cartella = os.path.join(_cartella_dati(), "in_lavorazione")
    os.makedirs(cartella, exist_ok=True)
    return cartella


def salva_distinta_caricata(lato, nome, dati):
    cartella = _cartella_in_lavorazione()
    percorso = os.path.join(cartella, lato)
    with open(percorso, "wb") as f:
        f.write(dati)
    with open(percorso + ".json", "w", encoding="utf-8") as f:
        json.dump({"nome": nome}, f, ensure_ascii=False)
    _carica_online(f"in_lavorazione/{lato}", percorso, "application/octet-stream")
    _carica_online(f"in_lavorazione/{lato}.json", percorso + ".json", "application/json")


def leggi_distinta_caricata(lato):
    """{"nome", "dati"} della foto caricata per quel lato, oppure None."""
    percorso = os.path.join(_cartella_in_lavorazione(), lato)
    try:
        info = json.loads(_leggi_file(percorso + ".json", f"in_lavorazione/{lato}.json"))
        return {"nome": info.get("nome") or lato, "dati": _leggi_file(percorso, f"in_lavorazione/{lato}")}
    except (OSError, ValueError):
        return None


def togli_distinte_caricate(lati=("casa", "ospite")):
    cartella = _cartella_in_lavorazione()
    percorsi = []
    for lato in lati:
        for nome in (lato, f"{lato}.json"):
            try:
                os.remove(os.path.join(cartella, nome))
            except OSError:
                pass
            _da_caricare.pop(f"in_lavorazione/{nome}", None)
            percorsi.append(f"in_lavorazione/{nome}")
    _online(cloud.elimina_file, percorsi)

