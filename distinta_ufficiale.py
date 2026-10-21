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
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

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
LOGO_LND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo_lnd.png")  # in alto a destra
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


def salva_distinte(stagione, nuove):
    """Più distinte nuove con una sola scrittura (es. tutte quelle del calendario)."""
    adesso = datetime.now().strftime("%Y-%m-%d %H:%M")
    dati = distinte_stagione(stagione)
    salvate = [{**d, "id": d.get("id") or uuid.uuid4().hex[:12], "aggiornata": adesso} for d in nuove]
    dati.update({d["id"]: d for d in salvate})
    _scrivi(stagione, dati)
    return salvate


def elimina_distinta(stagione, id_distinta):
    dati = distinte_stagione(stagione)
    if dati.pop(id_distinta, None) is not None:
        _scrivi(stagione, dati)


def ordinate(distinte):
    """Le distinte dalla partita più recente."""
    return sorted(distinte.values(), key=lambda d: (d.get("data", ""), d.get("aggiornata", "")), reverse=True)


def ultima_del_gruppo(distinte, gruppo, prima_del="9999", tranne=""):
    """L'ultima distinta con i giocatori di un gruppo squadra (prima di quella data), da cui ripartire
    per la prossima partita. Le distinte ancora vuote preparate dal calendario non contano."""
    return next((d for d in ordinate(distinte) if d.get("gruppo") == gruppo and d.get("giocatori")
                 and d.get("data", "") < prima_del and d.get("id") != tranne), None)


def in_elenco(distinte, oggi):
    """Per scegliere: prima le prossime partite (dalla più vicina), poi quelle passate (dalla più recente)."""
    prossime = sorted((d for d in distinte.values() if d.get("data", "") >= oggi), key=lambda d: d.get("data", ""))
    passate = [d for d in ordinate(distinte) if d.get("data", "") < oggi]
    return prossime + passate


def etichetta(d):
    giorno = data_da_iso(d.get("data"))
    return (f"{giorno:%d/%m/%Y} · " if giorno else "") + f"{d.get('casa', '')} - {d.get('ospite', '')}" + \
        (f" · {d['giornata']}" if d.get("giornata") else "")


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


def in_scadenza(distinta, persone):
    """[testo] per certificati e documenti validi il giorno della gara ma che scadono entro un mese (anagrafica.GIORNI_AVVISO):
    da rinnovare prima delle prossime partite. Vale per i giocatori e per le persone in panchina."""
    giorno = data_da_iso(distinta.get("data"))
    ids = [g["id"] for g in distinta.get("giocatori") or []] + list((distinta.get("ruoli") or {}).values()) + \
        list(distinta.get("panchina") or [])
    avvisi = []
    for i in dict.fromkeys(ids):
        r = persone.get(i)
        if not r:
            continue
        for campo, cosa in (("certificato_scadenza", "certificato medico"), ("documento_scadenza", "documento")):
            if r.get(campo) and stato_scadenza(r[campo], giorno) == "in scadenza":
                avvisi.append(f"{nome_stampa(r)}: il {cosa} scade il {data_da_iso(r[campo]):%d/%m/%Y}.")
    return avvisi


# --- PDF sul modello della società -------------------------------------------------------------

