"""Presenze agli allenamenti, un file per anno sportivo nello spazio privato di Supabase.

presenze/<stagione>.json = {gruppo: {seduta: {id_ragazzo: stato}}}, con lo stato in STATI.
La seduta è la data "yyyy-mm-dd"; il secondo allenamento dello stesso giorno è "yyyy-mm-dd_2".
I ragazzi sono indicati con l'id della loro scheda in anagrafica, così un cambio di nome non perde lo storico.
Le sigle sono quelle delle tabelle del mister (C, A, P, D, Z), più infortunato e giustificato.
"""
import json
import os
import re
from datetime import date

from cronaca_manager import _cartella_dati, _carica_online, _leggi_file

STATI = ["completo", "parziale", "differenziato", "presenza", "assente", "infortunato", "giustificato"]
SIGLE = {"completo": "C", "parziale": "P", "differenziato": "D", "presenza": "Z", "assente": "A",
         "infortunato": "I", "giustificato": "G"}
DA_SIGLA = {v: k for k, v in SIGLE.items()}
SIGLE_TABELLA = ["C", "A", "P", "D", "Z"]  # le colonne delle tabelle del mister
IN_CAMPO = ("completo", "parziale", "differenziato")  # si è allenato: conta nella percentuale di presenza
VECCHI_STATI = {"presente": "completo"}  # salvati prima delle sigle del mister
MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
MESI_LUNGHI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre",
               "Ottobre", "Novembre", "Dicembre"]


def _nome_file(stagione):
    return "presenze_" + re.sub(r"[^0-9A-Za-z]+", "-", str(stagione)).strip("-") + ".json"


def _percorsi(stagione):
    nome = _nome_file(stagione)
    return os.path.join(_cartella_dati(), nome), f"presenze/{nome}"


def _stato(valore):
    return VECCHI_STATI.get(valore, valore)


def presenze_stagione(stagione):
    locale, online = _percorsi(stagione)
    try:
        dati = json.loads(_leggi_file(locale, online)) or {}
    except (OSError, ValueError):
        dati = {}
    if not isinstance(dati, dict):
        return {}
    return {g: {s: {i: _stato(v) for i, v in segnati.items()} for s, segnati in (sedute or {}).items()}
            for g, sedute in dati.items()}


def presenze_gruppo(stagione, gruppo):
    """{seduta: {id_ragazzo: stato}} di un gruppo squadra."""
    return presenze_stagione(stagione).get(gruppo) or {}


def giorno_di(seduta):
    """"2026-08-21_2" -> "2026-08-21"."""
    return seduta[:10]


def numero_di(seduta):
    """1 per il primo allenamento del giorno, 2 per il secondo..."""
    return int(seduta[11:]) if len(seduta) > 11 else 1


def seduta(giorno, numero=1):
    return giorno if numero <= 1 else f"{giorno}_{numero}"


def ordina(sedute):
    return sorted(sedute, key=lambda s: (giorno_di(s), numero_di(s)))


def etichetta_corta(chiave):
    """"2026-09-01" -> "01-set" come nelle tabelle del mister ("²" per il secondo allenamento del giorno)."""
    giorno = date.fromisoformat(giorno_di(chiave))
    return f"{giorno.day:02d}-{MESI[giorno.month - 1]}" + ("²" if numero_di(chiave) > 1 else "")


def salva_allenamento(stagione, gruppo, chiave, segnati):
    """Scrive (o sostituisce) un allenamento; rilegge il file appena prima di scrivere,
    così due allenatori di squadre diverse non si cancellano a vicenda."""
    segnati = {i: s for i, s in segnati.items() if s in STATI}
    dati = presenze_stagione(stagione)
    allenamenti = dati.setdefault(gruppo, {})
    if segnati:
        allenamenti[chiave] = segnati
    else:
        allenamenti.pop(chiave, None)
    _scrivi(stagione, dati)


def elimina_allenamento(stagione, gruppo, chiave):
    salva_allenamento(stagione, gruppo, chiave, {})


def _scrivi(stagione, dati):
    locale, online = _percorsi(stagione)
    with open(locale, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1)
    _carica_online(online, locale, "application/json")


def sposta_allenamento(stagione, gruppo, chiave, nuova, segnati):
    """Corregge un allenamento salvato, anche cambiandone la data (sostituisce quello della nuova data)."""
    dati = presenze_stagione(stagione)
    allenamenti = dati.setdefault(gruppo, {})
    allenamenti.pop(chiave, None)
    allenamenti[nuova] = {i: s for i, s in segnati.items() if s in STATI}
    _scrivi(stagione, dati)


def aggiungi_allenamenti(stagione, gruppo, sedute):
    """Scrive in un colpo solo più allenamenti ({seduta: {id: stato}}), sostituendo quelli con la stessa chiave."""
    dati = presenze_stagione(stagione)
    allenamenti = dati.setdefault(gruppo, {})
    for chiave, segnati in sedute.items():
        allenamenti[chiave] = {i: s for i, s in segnati.items() if s in STATI}
    _scrivi(stagione, dati)


def rinomina_gruppo(stagione, vecchio, nuovo):
    dati = presenze_stagione(stagione)
    if vecchio in dati:
        dati[nuovo] = {**dati.get(nuovo, {}), **dati.pop(vecchio)}
        _scrivi(stagione, dati)


def nel_periodo(allenamenti, dal=None, al=None):
    """Le sedute tra le due date (yyyy-mm-dd, comprese), in ordine."""
    return [s for s in ordina(allenamenti) if (not dal or giorno_di(s) >= dal) and (not al or giorno_di(s) <= al)]


