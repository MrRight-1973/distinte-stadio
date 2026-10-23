"""Modulo da far firmare a ogni tesserato (o ai genitori, se minorenne): informativa privacy (art. 13 GDPR)
e i due consensi facoltativi che l'app gestisce, foto e video e nome sulla pagina pubblica delle partite.

Il modulo esce già compilato con i dati della scheda (nome, nascita, squadra, genitore) e con le caselle
vuote: la risposta firmata si riporta poi a mano nella scheda dell'anagrafica. Il testo è un'impostazione
di partenza, da far controllare a chi segue la privacy per la società.
"""
import io
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from anagrafica import data_da_iso, e_calciatore
from distinta_ufficiale import BLU, BLU_CHIARO, FONT, FONT_B, GRIGIO, LINEE, _logo
from pdf_manager import LOGO_PATH, _esc

_S_TITOLO = ParagraphStyle("T", fontName=FONT_B, fontSize=16, leading=19, alignment=1, textColor=BLU)
_S_SOTTO = ParagraphStyle("t", fontName=FONT, fontSize=10, leading=12, alignment=1, textColor=GRIGIO)
_S_SEZ = ParagraphStyle("S", fontName=FONT_B, fontSize=10.5, leading=13, textColor=BLU, spaceBefore=8, spaceAfter=3)
_S_TESTO = ParagraphStyle("x", fontName=FONT, fontSize=8.6, leading=10.8, alignment=4)
_S_PUNTO = ParagraphStyle("p", parent=_S_TESTO, leftIndent=9, bulletIndent=0)
_S_PUNTO_SX = ParagraphStyle("q", parent=_S_PUNTO, alignment=0)
_S_DATO = ParagraphStyle("d", fontName=FONT, fontSize=9.5, leading=12)
_S_SCELTA = ParagraphStyle("c", fontName=FONT, fontSize=9.5, leading=11)
_S_FIRMA = ParagraphStyle("f", fontName=FONT, fontSize=8.5, leading=10, textColor=GRIGIO)


def minorenne(r, oggi=None):
    """Meno di 18 anni oggi, dalla data di nascita (o dall'anno). Senza nessuna delle due: minorenne se
    calciatore, per prudenza; dirigenti e staff sono adulti."""
    oggi = oggi or date.today()
    nascita = data_da_iso(r.get("nascita"))
    if nascita:
        return (oggi.year - nascita.year - ((oggi.month, oggi.day) < (nascita.month, nascita.day))) < 18
    anno = str(r.get("anno_nascita") or "")
    if anno.isdigit():
        return oggi.year - int(anno) <= 18
    return e_calciatore(r)


