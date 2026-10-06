import base64
import io
import json
import re
from datetime import datetime

from openai import OpenAI
from PIL import Image, ImageOps

from pdf_immagini import e_pdf, pagine_pdf

MODELLO = "gpt-4o"
VALORI_VUOTI = {"", "N.D.", "ND", "N/A", "NONE", "NULL", "NON INDICATO"}
ETA_MINIMA_GIOCATORE = 5
ANNO_MINIMO = 1940


def pulisci_testo(testo):
    """Rimuove caratteri speciali inutili e standardizza in MAIUSCOLO"""
    if testo is None:
        return ""
    pulito = str(testo).replace("_", " ")
    pulito = re.sub(r"\s+", " ", pulito).strip().upper()
    return "" if pulito in VALORI_VUOTI else pulito


def normalizza_anno(anno_grezzo):
    """Isola l'anno di nascita e lo restituisce nel formato a 4 cifre (YYYY).

    Accetta "04", "'04", "2004" e anche la data di nascita completa
    ("19/08/2004", "17 10 05"): in quel caso l'anno è l'ultimo gruppo di cifre.
    Il range è da ANNO_MINIMO a (anno corrente - ETA_MINIMA_GIOCATORE).
    """
    if anno_grezzo is None:
        return ""
    anno_massimo = datetime.now().year - ETA_MINIMA_GIOCATORE

    gruppi = [g for g in re.findall(r"\d+", str(anno_grezzo)) if len(g) in (2, 4)]
    if not gruppi:
        return ""
    # Un anno a 4 cifre ha la precedenza; altrimenti l'anno è l'ultimo gruppo (GG MM AA)
    quattro = [g for g in gruppi if len(g) == 4]
    gruppo = quattro[-1] if quattro else gruppi[-1]
    if len(gruppo) == 2:
        anno = 2000 + int(gruppo)
        if anno > anno_massimo:
            anno -= 100
    else:
        anno = int(gruppo)
    if ANNO_MINIMO <= anno <= anno_massimo:
        return str(anno)
    return ""


def pulisci_societa(nome):
    """Nome società senza il codice di matricola LND davanti ("915577 A.S.D. ...")
    e senza la sigla tra parentesi in fondo ("... (A)")."""
    nome = pulisci_testo(nome)
    nome = re.sub(r"^\d{3,}\s+", "", nome)
    nome = re.sub(r"\s*\([A-Z]\)$", "", nome)
    return nome.strip()


def _chiave_squadra(nome):
    """Forma confrontabile del nome squadra: senza sigle societarie, spazi e punteggiatura."""
    nome = re.sub(r"\b(A\s*\.?\s*S\s*\.?\s*D|S\s*\.?\s*S\s*\.?\s*D|U\s*\.?\s*S|POL|AC|SSD|ASD|SRL)\b\.?", " ", nome.upper())
    return re.sub(r"[^A-Z0-9]", "", nome)


MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "sett": 9, "ott": 10, "nov": 11, "dic": 12,
}


def normalizza_data(data_grezza):
    """Riporta la data della gara nel formato GG/MM/AAAA, oppure "" se non è credibile.

    Accetta 02/11/2025, 2-11-25, 02.11.2025, "2 novembre 2025". Anni a 2 cifre = 20xx.
    Una data di gara realistica è tra tre anni fa e l'anno prossimo: questo
    scarta, per esempio, una data di nascita letta per errore.
    """
    if not data_grezza:
        return ""
    testo = str(data_grezza).strip().lower()

    giorno = mese = anno = None
    m = re.search(r"(\d{1,2})\s*[/\-.\s]\s*(\d{1,2})\s*[/\-.\s]\s*(\d{4}|\d{2})\b", testo)
    if m:
        giorno, mese, anno = int(m[1]), int(m[2]), int(m[3])
    else:
        m = re.search(r"(\d{1,2})\s*(?:°|º)?\s*([a-zà]+)\.?\s*(\d{4}|\d{2})\b", testo)
        if m and m[2] in MESI:
            giorno, mese, anno = int(m[1]), MESI[m[2]], int(m[3])
    if anno is None:
        return ""
    if anno < 100:
        anno += 2000

    anno_corrente = datetime.now().year
    if not (anno_corrente - 3 <= anno <= anno_corrente + 1):
        return ""
    try:
        return datetime(anno, mese, giorno).strftime("%d/%m/%Y")
    except ValueError:
        return ""


