"""Ricarica dai CSV scaricati dall'app (icona ⬇️ sopra le tabelle): liste dei giocatori e note gara.

I CSV di Streamlit hanno le stesse colonne delle tabelle; si accettano anche quelli
salvati da Excel (separatore ";" e codifica Windows).
"""
import csv
import io
import re
import uuid

import pandas as pd

from cronaca_manager import SCELTE_DETTAGLIO, TIPI_NOTA

NUM_RIGHE = 20


class CsvErrore(Exception):
    pass


def leggi_csv(dati):
    for codifica in ("utf-8-sig", "cp1252"):
        try:
            testo = dati.decode(codifica)
            break
        except UnicodeDecodeError:
            continue
    try:
        separatore = csv.Sniffer().sniff(testo.splitlines()[0] if testo.strip() else ",", ",;\t").delimiter
    except csv.Error:
        separatore = ","
    try:
        df = pd.read_csv(io.StringIO(testo), sep=separatore, dtype=str, keep_default_na=False)
    except Exception as e:
        raise CsvErrore(f"File CSV non leggibile: {e}") from e
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _colonna(df, *nomi):
    chiavi = {re.sub(r"[^a-z]", "", c.lower()): c for c in df.columns}
    return next((chiavi[n] for n in nomi if n in chiavi), None)


def griglia_da_csv(dati):
    """DataFrame della lista (N° 1-20, GIOCATORE, ANNO) da un CSV con le stesse colonne."""
    df = leggi_csv(dati)
    c_nome = _colonna(df, "giocatore", "cognomenome", "nome", "giocatori")
    if not c_nome:
        raise CsvErrore("Nel CSV manca la colonna GIOCATORE.")
    c_num, c_anno = _colonna(df, "n", "numero", "nmaglia", "maglia"), _colonna(df, "anno", "annonascita")
    righe = {i: {"N°": i, "GIOCATORE": "", "ANNO": ""} for i in range(1, NUM_RIGHE + 1)}
    liberi = []
    for _, r in df.iterrows():
        nome = str(r[c_nome]).strip()
        if not nome:
            continue
        anno = str(r[c_anno]).strip() if c_anno else ""
        try:
            numero = int(float(str(r[c_num]).strip())) if c_num else 0
        except ValueError:
            numero = 0
        if 1 <= numero <= NUM_RIGHE and not righe[numero]["GIOCATORE"]:
            righe[numero].update(GIOCATORE=nome, ANNO=anno)
        else:
            liberi.append((nome, anno))
    for nome, anno in liberi:  # numeri mancanti o doppi: nelle prime righe libere
        vuota = next((i for i in righe if not righe[i]["GIOCATORE"]), None)
        if vuota is None:
            raise CsvErrore(f"Troppi giocatori nel CSV: la lista ha {NUM_RIGHE} righe.")
        righe[vuota].update(GIOCATORE=nome, ANNO=anno)
    return pd.DataFrame(list(righe.values())).set_index("N°")


def _nome_numero(testo):
    """"ROSSI ANDREA (9)" -> ("ROSSI ANDREA", 9)."""
    m = re.match(r"^(.*?)\s*\((\d+)\)\s*$", testo.strip())
    return (m[1].strip(), int(m[2])) if m else (testo.strip(), None)


def _metti(dettagli, campo, testo):
    nome, numero = _nome_numero(testo)
    if nome:
        dettagli[campo] = nome
        if numero:
            dettagli[f"{campo}_n"] = numero


def dettagli_da_descrizione(tipo, testo):
    """Il contrario di descrizione_nota: dalla colonna Giocatori ai giocatori e alle scelte della nota."""
    dettagli = {}
    scelta = SCELTE_DETTAGLIO.get(tipo)
    opzioni = {o.lower(): o for o in scelta[2]} if scelta else {}
    for parte in [p.strip() for p in str(testo or "").split(",") if p.strip()]:
        basso = parte.lower()
        if tipo == "Sostituzione" and basso.startswith(("esce ", "entra ")):
            campo, resto = parte.split(" ", 1)
            _metti(dettagli, campo.lower(), resto)
        elif tipo == "Gol" and basso.startswith("autogol"):
            dettagli["come"] = "Autogol"
            if basso.startswith("autogol di "):
                _metti(dettagli, "giocatore", parte[len("autogol di "):])
        elif basso.startswith("assist "):
            _metti(dettagli, "assist", parte[len("assist "):])
        elif basso in opzioni:
            dettagli[scelta[0]] = opzioni[basso]
        elif "giocatore" not in dettagli:
            _metti(dettagli, "giocatore", parte)
    return dettagli


def note_da_csv(dati, nomi_squadre):
    """Note della cronaca da un CSV con le colonne Min., Tipo, Squadra, Giocatori, Commento.
    nomi_squadre: {"casa": nome, "ospite": nome} per riconoscere la colonna Squadra."""
    df = leggi_csv(dati)
    c_min, c_tipo = _colonna(df, "min", "minuto"), _colonna(df, "tipo")
    c_sq, c_gioc = _colonna(df, "squadra"), _colonna(df, "giocatori", "giocatore")
    c_testo = _colonna(df, "commento", "testo", "nota")
    if not (c_min and (c_testo or c_gioc)):
        raise CsvErrore("Il CSV non sembra un elenco di note: servono almeno le colonne Min. e Commento.")
    lati = {str(v).strip().lower(): k for k, v in nomi_squadre.items() if v}
    lati.update({"casa": "casa", "ospite": "ospite"})
    note = []
    for i, r in df.iterrows():
        tipo = str(r[c_tipo]).strip().capitalize() if c_tipo else "Nota"
        tipo = tipo if tipo in TIPI_NOTA else "Nota"
        testo = str(r[c_testo]).strip() if c_testo else ""
        giocatori = str(r[c_gioc]).strip() if c_gioc else ""
        if not (testo or giocatori):
            continue
        dettagli = dettagli_da_descrizione(tipo, giocatori) if tipo != "Nota" else {}
        if tipo == "Nota" and giocatori:
            testo = f"{giocatori}. {testo}".strip(". ")
        note.append({
            "id": uuid.uuid4().hex[:10], "ts": float(i), "minuto": str(r[c_min]).strip(), "tipo": tipo,
            "squadra": lati.get(str(r[c_sq]).strip().lower(), "") if c_sq else "",
            "testo": testo, "origine": "csv", "audio": None, "dettagli": dettagli,
        })
    return note


def unisci_note(esistenti, nuove):
    """Aggiunge le note nuove saltando quelle già presenti (stesso minuto, tipo, squadra e testo)."""
    chiave = lambda n: (n.get("minuto"), n.get("tipo"), n.get("squadra"), n.get("testo"))
    gia = {chiave(n) for n in esistenti}
    aggiunte = [n for n in nuove if chiave(n) not in gia]
    return esistenti + aggiunte, len(aggiunte)
