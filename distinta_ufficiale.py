"""📝 Crea distinta: l'elenco ufficiale dei calciatori e delle persone ammesse in panchina, preparato
dall'anagrafica e stampato sul modello della società (come la distinta cartacea da dare all'arbitro).

Le distinte di un anno sportivo stanno nello spazio privato di Supabase
(distinte_ufficiali/distinte_<stagione>.json = {id: distinta}) e contengono solo gli id delle schede:
documenti e matricole si leggono dall'anagrafica al momento della stampa. Niente va sulla pagina pubblica.
"""
import io
import json
import os
import re
import uuid
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from anagrafica import data_da_iso, stato_scadenza
from cronaca_manager import _cartella_dati, _carica_online, _leggi_file
from pdf_manager import _carica_logo, _esc

MAX_GIOCATORI = 20
RIGHE_PANCHINA_AGGIUNTIVA = 5
# Le persone ammesse al recinto di gioco, nell'ordine del modulo: (chiave, etichetta stampata)
RUOLI_PANCHINA = [("accompagnatore", "Dirigente Accompagnatore Sig."),
                  ("arbitro", "Dirigente Addetto all'Arbitro Sig."),
                  ("medico", "Medico Sociale Dott."),
                  ("allenatore", "Allenatore Sig."),
                  ("allenatore2", "Allenatore in seconda Sig."),
                  ("sanitario", "Operatore Sanitario Sig.")]
ASSISTENTE = ("assistente", "Assistente")  # l'assistente dell'arbitro messo dalla società
MASSAGGIATORE = ("massaggiatore", "Massaggiatore sportivo")  # prima riga della panchina aggiuntiva
SIGLE_DOCUMENTO = {"Carta d'identità": "C.I.", "Patente": "PAT", "Passaporto": "PASS"}
DICHIARAZIONE = ("Il sottoscritto Dirigente accompagnatore ufficiale dichiara, ai sensi dell'Art.61 N.O.I.F., che i "
                 "calciatori sopraindicati sono regolarmente tesserati e partecipano alla gara sotto la "
                 "responsabilità della Società di appartenenza.")


def _nome_file(stagione):
    return "distinte_" + re.sub(r"[^0-9A-Za-z]+", "-", str(stagione)).strip("-") + ".json"


def _percorsi(stagione):
    nome = _nome_file(stagione)
    return os.path.join(_cartella_dati(), nome), f"distinte_ufficiali/{nome}"


def distinte_stagione(stagione):
    """{id: distinta} delle distinte preparate in un anno sportivo."""
    locale, online = _percorsi(stagione)
    try:
        dati = json.loads(_leggi_file(locale, online)) or {}
    except (OSError, ValueError):
        dati = {}
    return dati if isinstance(dati, dict) else {}


def _scrivi(stagione, dati):
    locale, online = _percorsi(stagione)
    with open(locale, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1)
    _carica_online(online, locale, "application/json")


def salva_distinta(stagione, distinta):
    """Aggiunge o aggiorna una distinta (rilegge il file appena prima di scrivere); restituisce quella salvata."""
    distinta = {**distinta, "id": distinta.get("id") or uuid.uuid4().hex[:12],
                "aggiornata": datetime.now().strftime("%Y-%m-%d %H:%M")}
    dati = distinte_stagione(stagione)
    dati[distinta["id"]] = distinta
    _scrivi(stagione, dati)
    return distinta


def elimina_distinta(stagione, id_distinta):
    dati = distinte_stagione(stagione)
    if dati.pop(id_distinta, None) is not None:
        _scrivi(stagione, dati)


def ordinate(distinte):
    """Le distinte dalla partita più recente."""
    return sorted(distinte.values(), key=lambda d: (d.get("data", ""), d.get("aggiornata", "")), reverse=True)


def ultima_del_gruppo(distinte, gruppo):
    """L'ultima distinta di un gruppo squadra, da cui ripartire per la prossima partita."""
    return next((d for d in ordinate(distinte) if d.get("gruppo") == gruppo), None)


def etichetta(d):
    giorno = data_da_iso(d.get("data"))
    return (f"{giorno:%d/%m/%Y} · " if giorno else "") + f"{d.get('casa', '')} - {d.get('ospite', '')}"


def nome_stampa(r):
    """"VENTURINI Leonardo": cognome in maiuscolo e nome con l'iniziale maiuscola, come nel modulo."""
    return f"{r.get('cognome', '')} {str(r.get('nome', '')).title()}".strip()