def unisci_scansioni(casa_raw, ospite_raw):
    """Riunisce i dati letti dalle due distinte, completando ciò che manca in una con l'altra.

    Ogni foto è la distinta di UNA società, ma l'intestazione riporta la gara con
    entrambe le squadre ("CASA - OSPITE"): si usa la lettura più diretta e, se
    manca, quella dell'altra foto.
    """
    def primo(*valori):
        return next((v for v in valori if v), "")

    avvisi = list(casa_raw.get("avvisi", [])) + list(ospite_raw.get("avvisi", []))

    # Le due foto caricate al contrario? La squadra della distinta "locale" è
    # quella scritta per seconda nell'intestazione della gara (o viceversa).
    sq_casa = _chiave_squadra(casa_raw.get("squadra", ""))
    sq_ospite = _chiave_squadra(ospite_raw.get("squadra", ""))
    gara_casa = _chiave_squadra(primo(casa_raw.get("squadra_casa"), ospite_raw.get("squadra_casa")))
    gara_ospite = _chiave_squadra(primo(casa_raw.get("squadra_ospite"), ospite_raw.get("squadra_ospite")))
    if (sq_casa and sq_casa == gara_ospite) or (sq_ospite and sq_ospite == gara_casa):
        avvisi.append(
            "Le due foto sembrano invertite: secondo l'intestazione della gara la distinta caricata "
            "come LOCALE è della squadra ospite. Controlla e, se serve, scambia le foto."
        )

    return {
        "campionato": primo(casa_raw.get("campionato"), ospite_raw.get("campionato")),
        "data": primo(casa_raw.get("data"), ospite_raw.get("data")),
        "nome_casa": primo(casa_raw.get("squadra"), casa_raw.get("squadra_casa"), ospite_raw.get("squadra_casa")),
        "nome_ospite": primo(ospite_raw.get("squadra"), ospite_raw.get("squadra_ospite"), casa_raw.get("squadra_ospite")),
        "all_casa": casa_raw.get("allenatore", ""),
        "all_ospite": ospite_raw.get("allenatore", ""),
        # Nelle categorie dilettantistiche ogni società porta il proprio assistente di parte
        "ass_casa": casa_raw.get("assistente_arbitro", ""),
        "ass_ospite": ospite_raw.get("assistente_arbitro", ""),
        "avvisi": avvisi,
    }


def _to_int(valore, default=0):
    try:
        return int(str(valore).strip())
    except (ValueError, TypeError):
        return default


def encode_image(uploaded_file):
    """Mantiene alta la risoluzione per l'OCR e corregge l'orientamento EXIF"""
    uploaded_file.seek(0)
    dati = uploaded_file.read()
    if e_pdf(dati):
        img = pagine_pdf(dati, max_pagine=1)[0]  # la distinta sta nella prima pagina
    else:
        img = Image.open(io.BytesIO(dati))
        img = ImageOps.exif_transpose(img)  # foto da smartphone spesso ruotate nei metadati
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    img.thumbnail((2000, 2000))
    buffer_img = io.BytesIO()
    img.save(buffer_img, format="JPEG", quality=95)
    return base64.b64encode(buffer_img.getvalue()).decode("utf-8")


