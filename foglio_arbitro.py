"""Lettura da foto del foglio dell'arbitro (calciatori ammoniti, espulsi e variazioni nelle formazioni)
per riempire la cronaca quando gli eventi non sono stati segnati a bordo campo.

La foto si legge con l'AI; gli eventi proposti si controllano prima di aggiungerli alle note.
"""
import base64
import io
import json

from openai import OpenAI
from PIL import Image

from cronaca_manager import _stesso_giocatore, rosa
from estrattore import MODELLO, costo_lettura, strisce_ingrandite

PROMPT = (
    "Sei un sistema OCR per il modulo LND che l'arbitro compila a fine gara: CALCIATORI AMMONITI, "
    "CALCIATORI ESPULSI, PERSONE ALLONTANATE ed EVENTUALI VARIAZIONI NELLE FORMAZIONI DELLE SQUADRE.\n"
    "Il modulo ha due colonne: a SINISTRA la Società OSPITANTE (squadra di casa), a DESTRA la Società "
    "OSPITATA (squadra ospite). Ogni riga compilata ha 'N.RO' (numero di maglia) e 'NOME e COGNOME'.\n"
    "Le variazioni sono righe 'al __' del __ t. esce il n. __ entra il n. __': il minuto, il tempo (1 o 2), "
    "il numero di chi esce e di chi entra.\n"
    "REGOLE:\n"
    "- Riporta solo le righe compilate. Le righe vuote o annullate con una barra ('\\\\' o '/') vanno ignorate.\n"
    "- I nomi come scritti, in MAIUSCOLO. Se il numero non è leggibile usa 0.\n"
    "- Ignora le persone allontanate (dirigenti, allenatori), le firme e le intestazioni.\n"
    "- risultato: i gol scritti accanto a 'RISULTATO' (casa e ospite), oppure null se non c'è.\n"
    "Rispondi SOLO con questo JSON:\n"
    "{\"casa\": {\"ammoniti\": [{\"numero\": 11, \"nome\": \"DANIELE ZAMBERLAN\"}], \"espulsi\": [], "
    "\"sostituzioni\": [{\"minuto\": 8, \"tempo\": 2, \"esce\": 6, \"entra\": 13}]}, "
    "\"ospite\": {\"ammoniti\": [], \"espulsi\": [], \"sostituzioni\": []}, \"risultato\": [1, 2]}"
)


def _jpeg(img, lato_massimo=2000):
    img = img.copy()
    img.thumbnail((lato_massimo, lato_massimo))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=90)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _intero(valore):
    try:
        return int(str(valore).strip())
    except (TypeError, ValueError):
        return 0