def nascita_gma(r):
    """("26", "06", "'05"); con il solo anno di nascita, giorno e mese restano vuoti."""
    giorno = data_da_iso(r.get("nascita"))
    if giorno:
        return f"{giorno.day:02d}", f"{giorno.month:02d}", f"'{giorno:%y}"
    anno = str(r.get("anno_nascita") or "")
    return "", "", f"'{anno[2:]}" if len(anno) == 4 else ""


def rilasciato(r):
    """L'ente che ha rilasciato il documento, accorciato per la cella stretta del modulo."""
    testo = str(r.get("documento_rilascio") or "").upper()
    return re.sub(r"^COMUNE( DI)? ", "COM. ", testo)


def controlli(distinta, persone):
    """[testo] dei problemi da sistemare prima di stampare: dati mancanti e scadenze al giorno della gara."""
    giorno = data_da_iso(distinta.get("data"))
    problemi = []
    giocatori = distinta.get("giocatori") or []
    if len(giocatori) > MAX_GIOCATORI:
        problemi.append(f"Ci sono {len(giocatori)} giocatori: il modulo ne contiene al massimo {MAX_GIOCATORI}.")
    ids = [g["id"] for g in giocatori]
    if len(set(ids)) < len(ids):
        problemi.append("Lo stesso giocatore è in più righe.")
    numeri = [g.get("numero") for g in giocatori if g.get("numero")]
    doppi = sorted({n for n in numeri if numeri.count(n) > 1})
    if doppi:
        problemi.append("Numeri di maglia ripetuti: " + ", ".join(str(n) for n in doppi) + ".")
    capitani = [g for g in giocatori if g.get("cap") == "C"]
    if len(capitani) > 1:
        problemi.append("C'è più di un capitano.")
    for g in giocatori:
        r = persone.get(g["id"])
        if not r:
            problemi.append("Un giocatore della distinta non è più in anagrafica.")
            continue
        nome = nome_stampa(r)
        if not r.get("matricola"):
            problemi.append(f"{nome}: manca la matricola FIGC.")
        if not r.get("documento_numero"):
            problemi.append(f"{nome}: manca il documento d'identità.")
        for campo, cosa in (("certificato_scadenza", "il certificato medico"), ("documento_scadenza", "il documento")):
            if r.get(campo) and stato_scadenza(r[campo], giorno) == "scaduto":
                problemi.append(f"{nome}: il giorno della gara {cosa} è scaduto.")
    if not (distinta.get("ruoli") or {}).get("accompagnatore"):
        problemi.append("Manca il dirigente accompagnatore (firma la distinta).")
    return problemi


# --- PDF sul modello della società -------------------------------------------------------------