def analizza_distinta(uploaded_file, ruolo_squadra, api_key):
    """Estrae società, data, campionato, allenatore e giocatori per la specifica squadra"""
    if not api_key:
        raise ValueError("Chiave OPENAI_API_KEY non configurata nei secrets.")

    client = OpenAI(api_key=api_key, timeout=90.0, max_retries=2)
    base64_image = encode_image(uploaded_file)

    focus_ruolo = (
        "Questa foto è la distinta della squadra OSPITE della gara."
        if ruolo_squadra == "OSPITE" else
        "Questa foto è la distinta della squadra LOCALE (di casa) della gara."
    )

    prompt_sistema = (
        "Sei un sistema OCR ad altissima precisione per distinte di gara di calcio dilettantistico italiano (FIGC/LND).\n"
        f"{focus_ruolo}\n\n"
        "COME SONO FATTE LE DISTINTE:\n"
        "- Ogni foto contiene l'elenco di UNA sola società. Il nome della società è il titolo in alto "
        "(es. 'Azzurra Duecarrare', 'BOCAR JUNIORS', '915577 A.S.D. PETTORAZZA SAN MARTINO'): "
        "se è preceduto da un codice numerico di matricola, NON includere il codice.\n"
        "- L'intestazione riporta la gara con entrambe le squadre, prima la squadra di casa e poi l'ospite, "
        "dopo diciture come 'Elenco dei calciatori che partecipano alla gara', 'Distinta Giocatori "
        "partecipanti alla gara', 'Distinta dei/delle giocatori/trici partecipanti alla gara'. "
        "Ignora sigle tra parentesi in fondo come '(A)'.\n"
        "- I formati possibili sono tre: modulo della società con colonne N | G M A | Cognome e Nome | Cap. V.C.; "
        "modulo con 'Numero Maglia' a sinistra e a destra; modulo ufficiale LND con un indice di riga stampato "
        "fuori dalla tabella (1-24) e la colonna 'N° del Ruolo'.\n"
        "- Il documento può essere una scansione, un file digitale, oppure una foto storta, piegata o di un foglio stampato.\n\n"
        "REGOLE RIGIDE DI SCANSIONE:\n"
        "1. squadra: il nome della società di QUESTA distinta, per esteso. Se non è leggibile con certezza usa \"\": non inventarlo.\n"
        "2. squadra_casa e squadra_ospite: le due squadre scritte nell'intestazione della gara ('CASA - OSPITE'). "
        "Se l'intestazione non c'è, usa \"\" per entrambe.\n"
        "3. data: la DATA DELLA GARA (vicino a 'in programma il', 'Data', 'da disputare il') in formato GG/MM/AAAA. "
        "Se l'anno è a 2 cifre (es. '27/9/26') riportalo così com'è. NON confonderla con le date di nascita, "
        "con la data di stampa in fondo al foglio, né con il numero della distinta.\n"
        "4. campionato: il testo dopo 'valevole per', 'Campionato' o 'del campionato' (es. 'Prima Categoria girone E').\n"
        "5. allenatore: il primo allenatore ('Allenatore', 'Allenatore Sig.', 'Allenatore 1'), non quello in seconda.\n"
        "6. assistente_arbitro: la persona nella riga 'Assistente', 'Assistente dell'Arbitro' o 'Assistente all'Arbitro "
        "(guardalinee)'. Riporta solo COGNOME NOME, senza data di nascita né numeri di tessera.\n"
        "7. giocatori: una voce per OGNI riga compilata della tabella, nell'ordine dall'alto in basso.\n"
        "   - numero: il numero di maglia. Nel modulo LND è la colonna 'N° del Ruolo' (NON l'indice di riga "
        "stampato fuori dalla tabella); negli altri moduli è la colonna 'N' o 'Numero Maglia'. "
        "Se è stato corretto a mano (es. 26 scritto sopra 12) usa il numero scritto a mano.\n"
        "   - cognome_nome: come scritto, COGNOME NOME. Nel modulo LND il nome è stampato in alto nella cella, "
        "più su della data di nascita e della matricola della STESSA riga: abbina ogni nome alla data e al numero "
        "della riga in cui si trova, senza slittare di una riga.\n"
        "   - anno_nascita: l'anno di nascita così come appare (es. '05', \"'05\", '2005'). Se c'è la data completa "
        "(es. '19/08/2004' o '17 10 05' nelle colonne G M A) riporta solo l'anno.\n"
        "8. Capitano e vice: cerca nella colonna 'Cap.', 'V.C.', 'Capitano V. Cap.' le sigle C o CAP. (capitano) "
        "e V, VC, V.C., V.CAP. o VICE (vice capitano), e riporta il NUMERO DI MAGLIA di quei giocatori.\n"
        "9. Correzioni a mano: un nome barrato va ignorato; vale il nome o il numero scritto a mano accanto. "
        "Le righe vuote non vanno riportate.\n"
        "10. Ignora tutto il resto: matricole FIGC, documenti di identità, tessere, dirigenti, massaggiatori, sponsor.\n\n"
        "Rispondi ESCLUSIVAMENTE con questo schema JSON:\n"
        "{\n"
        "  \"squadra\": \"NOME SOCIETA' DI QUESTA DISTINTA\",\n"
        "  \"squadra_casa\": \"\",\n"
        "  \"squadra_ospite\": \"\",\n"
        "  \"allenatore\": \"COGNOME NOME\",\n"
        "  \"assistente_arbitro\": \"COGNOME NOME\",\n"
        "  \"capitano_num\": 10,\n"
        "  \"vice_capitano_num\": 4,\n"
        "  \"data\": \"DD/MM/YYYY\",\n"
        "  \"campionato\": \"NOME CAMPIONATO\",\n"
        "  \"giocatori\": [\n"
        "    {\"numero\": 1, \"cognome_nome\": \"ROSSI ANDREA\", \"anno_nascita\": \"04\"}\n"
        "  ]\n"
        "}"
    )

    response = client.chat.completions.create(
        model=MODELLO,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt_sistema},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Esegui l'estrazione OCR della distinta {ruolo_squadra}."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}", "detail": "high"},
                    },
                ],
            },
        ],
        temperature=0.0,
    )

    risultato_grezzo = response.choices[0].message.content
    if not risultato_grezzo:
        raise ValueError(f"Il modello non ha restituito contenuto per la distinta {ruolo_squadra}.")

    try:
        dati = json.loads(risultato_grezzo.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Risposta AI non valida per la distinta {ruolo_squadra}: {e}") from e

    return normalizza_risposta(dati, ruolo_squadra)


def normalizza_risposta(dati, ruolo_squadra):
    """Pulisce la risposta del modello e la riporta alla griglia fissa di 20 righe."""
    dati["allenatore"] = pulisci_testo(dati.get("allenatore"))
    dati["assistente_arbitro"] = pulisci_testo(re.sub(r"\(.*?\)", "", str(dati.get("assistente_arbitro") or "")))
    dati["campionato"] = pulisci_testo(dati.get("campionato"))
    dati["data"] = normalizza_data(dati.get("data"))
    dati["squadra"] = pulisci_societa(dati.get("squadra"))
    dati["squadra_casa"] = pulisci_societa(dati.get("squadra_casa"))
    dati["squadra_ospite"] = pulisci_societa(dati.get("squadra_ospite"))

    cap_num = _to_int(dati.get("capitano_num"))
    vice_num = _to_int(dati.get("vice_capitano_num"))

    # Ogni giocatore va nella riga del suo numero di maglia. Chi ha un numero
    # oltre il 20 (o ripetuto, o illeggibile) non viene perso: finisce nella
    # prima riga libera, col numero vero tra parentesi, e la segreteria è avvisata.
    righe = {}
    fuori_posto = []
    for g in dati.get("giocatori") or []:
        if not isinstance(g, dict):
            continue
        nome = pulisci_testo(g.get("cognome_nome"))
        if not nome:
            continue
        num = _to_int(g.get("numero"))
        if num == cap_num and "(C)" not in nome:
            nome += " (C)"
        elif num == vice_num and "(VC)" not in nome:
            nome += " (VC)"
        giocatore = {"cognome_nome": nome, "anno_nascita": normalizza_anno(g.get("anno_nascita"))}
        if 1 <= num <= 20 and num not in righe:
            righe[num] = giocatore
        else:
            fuori_posto.append((num, giocatore))

    avvisi = []
    righe_libere = [i for i in range(1, 21) if i not in righe]
    for num, giocatore in fuori_posto:
        if not righe_libere:
            avvisi.append(f"Distinta {ruolo_squadra}: {giocatore['cognome_nome']} non entra nelle 20 righe.")
            continue
        riga = righe_libere.pop(0)
        etichetta = f"maglia {num}" if num > 0 else "numero di maglia non letto"
        avvisi.append(f"Distinta {ruolo_squadra}: {giocatore['cognome_nome']} ({etichetta}) messo alla riga {riga}, controlla.")
        if num > 0:
            giocatore = {**giocatore, "cognome_nome": f"{giocatore['cognome_nome']} ({num})"}
        righe[riga] = giocatore

    dati["giocatori"] = [
        {"N°": i, "GIOCATORE": righe[i]["cognome_nome"], "ANNO": righe[i]["anno_nascita"]}
        if i in righe else {"N°": i, "GIOCATORE": "", "ANNO": ""}
        for i in range(1, 21)
    ]
    dati["avvisi"] = avvisi
    return dati