def leggi_foglio(api_key, dati_immagine, modello=MODELLO):
    """Ciò che è scritto sul foglio: {"casa": {...}, "ospite": {...}, "risultato": [g1, g2] | None, "costo"}."""
    if not api_key:
        raise ValueError("Chiave OPENAI_API_KEY non configurata nei secrets.")
    img = Image.open(io.BytesIO(dati_immagine))
    if img.mode != "RGB":
        img = img.convert("RGB")
    contenuto = [{"type": "text", "text": "Leggi il foglio. Seguono la foto intera e la stessa foto in strisce "
                                         "ingrandite dall'alto in basso (si sovrappongono un po')."},
                 {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_jpeg(img)}", "detail": "high"}}]
    contenuto += [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}", "detail": "high"}}
                  for b in strisce_ingrandite(img)]
    parametri = {"temperature": 0.0} if modello.startswith("gpt-4") else {"reasoning_effort": "low"}
    client = OpenAI(api_key=api_key, timeout=180.0, max_retries=2)
    risposta = client.chat.completions.create(
        model=modello, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": PROMPT}, {"role": "user", "content": contenuto}], **parametri)
    try:
        dati = json.loads(risposta.choices[0].message.content or "{}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Risposta AI non valida: {e}") from e

    letto = {"risultato": None}
    for lato in ("casa", "ospite"):
        parte = dati.get(lato) or {}
        letto[lato] = {
            "ammoniti": [{"numero": _intero(g.get("numero")), "nome": str(g.get("nome") or "").strip().upper()}
                         for g in parte.get("ammoniti") or [] if isinstance(g, dict)],
            "espulsi": [{"numero": _intero(g.get("numero")), "nome": str(g.get("nome") or "").strip().upper()}
                        for g in parte.get("espulsi") or [] if isinstance(g, dict)],
            "sostituzioni": [{"minuto": _intero(s.get("minuto")), "tempo": _intero(s.get("tempo")),
                              "esce": _intero(s.get("esce")), "entra": _intero(s.get("entra"))}
                             for s in parte.get("sostituzioni") or [] if isinstance(s, dict)],
        }
    r = dati.get("risultato")
    if isinstance(r, list) and len(r) == 2 and all(str(x).strip().isdigit() for x in r):
        letto["risultato"] = [int(r[0]), int(r[1])]
    uso = getattr(risposta, "usage", None)
    letto["costo"] = costo_lettura(modello, getattr(uso, "prompt_tokens", 0) or 0, getattr(uso, "completion_tokens", 0) or 0)
    return letto


def minuto_da_foglio(minuto, tempo, durata=45):
    """'al 8' del 2° t.' -> "53'"; oltre la durata del tempo -> recupero ("45+2'")."""
    if not minuto:
        return ""
    if tempo == 2:
        return f"{2 * durata}+{minuto - durata}'" if minuto > durata else f"{durata + minuto}'"
    return f"{durata}+{minuto - durata}'" if minuto > durata else f"{minuto}'"


def _giocatore(cronaca, lato, numero, nome=""):
    """(nome, numero) dalla distinta collegata; se il numero non c'è, il nome scritto sul foglio."""
    for n, nome_rosa in rosa(cronaca, lato):
        if numero and str(n) == str(numero):
            return nome_rosa, n
    return (nome or (f"N. {numero}" if numero else "")), (numero or None)


def _stesso(nota, proposta, campo):
    """Stesso giocatore: col numero di maglia se c'è in entrambe, altrimenti col nome."""
    n1, n2 = nota.get(f"{campo}_n"), proposta.get(f"{campo}_n")
    if n1 and n2:
        return str(n1) == str(n2)
    return _stesso_giocatore(nota.get(campo, ""), proposta.get(campo, ""))


def _corrisponde(nota, proposta):
    if nota.get("tipo") != proposta["tipo"] or nota.get("squadra") != proposta["squadra"]:
        return False
    nd, d = nota.get("dettagli") or {}, proposta["dettagli"]
    if proposta["tipo"] == "Sostituzione":
        return _stesso(nd, d, "esce") and _stesso(nd, d, "entra")
    return _stesso(nd, d, "giocatore")


def confronta(cronaca, letto):
    """Foglio dell'arbitro contro note prese in partita.

    Restituisce (dal_foglio, solo_note):
    - dal_foglio: gli eventi del foglio, ognuno con "stato" = "uguale" | "minuto" (in cronaca con un altro
      minuto) | "manca" (non in cronaca), e "nota" = la nota corrispondente, se c'è;
    - solo_note: le note di cartellini e sostituzioni che sul foglio non ci sono.
    """
    durata = int(cronaca.get("durata_tempo") or 45)
    note = [n for n in cronaca.get("note") or [] if n.get("tipo") in ("Ammonizione", "Espulsione", "Sostituzione")]
    usate = set()
    dal_foglio = []
    for p in _proposte(cronaca, letto, durata):
        nota = next((n for n in note if n["id"] not in usate and _corrisponde(n, p)), None)
        if nota:
            usate.add(nota["id"])
            stato = "minuto" if p["minuto"] and _minuto_diverso(nota.get("minuto"), p["minuto"]) else "uguale"
        else:
            stato = "manca"
        dal_foglio.append({**p, "stato": stato, "nota": nota})
    solo_note = [n for n in note if n["id"] not in usate and n.get("squadra") in ("casa", "ospite")]
    return dal_foglio, solo_note


def _minuto_diverso(a, b):
    from statistiche import minuto_numero
    return minuto_numero(a) != minuto_numero(b) or not str(a or "").strip()


def _proposte(cronaca, letto, durata):
    proposte = []
    for lato in ("casa", "ospite"):
        parte = letto.get(lato) or {}
        for tipo, elenco in (("Ammonizione", parte.get("ammoniti")), ("Espulsione", parte.get("espulsi"))):
            for g in elenco or []:
                nome, numero = _giocatore(cronaca, lato, g["numero"], g["nome"])
                if nome:
                    proposte.append({"tipo": tipo, "squadra": lato, "minuto": "",
                                     "dettagli": {"giocatore": nome, "giocatore_n": numero}})
        for s in parte.get("sostituzioni") or []:
            esce, n_esce = _giocatore(cronaca, lato, s["esce"])
            entra, n_entra = _giocatore(cronaca, lato, s["entra"])
            if esce or entra:
                proposte.append({"tipo": "Sostituzione", "squadra": lato,
                                 "minuto": minuto_da_foglio(s["minuto"], s["tempo"], durata),
                                 "dettagli": {"esce": esce, "esce_n": n_esce, "entra": entra, "entra_n": n_entra}})
    for p in proposte:
        p["dettagli"] = {k: v for k, v in p["dettagli"].items() if v}
    return proposte