def genera_pdf_distinta(distinta, persone, nome_societa):
    """persone: {id: scheda dell'anagrafica}. A4 verticale: intestazione, 20 calciatori, assistente,
    persone ammesse al recinto di gioco, panchina aggiuntiva, dichiarazione e firme."""
    buffer = io.BytesIO()
    margine = 22
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=margine, rightMargin=margine, topMargin=margine,
                            bottomMargin=margine, title=f"Distinta {distinta.get('casa', '')} - {distinta.get('ospite', '')}")
    larga = A4[0] - 2 * margine
    s_val = ParagraphStyle("V", fontName="Helvetica", fontSize=11, leading=13)
    s_etich = ParagraphStyle("E", fontName="Helvetica", fontSize=7, leading=8, alignment=2)
    s_titolo = ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=17, leading=20, alignment=1)
    s_testa = ParagraphStyle("H", fontName="Helvetica-Bold", fontSize=6.5, leading=7.5, alignment=1)
    s_piccolo = ParagraphStyle("P", fontName="Helvetica", fontSize=6, leading=6.5, alignment=1)
    s_mini = ParagraphStyle("m", parent=s_piccolo, fontSize=5, leading=5.5)
    s_cella = ParagraphStyle("c", fontName="Helvetica", fontSize=7.5, leading=7.5, alignment=1)
    s_num = ParagraphStyle("n", fontName="Helvetica-Bold", fontSize=11, leading=12, alignment=1)
    s_nome = ParagraphStyle("N", fontName="Helvetica", fontSize=10, leading=10)
    s_riga = ParagraphStyle("R", fontName="Helvetica", fontSize=7.5, leading=9)
    s_dich = ParagraphStyle("D", fontName="Helvetica", fontSize=7.5, leading=9)
    nero = colors.black

    def campo(etichetta_, valore):
        return [Paragraph(_esc(etichetta_), s_etich), Paragraph(_esc(valore), s_val)]

    # Intestazione: stemma a sinistra, società e dati della gara a destra
    giorno = data_da_iso(distinta.get("data"))
    gara = f"{distinta.get('casa', '')} - {distinta.get('ospite', '')}"
    dati_gara = Table([
        ["", Paragraph(_esc(nome_societa), s_titolo), "", ""],
        campo("Elenco dei calciatori che partecipano alla gara:", gara) + ["", ""],
        campo("valevole per:", distinta.get("competizione", "")) + ["", ""],
        campo("in programma il:", f"{giorno:%d/%m/%Y}" if giorno else "") + campo("a:", distinta.get("localita", "")),
        campo("stadio/campo:", distinta.get("campo", "")) + campo("ore:", distinta.get("ora", "")),
    ], colWidths=[105, 200, 30, 97])
    dati_gara.setStyle(TableStyle([
        ("SPAN", (1, 0), (3, 0)), ("SPAN", (1, 1), (3, 1)), ("SPAN", (1, 2), (3, 2)),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 1), (-1, -1), 1),
        ("LINEBELOW", (1, 1), (3, 2), 0.6, nero), ("LINEBELOW", (1, 3), (1, 4), 0.6, nero),
        ("LINEBELOW", (3, 3), (3, 4), 0.6, nero), ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
    ]))
    logo = _carica_logo(78) or ""
    testa = Table([[logo, dati_gara]], colWidths=[larga - 440, 440])
    testa.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "CENTER"),
                               ("BOX", (0, 0), (-1, -1), 1, nero), ("LEFTPADDING", (1, 0), (1, 0), 0),
                               ("RIGHTPADDING", (1, 0), (1, 0), 4), ("TOPPADDING", (0, 0), (-1, -1), 4),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))

    # Calciatori: 20 righe, ordinate per numero
    larghezze = [22, 17, 17, 17, 148, 20, 58, 60, 34, 62, 58, 16, 16]
    larghezze[4] += larga - sum(larghezze)
    dati = [
        [Paragraph("<b>N</b>", s_testa), Paragraph("Data di Nascita", s_testa), "", "",
         Paragraph("<b>Cognome e Nome</b>", s_testa), Paragraph("Cap.", s_testa), Paragraph("Matricola FIGC", s_testa),
         Paragraph("N. Tessera riconoscimento", s_piccolo), Paragraph("Documento di identificazione", s_testa), "", "",
         Paragraph("amm", s_mini), Paragraph("esp", s_mini)],
        ["", Paragraph("G", s_testa), Paragraph("M", s_testa), Paragraph("A", s_testa), "",
         Paragraph("V.C.", s_testa), "", "", Paragraph("Tipo", s_testa), Paragraph("Numero", s_testa),
         Paragraph("Rilasciato", s_testa), "", ""],
    ]
    giocatori = sorted(distinta.get("giocatori") or [], key=lambda g: (g.get("numero") or 99))
    for i in range(MAX_GIOCATORI):
        if i < len(giocatori) and giocatori[i]["id"] in persone:
            g = giocatori[i]
            r = persone[g["id"]]
            # celle come paragrafi centrati: data di nascita e numeri stanno a metà riga
            celle = [*nascita_gma(r), None, g.get("cap") or "", r.get("matricola", ""), "",
                     SIGLE_DOCUMENTO.get(r.get("documento_tipo"), ""), r.get("documento_numero", "")]
            celle = [Paragraph(_esc(c), s_cella) if c is not None else Paragraph(_esc(nome_stampa(r)), s_nome)
                     for c in celle]
            dati.append([Paragraph(_esc(g.get("numero") or ""), s_num), *celle,
                         Paragraph(_esc(rilasciato(r)), s_piccolo), "", ""])
        else:
            dati.append([""] * len(larghezze))
    assistente = persone.get((distinta.get("ruoli") or {}).get(ASSISTENTE[0]))
    dati.append([Paragraph(ASSISTENTE[1], s_riga), "", "", "",
                 Paragraph(_esc(nome_stampa(assistente)).upper() if assistente else "", s_riga), "",
                 (assistente or {}).get("matricola", ""), "",
                 SIGLE_DOCUMENTO.get((assistente or {}).get("documento_tipo"), ""),
                 (assistente or {}).get("documento_numero", ""), "", "", ""])
    ultima = len(dati) - 1
    tabella = Table(dati, colWidths=larghezze, rowHeights=[16, 12] + [17] * MAX_GIOCATORI + [20], repeatRows=0)
    stile = [
        ("GRID", (0, 0), (-1, -1), 0.6, nero), ("BOX", (0, 0), (-1, -1), 1, nero),
        ("SPAN", (1, 0), (3, 0)), ("SPAN", (8, 0), (10, 0)),
        ("SPAN", (0, 0), (0, 1)), ("SPAN", (4, 0), (4, 1)), ("SPAN", (6, 0), (6, 1)), ("SPAN", (7, 0), (7, 1)),
        ("SPAN", (11, 0), (11, 1)), ("SPAN", (12, 0), (12, 1)),
        ("SPAN", (0, ultima), (3, ultima)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 2), (0, ultima - 1), "Helvetica-Bold"), ("FONTSIZE", (0, 2), (0, ultima - 1), 11),
        ("FONTSIZE", (1, 2), (3, ultima), 7), ("FONTSIZE", (5, 2), (-1, ultima), 7.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.5), ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#F2F2F2")),
    ]
    tabella.setStyle(TableStyle(stile))

    def ammessi(titolo, righe):
        """Tabella delle persone in panchina: etichetta, nome, tessera e documento."""
        colonne = [140, 200, 60, 34, 62]
        colonne.append(larga - sum(colonne))
        corpo = [[Paragraph(_esc(titolo), ParagraphStyle("t", parent=s_riga, alignment=1)), "",
                  Paragraph("N° Tessera FIGC", s_testa), Paragraph("Documento di identificazione", s_testa), "", ""],
                 ["", "", "", Paragraph("Tipo", s_testa), Paragraph("Numero", s_testa),
                  Paragraph("Rilasciato", s_testa)]]
        for etichetta_, r in righe:
            corpo.append([Paragraph(_esc(etichetta_), s_riga),
                          Paragraph(_esc(nome_stampa(r)).upper() if r else "", s_riga),
                          (r or {}).get("matricola", ""), SIGLE_DOCUMENTO.get((r or {}).get("documento_tipo"), ""),
                          (r or {}).get("documento_numero", ""),
                          Paragraph(_esc(rilasciato(r or {})), s_piccolo)])
        t = Table(corpo, colWidths=colonne, rowHeights=[11, 9] + [13.5] * len(righe))
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.6, nero), ("BOX", (0, 0), (-1, -1), 1, nero),
            ("SPAN", (0, 0), (1, 1)), ("SPAN", (2, 0), (2, 1)), ("SPAN", (3, 0), (5, 0)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 0), (-1, -1), "CENTER"),
            ("FONTSIZE", (0, 2), (-1, -1), 7.5), ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 0.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5), ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#F2F2F2")),
        ]))
        return t

    ruoli = distinta.get("ruoli") or {}
    recinto = ammessi("Persone ammesse al recinto di gioco",
                      [(etichetta_, persone.get(ruoli.get(chiave))) for chiave, etichetta_ in RUOLI_PANCHINA])
    massaggiatore = ruoli.get(MASSAGGIATORE[0])
    extra = ([(MASSAGGIATORE[1], persone[massaggiatore])] if massaggiatore in persone else []) + \
        [(persone[i].get("qualifica") or persone[i].get("tipo", ""), persone[i])
         for i in distinta.get("panchina") or [] if i in persone and i != massaggiatore]
    extra = extra[:RIGHE_PANCHINA_AGGIUNTIVA]
    aggiuntiva = ammessi("Panchina Aggiuntiva",
                         extra
                         + [("", None)] * (RIGHE_PANCHINA_AGGIUNTIVA - len(extra)))

    riga_firma, spazio = 180, 90
    bordo = (larga - 2 * riga_firma - spazio) / 2
    firme = Table([["", "L'Arbitro", "", "Il Dirigente Accompagnatore", ""], [""] * 5],
                  colWidths=[bordo, riga_firma, spazio, riga_firma, bordo], rowHeights=[14, 20])
    firme.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTSIZE", (0, 0), (-1, -1), 10),
                               ("LINEBELOW", (1, 1), (1, 1), 0.6, nero), ("LINEBELOW", (3, 1), (3, 1), 0.6, nero)]))

    doc.build([testa, tabella, Spacer(1, 5), recinto, Spacer(1, 5), aggiuntiva, Spacer(1, 4),
               Paragraph(_esc(DICHIARAZIONE), s_dich), Spacer(1, 6), firme])
    return buffer.getvalue()
