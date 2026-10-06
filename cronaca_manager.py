"""Cronaca della partita: cronometro, note (vocali o scritte) e resoconto per i giornalisti.

Il cronometro si basa sull'orario del server, non sul telefono: se lo schermo si
spegne o la pagina si ricarica, il minuto resta giusto. Le note sono salvate su
file a ogni modifica, così non si perdono se la connessione cade durante la gara.
"""
import io
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime

from openai import OpenAI

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
        "partita": {"casa": casa, "ospite": ospite, "campionato": campionato, "data": data},
        "durata_tempo": 45,
        "tempi": {},          # chiave fase -> {"inizio": ts, "fine": ts | None}
        "note": [],
        "resoconto": None,
        "distinta": None,     # distinta pubblicata (info_gara, casa, ospite)
        "referto": [],        # nomi dei file delle foto del referto
    }


def carica_cronaca():
    try:
        with open(_percorso_file(), encoding="utf-8") as f:
            dati = json.load(f)
        base = cronaca_vuota()
        base.update(dati)
        return base
    except (OSError, ValueError):
        return cronaca_vuota()


def salva_cronaca(cronaca):
    percorso = _percorso_file()
    temporaneo = percorso + ".tmp"
    with open(temporaneo, "w", encoding="utf-8") as f:
        json.dump(cronaca, f, ensure_ascii=False, indent=2)
    os.replace(temporaneo, percorso)  # scrittura atomica: il file non resta mai a metà


def archivia_e_azzera(cronaca, **partita):
    """Conserva la cronaca attuale (se ha note) con data e ora nel nome, poi ne apre una nuova."""
    if cronaca.get("note"):
        nome = datetime.now().strftime("cronaca_%Y%m%d_%H%M%S.json")
        with open(os.path.join(_cartella_dati(), nome), "w", encoding="utf-8") as f:
            json.dump(cronaca, f, ensure_ascii=False, indent=2)
    nuova = cronaca_vuota(**partita)
    salva_cronaca(nuova)
    return nuova


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
    """I giocatori scelti dai menu, in parole: "ROSSI ANDREA (9), assist BIANCHI LUCA (7)"."""
    d = nota.get("dettagli") or {}
    tipo = nota.get("tipo")
    if tipo == "Sostituzione":
        parti = [f"esce {_con_numero(d, 'esce')}" if d.get("esce") else "",
                 f"entra {_con_numero(d, 'entra')}" if d.get("entra") else ""]
    elif tipo == "Rigore":
        parti = [_con_numero(d, "giocatore"), (d.get("esito") or "").lower()]
    else:
        parti = [_con_numero(d, "giocatore"), f"assist {_con_numero(d, 'assist')}" if d.get("assist") else ""]
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
    with open(os.path.join(_cartella_dati(), "audio", nome), "wb") as f:
        f.write(dati_audio)
    return nome


def leggi_audio(nome):
    with open(os.path.join(_cartella_dati(), "audio", nome), "rb") as f:
        return f.read()


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
    for n in sorted(cronaca["note"], key=lambda x: x.get("ts", 0)):
        squadra = f" [{nomi[n['squadra']]}]" if n.get("squadra") in nomi else ""
        dettagli = descrizione_nota(n)
        commento = n.get("testo", "")
        testo = f"{dettagli}. {commento}" if dettagli and commento else (dettagli or commento)
        righe.append(f"{n.get('minuto', '')} – {n.get('tipo', 'Nota')}{squadra}: {testo}")
    return "\n".join(righe)


TIPI_EVENTO = ["gol", "ammonizione", "espulsione"]
_TIPO_DA_NOTA = {"Gol": "gol", "Ammonizione": "ammonizione", "Espulsione": "espulsione"}


def _minuti(minuto):
    """Chiave d'ordine per 23', 45+2', Pre-gara..."""
    numeri = [int(x) for x in "".join(c if c.isdigit() else " " for c in str(minuto)).split()]
    return (numeri[0] if numeri else 999, numeri[1] if len(numeri) > 1 else 0)


def pulisci_eventi(eventi):
    """Eventi validi (gol, ammonizioni, espulsioni), ordinati per tipo e minuto."""
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


def eventi_da_note(cronaca, solo_con_giocatore=False):
    """Eventi ricavati dalle note. Il giocatore è quello scelto dal menu; se manca, il testo della
    nota (bozza da correggere). Con solo_con_giocatore=True restano solo quelli col giocatore scelto."""
    eventi = []
    for n in cronaca.get("note") or []:
        d = n.get("dettagli") or {}
        if e_gol(n):
            tipo = "gol"
        elif n.get("tipo") in _TIPO_DA_NOTA:
            tipo = _TIPO_DA_NOTA[n["tipo"]]
        else:
            continue
        if solo_con_giocatore and not d.get("giocatore"):
            continue
        eventi.append({"tipo": tipo, "squadra": n.get("squadra"), "minuto": n.get("minuto"),
                       "giocatore": d.get("giocatore") or (n.get("testo") or "")[:40],
                       "nota": "rig." if n.get("tipo") == "Rigore" else ""})
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


def _unisci_eventi(scelti, letti_da_ai, bozza):
    """I giocatori scelti dai menu sono certi; l'AI completa solo gli eventi senza giocatore scelto."""
    chiavi = {(e["tipo"], e["squadra"], e["minuto"]) for e in scelti}
    altri = [e for e in (letti_da_ai or bozza) if (e["tipo"], e["squadra"], e["minuto"]) not in chiavi]
    return pulisci_eventi(scelti + altri)


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
        "eventi": _unisci_eventi(eventi_da_note(cronaca, solo_con_giocatore=True), pulisci_eventi(dati.get("eventi")),
                                 eventi_da_note(cronaca)),
        "risultato": f"{gol_casa}-{gol_ospite}",
        "generato": time.time(),
    }
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
    for tipo, etichetta in (("gol", "Marcatori"), ("ammonizione", "Ammoniti"), ("espulsione", "Espulsi")):
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
    """Collega alla cronaca la distinta della partita e ne riprende squadre, campionato e data."""
    cronaca["distinta"] = distinta
    info = distinta.get("info_gara") or {}
    p = cronaca["partita"]
    # I dati della distinta pubblicata valgono più di quelli scritti a mano
    p["casa"] = (distinta.get("casa") or {}).get("squadra") or p.get("casa", "")
    p["ospite"] = (distinta.get("ospite") or {}).get("squadra") or p.get("ospite", "")
    p["campionato"] = info.get("campionato") or p.get("campionato", "")
    p["data"] = info.get("data") or p.get("data", "")
    salva_cronaca(cronaca)


def _cartella_referto():
    cartella = os.path.join(_cartella_dati(), "referto")
    os.makedirs(cartella, exist_ok=True)
    return cartella


def aggiungi_foto_referto(cronaca, dati_immagine):
    """Salva la foto del referto ridotta (max 1800 px, orientamento corretto) in JPEG."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(dati_immagine)))
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.thumbnail((1800, 1800))
    nome = f"{uuid.uuid4().hex[:10]}.jpg"
    img.save(os.path.join(_cartella_referto(), nome), format="JPEG", quality=85)
    cronaca.setdefault("referto", []).append(nome)
    salva_cronaca(cronaca)
    return nome


def leggi_foto_referto(nome):
    with open(os.path.join(_cartella_referto(), nome), "rb") as f:
        return f.read()


def togli_foto_referto(cronaca, nome):
    cronaca["referto"] = [n for n in cronaca.get("referto", []) if n != nome]
    salva_cronaca(cronaca)