def statistiche(allenamenti, dal=None, al=None):
    """{id_ragazzo: {uno per stato, "segnati", "percentuale"}} sugli allenamenti tra le due date (yyyy-mm-dd,
    comprese). La percentuale conta completi, parziali e differenziati sulle volte in cui il ragazzo è stato segnato."""
    conti = {}
    for chiave in nel_periodo(allenamenti, dal, al):
        for id_ragazzo, stato in allenamenti[chiave].items():
            voce = conti.setdefault(id_ragazzo, {s: 0 for s in STATI})
            if stato in STATI:
                voce[stato] += 1
    for voce in conti.values():
        voce["segnati"] = sum(voce[s] for s in STATI)
        voce["percentuale"] = round(100 * sum(voce[s] for s in IN_CAMPO) / voce["segnati"]) if voce["segnati"] else 0
    return conti


def mesi_della_stagione(stagione):
    """[(etichetta, dal, al)] da luglio a giugno, per il filtro delle statistiche."""
    try:
        primo = int(str(stagione)[:4])
    except ValueError:
        primo = date.today().year
    mesi = []
    for i in range(12):
        mese, anno = (7 + i - 1) % 12 + 1, primo + (7 + i - 1) // 12
        fine = date(anno + (mese == 12), mese % 12 + 1, 1).toordinal() - 1
        mesi.append((f"{MESI_LUNGHI[mese - 1]} {anno}", f"{anno}-{mese:02d}-01", date.fromordinal(fine).isoformat()))
    return mesi


# --- Tabelle del mister (PDF o CSV esportati dal suo foglio) -------------------------------------

_DATA = re.compile(r"^(\d{1,2})[-/.]([a-z]{3})", re.I)
_RIGA = re.compile(r"^(?P<nome>[^\d;,]+?)[\s;,]+(?:(?P<anno>(?:19|20)\d\d)[\s;,]+)?(?P<sigle>[A-Z](?:[\s;,]+[A-Z])*)"
                   r"(?=[\s;,]+\d|[\s;,]*$)")


def leggi_tabella(testo, stagione):
    """Dal testo della tabella del mister: {"stagione", "sedute": [chiavi], "righe": [(nome, anno, [stati])],
    "problemi": [testo]}. Le date sono "01-set"; l'anno lo dà l'anno sportivo (luglio-dicembre il primo,
    gennaio-giugno il secondo). Due colonne con la stessa data sono due allenamenti dello stesso giorno."""
    m = re.search(r"(20\d\d)\s*/\s*(20\d\d)", testo)
    primo = int(m[1]) if m else int(str(stagione)[:4])
    righe, problemi, sedute = [], [], []
    for linea in testo.splitlines():
        parole = [p for p in re.split(r"[\s;,]+", linea.strip()) if p]
        date_riga = [_DATA.match(p) for p in parole]
        if not sedute and sum(1 for d in date_riga if d) >= 2:
            contate = {}
            for d in filter(None, date_riga):
                mese = d[2].lower()
                if mese not in MESI:
                    continue
                n_mese = MESI.index(mese) + 1
                giorno = date(primo if n_mese >= 7 else primo + 1, n_mese, int(d[1])).isoformat()
                contate[giorno] = contate.get(giorno, 0) + 1
                sedute.append(seduta(giorno, contate[giorno]))
            continue
        if not sedute:
            continue
        r = _RIGA.match(linea.strip())
        if not r or "COGNOME" in r["nome"].upper():
            continue
        sigle = re.split(r"[\s;,]+", r["sigle"])
        nome = re.sub(r"\s+", " ", r["nome"]).strip().upper()
        if len(sigle) != len(sedute) or any(s not in DA_SIGLA for s in sigle):
            problemi.append(f"{nome}: {len(sigle)} sigle per {len(sedute)} allenamenti, riga saltata")
            continue
        righe.append((nome, r["anno"] or "", [DA_SIGLA[s] for s in sigle]))
    return {"stagione": f"{primo}/{str(primo + 1)[2:]}", "sedute": sedute, "righe": righe, "problemi": problemi}


def testo_da_pdf(dati):
    """Il testo di un PDF (le tabelle del mister esportate dal foglio di calcolo)."""
    import pypdfium2 as pdfium
    documento = pdfium.PdfDocument(dati)
    try:
        return "\n".join(pagina.get_textpage().get_text_range() for pagina in documento)
    finally:
        documento.close()


def testo_da_file(nome, dati):
    if nome.lower().endswith(".pdf"):
        return testo_da_pdf(dati)
    for codifica in ("utf-8-sig", "cp1252"):
        try:
            return dati.decode(codifica)
        except UnicodeDecodeError:
            continue
    return ""


def allenato_complessivo(stagioni, gruppi=None):
    """{id_ragazzo: (allenamenti svolti, allenamenti segnati)} sommando più anni sportivi e gruppi squadra
    (gruppi=None: tutti). Per affiancare la presenza agli allenamenti alle statistiche delle partite."""
    totali = {}
    for stagione in stagioni:
        for gruppo, allenamenti in presenze_stagione(stagione).items():
            if gruppi is not None and gruppo not in gruppi:
                continue
            for id_ragazzo, v in statistiche(allenamenti).items():
                svolti, segnati = totali.get(id_ragazzo, (0, 0))
                totali[id_ragazzo] = (svolti + sum(v[s] for s in IN_CAMPO), segnati + v["segnati"])
    return totali