def _scelte(no):
    """Le due caselle vuote da spuntare a penna: «do il consenso» e il no."""
    voci = [Paragraph("do il consenso", _S_SCELTA), Paragraph(no, _S_SCELTA)]
    t = Table([["", voci[0], "", voci[1]]], colWidths=[11, 100, 11, 330], rowHeights=[11], hAlign="LEFT")
    t.setStyle(TableStyle([("BOX", (0, 0), (0, 0), 0.9, BLU), ("BOX", (2, 0), (2, 0), 0.9, BLU),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (1, 0), (1, 0), 5),
                           ("LEFTPADDING", (3, 0), (3, 0), 5), ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return Table([[t]], colWidths=[460], hAlign="LEFT", style=[("LEFTPADDING", (0, 0), (0, 0), 14),
                                                               ("TOPPADDING", (0, 0), (0, 0), 4)])


def _riga(etichetta, valore):
    return Paragraph(f"<font color='#5B6475' size='8'>{_esc(etichetta)}</font><br/>{valore or '&nbsp;'}", _S_DATO)


def _pagina(r, squadra, stagione, nome_societa, oggi):
    minore = minorenne(r, oggi)
    larga = A4[0] - 2 * 34
    societa = _esc(nome_societa)
    nome = f"<b>{_esc(r.get('cognome', ''))}</b> {_esc(str(r.get('nome', '')).title())}"
    nascita = data_da_iso(r.get("nascita"))
    nato = nascita.strftime("%d/%m/%Y") if nascita else (r.get("anno_nascita") or "")
    pezzi = []

    testa = Table([[_logo(LOGO_PATH, 58, 70),
                    [Paragraph(societa, _S_TITOLO), Paragraph("Informativa privacy e consensi", _S_SOTTO),
                     Paragraph(f"Stagione {_esc(stagione)}" + (f" · {_esc(squadra)}" if squadra else ""), _S_SOTTO)],
                    ""]], colWidths=[76, larga - 152, 76])
    testa.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    pezzi += [testa, Spacer(1, 8)]

    dati = [[_riga("Tesserato", nome), _riga("Nato il", _esc(nato))],
            [_riga("Squadra / ruolo", _esc(squadra or r.get("qualifica") or r.get("tipo") or "")),
             _riga("Matricola FIGC", _esc(r.get("matricola", "")))]]
    if minore:
        dati.append([_riga("Genitore o tutore", _esc(r.get("genitore", ""))), _riga("Telefono", _esc(r.get("telefono", "")))])
    tabella = Table(dati, colWidths=[larga * 0.62, larga * 0.38])
    tabella.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, BLU), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINEE),
                                 ("BACKGROUND", (0, 0), (-1, -1), BLU_CHIARO), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                 ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    pezzi.append(tabella)

    chi, di_chi = ("il minore", "del minore") if minore else ("l'interessato", "dell'interessato")
    pezzi.append(Paragraph("1. Informativa sul trattamento dei dati (art. 13 Regolamento UE 2016/679)", _S_SEZ))
    punti = [
        f"<b>Titolare del trattamento</b>: {societa} · sede ______________________________ · "
        "email ______________________",
        "<b>Dati trattati</b>: dati anagrafici e di contatto, matricola FIGC, tipo, numero e scadenza del documento "
        "d'identità, scadenza del certificato medico sportivo (mai il certificato né la foto del documento), "
        "presenze agli allenamenti, convocazioni e partecipazione alle gare.",
        "<b>Finalità e base giuridica</b>: tesseramento e svolgimento dell'attività sportiva, rapporti con la "
        "FIGC/LND e adempimenti previsti dalle norme federali e di legge. Per queste finalità il consenso non "
        "serve: senza questi dati non è possibile il tesseramento.",
        "<b>Distinte di gara</b>: nome, numero di maglia e data di nascita compaiono nella distinta consegnata "
        "all'arbitro, come richiesto dal regolamento.",
        "<b>Pagina pubblica delle partite</b>: la società pubblica online la distinta e la cronaca delle gare. "
        "Per i minorenni compaiono solo cognome e iniziale del nome, senza data di nascita, salvo diverso "
        "consenso qui sotto. È sempre possibile chiedere che compaia solo il numero di maglia.",
        "<b>Chi tratta i dati</b>: dirigenti e allenatori incaricati dalla società, ciascuno solo per la propria "
        "squadra; i fornitori dei servizi informatici usati dalla società, come responsabili del trattamento. "
        "I dati non sono venduti né usati per pubblicità.",
        "<b>Conservazione</b>: per la durata del tesseramento e poi per il tempo richiesto dalle norme federali e "
        "di legge; poi vengono cancellati.",
        "<b>Diritti</b>: accesso, rettifica, cancellazione, limitazione, opposizione e revoca dei consensi in "
        "qualsiasi momento, scrivendo al titolare; reclamo al Garante per la protezione dei dati personali "
        "(www.garanteprivacy.it).",
    ]
    # la prima riga ha spazi da compilare a penna: allineata a sinistra, senza giustificare
    pezzi += [Paragraph(p, _S_PUNTO_SX if i == 0 else _S_PUNTO, bulletText="•") for i, p in enumerate(punti)]

    pezzi.append(Paragraph("2. Consensi facoltativi", _S_SEZ))
    pezzi.append(Paragraph(f"Rispondere no non cambia niente per il tesseramento né per l'attività {di_chi}. "
                           "Ogni consenso si può revocare in qualsiasi momento.", _S_TESTO))
    nome_pagina = ("Il nome completo " + di_chi + " può comparire sulla pagina pubblica delle partite (distinta e "
                   "cronaca), sempre senza data di nascita.") if minore else (
                  "Il mio nome può comparire sulla pagina pubblica delle partite (distinta e cronaca).")
    for titolo, testo, no in (
            ("a) Foto e video", f"Foto e video in cui compare {chi}, fatti durante gare, allenamenti ed eventi, "
                                "possono essere pubblicati sui canali della società (sito, social, pagina delle "
                                "partite, materiale stampato).", "non do il consenso"),
            ("b) Nome sulla pagina pubblica", nome_pagina,
             "non do il consenso (compare solo il numero di maglia)")):
        pezzi.append(KeepTogether([
            Spacer(1, 5), Paragraph(f"<b>{titolo}</b>: {testo}", _S_TESTO),
            _scelte(no)]))

    pezzi.append(Spacer(1, 12))
    if minore:
        pezzi.append(Paragraph("Firma di entrambi i genitori o di chi esercita la responsabilità genitoriale. Se firma "
                               "un solo genitore, dichiara di farlo anche con il consenso dell'altro.", _S_TESTO))
        firme = [["Data ______________", "Firma ________________________________"],
                 ["", "Firma ________________________________"]]
    else:
        pezzi.append(Paragraph("Dichiaro di aver letto l'informativa.", _S_TESTO))
        firme = [["Data ______________", "Firma ________________________________"]]
    tabella = Table([[Paragraph(a, _S_FIRMA), Paragraph(b, _S_FIRMA)] for a, b in firme],
                    colWidths=[larga * 0.35, larga * 0.65], rowHeights=[30] * len(firme))
    tabella.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
    pezzi.append(tabella)
    return pezzi


def genera_moduli(persone, stagione, nome_societa, squadra_di=None, oggi=None):
    """Un PDF con una pagina per persona. squadra_di: {id: gruppo squadra della stagione}."""
    squadra_di = squadra_di or {}
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=34, rightMargin=34, topMargin=28, bottomMargin=28,
                            title="Informativa privacy e consensi", author=nome_societa)
    pezzi = []
    for i, r in enumerate(persone):
        if i:
            pezzi.append(PageBreak())
        pezzi += _pagina(r, squadra_di.get(r.get("id"), ""), stagione, nome_societa, oggi)
    doc.build(pezzi)
    return buffer.getvalue()