def _registra_font():
    """Carlito (licenza OFL, nella cartella fonts) per il PDF; senza i file resta Helvetica."""
    cartella = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    try:
        pdfmetrics.registerFont(TTFont("Carlito", os.path.join(cartella, "Carlito-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("Carlito-Bold", os.path.join(cartella, "Carlito-Bold.ttf")))
        registerFontFamily("Carlito", normal="Carlito", bold="Carlito-Bold", italic="Carlito",
                           boldItalic="Carlito-Bold")
        return "Carlito", "Carlito-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


FONT, FONT_B = _registra_font()
BLU = colors.HexColor("#14336B")  # titoli, numeri e bordi esterni
BLU_CHIARO = colors.HexColor("#E6ECF6")  # intestazioni delle tabelle
RIGA_ALTERNA = colors.HexColor("#F6F8FC")
LINEE = colors.HexColor("#8C96A8")
GRIGIO = colors.HexColor("#5B6475")


def _nome_ricco(r):
    """"<b>VENTURINI</b> Leonardo": il cognome in grassetto."""
    return f"<b>{_esc(str(r.get('cognome', '')))}</b> {_esc(str(r.get('nome', '')).title())}".strip()


def genera_pdf_distinta(distinta, persone, nome_societa):
    """persone: {id: scheda dell'anagrafica}. A4 verticale: intestazione, 20 calciatori, assistente,
    persone ammesse al recinto di gioco, panchina aggiuntiva, dichiarazione e firme."""
    buffer = io.BytesIO()
    margine = 22
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=margine, rightMargin=margine, topMargin=margine,
                            bottomMargin=margine, title=f"Distinta {distinta.get('casa', '')} - {distinta.get('ospite', '')}",
                            author=nome_societa)
    larga = A4[0] - 2 * margine
    s_val = ParagraphStyle("V", fontName=FONT, fontSize=12, leading=14, textColor=colors.black)
    s_etich = ParagraphStyle("E", fontName=FONT, fontSize=7.5, leading=8.5, alignment=2, textColor=GRIGIO)
    s_titolo = ParagraphStyle("T", fontName=FONT_B, fontSize=20, leading=23, alignment=1, textColor=BLU)
    s_testa = ParagraphStyle("H", fontName=FONT_B, fontSize=7, leading=8, alignment=1, textColor=BLU)
    s_piccolo = ParagraphStyle("P", fontName=FONT, fontSize=6.5, leading=7, alignment=1)
    s_mini = ParagraphStyle("m", parent=s_piccolo, fontSize=5.5, leading=6, textColor=BLU)
    s_cella = ParagraphStyle("c", fontName=FONT, fontSize=8.5, leading=8.5, alignment=1)
    s_num = ParagraphStyle("n", fontName=FONT_B, fontSize=12, leading=13, alignment=1, textColor=BLU)
    s_nome = ParagraphStyle("N", fontName=FONT, fontSize=11, leading=11)
    s_riga = ParagraphStyle("R", fontName=FONT, fontSize=8.5, leading=10)
    s_sezione = ParagraphStyle("S", fontName=FONT_B, fontSize=8.5, leading=10, alignment=1, textColor=BLU)
    s_dich = ParagraphStyle("D", fontName=FONT, fontSize=8, leading=10, alignment=4, textColor=GRIGIO)
    s_firma = ParagraphStyle("F", fontName=FONT_B, fontSize=10, leading=12, alignment=1, textColor=BLU)

    def campo(etichetta_, valore, larghezza):
        """Il valore su una riga sola: il carattere si rimpicciolisce se il testo è lungo (fino a 8 punti)."""
        corpo = 12
        while corpo > 8 and stringWidth(valore, FONT, corpo) > larghezza - 5:
            corpo -= 0.5
        stile = ParagraphStyle("V", parent=s_val, fontSize=corpo, leading=corpo + 2)
        return [Paragraph(_esc(etichetta_), s_etich), Paragraph(_esc(valore), stile)]

    # Intestazione: stemma a sinistra, società e dati della gara al centro, logo LND a destra
    giorno = data_da_iso(distinta.get("data"))
    gara = f"{distinta.get('casa', '')} - {distinta.get('ospite', '')}"
    dati_gara = Table([
        ["", Paragraph(_esc(nome_societa), s_titolo), "", ""],
        campo("Elenco dei calciatori che partecipano alla gara:", gara, 286) + ["", ""],
        campo("valevole per:", distinta.get("competizione", ""), 286) + ["", ""],
        campo("in programma il:", f"{giorno:%d/%m/%Y}" if giorno else "", 155) + campo("a:", distinta.get("localita", ""), 106),
        campo("stadio/campo:", distinta.get("campo", ""), 155) + campo("ore:", distinta.get("ora", ""), 106),
    ], colWidths=[95, 155, 25, 111])
    dati_gara.setStyle(TableStyle([
        ("SPAN", (1, 0), (3, 0)), ("SPAN", (1, 1), (3, 1)), ("SPAN", (1, 2), (3, 2)),
        ("FONTNAME", (0, 0), (-1, -1), FONT), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 1), (-1, -1), 1.5),
        ("LINEBELOW", (1, 1), (3, 2), 0.5, LINEE), ("LINEBELOW", (1, 3), (1, 4), 0.5, LINEE),
        ("LINEBELOW", (3, 3), (3, 4), 0.5, LINEE), ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
    ]))
    logo = _carica_logo(80) or ""
    try:  # il logo LND in alto a destra, come nel modulo
        larghezza, altezza = ImageReader(LOGO_LND).getSize()
        lnd = Image(LOGO_LND, width=54, height=54 * altezza / larghezza)
    except Exception:
        lnd = ""
    testa = Table([[logo, dati_gara, lnd]], colWidths=[larga - 450, 386, 64])
    testa.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), FONT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (0, 0), "CENTER"),
                               ("ALIGN", (2, 0), (2, 0), "CENTER"), ("VALIGN", (2, 0), (2, 0), "TOP"),
                               ("BOX", (0, 0), (-1, -1), 1.2, BLU), ("LINEBELOW", (0, 0), (-1, 0), 2.5, BLU),
                               ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 4),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))

    # Calciatori: 20 righe, ordinate per numero
    larghezze = [22, 17, 17, 17, 148, 20, 58, 60, 34, 62, 58, 16, 16]
    larghezze[4] += larga - sum(larghezze)
    dati = [
        [Paragraph("N°", s_testa), Paragraph("Data di nascita", s_testa), "", "",
         Paragraph("Cognome e Nome", s_testa), Paragraph("Cap.", s_testa), Paragraph("Matricola FIGC", s_testa),
         Paragraph("N. Tessera riconoscimento", s_mini), Paragraph("Documento di identificazione", s_testa), "", "",
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
            celle = [Paragraph(_esc(c), s_cella) if c is not None else Paragraph(_nome_ricco(r), s_nome)
                     for c in celle]
            dati.append([Paragraph(_esc(g.get("numero") or ""), s_num), *celle,
                         Paragraph(_esc(rilasciato(r)), s_piccolo), "", ""])
        else:
            dati.append([""] * len(larghezze))
    assistente = persone.get((distinta.get("ruoli") or {}).get(ASSISTENTE[0]))
    dati.append([Paragraph(f"<b>{ASSISTENTE[1]}</b>", ParagraphStyle("a", parent=s_riga, textColor=BLU)), "", "", "",
                 Paragraph(_nome_ricco(assistente) if assistente else "", s_riga), "",
                 Paragraph(_esc((assistente or {}).get("matricola", "")), s_cella), "",
                 Paragraph(_esc(SIGLE_DOCUMENTO.get((assistente or {}).get("documento_tipo"), "")), s_cella),
                 Paragraph(_esc((assistente or {}).get("documento_numero", "")), s_cella),
                 Paragraph(_esc(rilasciato(assistente or {})), s_piccolo), "", ""])
    ultima = len(dati) - 1
    tabella = Table(dati, colWidths=larghezze, rowHeights=[15, 11] + [17] * MAX_GIOCATORI + [19], repeatRows=0)
    stile = [
        ("GRID", (0, 0), (-1, -1), 0.4, LINEE), ("BOX", (0, 0), (-1, -1), 1.2, BLU),
        ("FONTNAME", (0, 0), (-1, -1), FONT), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("LINEBELOW", (0, 1), (-1, 1), 1, BLU), ("LINEABOVE", (0, ultima), (-1, ultima), 1, BLU),
        ("SPAN", (1, 0), (3, 0)), ("SPAN", (8, 0), (10, 0)),
        ("SPAN", (0, 0), (0, 1)), ("SPAN", (4, 0), (4, 1)), ("SPAN", (6, 0), (6, 1)), ("SPAN", (7, 0), (7, 1)),
        ("SPAN", (11, 0), (11, 1)), ("SPAN", (12, 0), (12, 1)),
        ("SPAN", (0, ultima), (3, ultima)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.5), ("RIGHTPADDING", (0, 0), (-1, -1), 1.5),
        ("LEFTPADDING", (4, 2), (4, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("BACKGROUND", (0, 0), (-1, 1), BLU_CHIARO), ("BACKGROUND", (0, ultima), (-1, ultima), BLU_CHIARO),
    ] + [("BACKGROUND", (0, 2 + i), (-1, 2 + i), RIGA_ALTERNA) for i in range(1, MAX_GIOCATORI, 2)]
    tabella.setStyle(TableStyle(stile))

    def ammessi(titolo, righe):
        """Tabella delle persone in panchina: etichetta, nome, tessera e documento."""
        colonne = [140, 200, 60, 34, 62]
        colonne.append(larga - sum(colonne))
        corpo = [[Paragraph(_esc(titolo), s_sezione), "",
                  Paragraph("N° Tessera FIGC", s_testa), Paragraph("Documento di identificazione", s_testa), "", ""],
                 ["", "", "", Paragraph("Tipo", s_testa), Paragraph("Numero", s_testa),
                  Paragraph("Rilasciato", s_testa)]]
        for etichetta_, r in righe:
            corpo.append([Paragraph(_esc(etichetta_), ParagraphStyle("e", parent=s_riga, textColor=GRIGIO)),
                          Paragraph(_nome_ricco(r) if r else "", s_riga),
                          Paragraph(_esc((r or {}).get("matricola", "")), s_cella),
                          Paragraph(_esc(SIGLE_DOCUMENTO.get((r or {}).get("documento_tipo"), "")), s_cella),
                          Paragraph(_esc((r or {}).get("documento_numero", "")), s_cella),
                          Paragraph(_esc(rilasciato(r or {})), s_piccolo)])
        t = Table(corpo, colWidths=colonne, rowHeights=[12, 9.5] + [13.5] * len(righe))
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, LINEE), ("BOX", (0, 0), (-1, -1), 1.2, BLU),
            ("FONTNAME", (0, 0), (-1, -1), FONT), ("LINEBELOW", (0, 1), (-1, 1), 1, BLU),
            ("SPAN", (0, 0), (1, 1)), ("SPAN", (2, 0), (2, 1)), ("SPAN", (3, 0), (5, 0)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 0), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
            ("BACKGROUND", (0, 0), (-1, 1), BLU_CHIARO),
        ] + [("BACKGROUND", (0, 2 + i), (-1, 2 + i), RIGA_ALTERNA) for i in range(1, len(righe), 2)]))
        return t

    ruoli = distinta.get("ruoli") or {}
    recinto = ammessi("Persone ammesse al recinto di gioco",
                      [(etichetta_, persone.get(ruoli.get(chiave))) for chiave, etichetta_ in RUOLI_PANCHINA])
    massaggiatore = ruoli.get(MASSAGGIATORE[0])
    extra = ([(MASSAGGIATORE[1], persone[massaggiatore])] if massaggiatore in persone else []) + \
        [(persone[i].get("qualifica") or persone[i].get("tipo", ""), persone[i])
         for i in distinta.get("panchina") or [] if i in persone and i != massaggiatore]
    extra = extra[:RIGHE_PANCHINA_AGGIUNTIVA]
    aggiuntiva = ammessi("Panchina aggiuntiva",
                         extra
                         + [("", None)] * (RIGHE_PANCHINA_AGGIUNTIVA - len(extra)))

    riga_firma, spazio = 190, 80
    bordo = (larga - 2 * riga_firma - spazio) / 2
    firme = Table([["", Paragraph("L'Arbitro", s_firma), "", Paragraph("Il Dirigente Accompagnatore", s_firma), ""],
                   [""] * 5],
                  colWidths=[bordo, riga_firma, spazio, riga_firma, bordo], rowHeights=[13, 20])
    firme.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("FONTNAME", (0, 0), (-1, -1), FONT),
                               ("LINEBELOW", (1, 1), (1, 1), 0.6, BLU), ("LINEBELOW", (3, 1), (3, 1), 0.6, BLU)]))

    doc.build([testa, Spacer(1, 4), tabella, Spacer(1, 4), recinto, Spacer(1, 4), aggiuntiva, Spacer(1, 4),
               Paragraph(_esc(DICHIARAZIONE), s_dich), Spacer(1, 6), firme])
    return buffer.getvalue()
