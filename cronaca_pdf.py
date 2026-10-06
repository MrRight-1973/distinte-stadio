"""PDF del resoconto partita per i giornalisti: articolo, tabellino e cronologia delle note."""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from cronaca_manager import punteggio
from pdf_manager import _blocco_sponsor, _carica_logo, _esc

BLU = colors.HexColor("#1A365D")
GRIGIO = colors.HexColor("#4A5568")
LINEA = colors.HexColor("#CBD5E0")


def genera_pdf_resoconto(cronaca, giocatori=None, sponsor_loghi=None):
    """giocatori: {"casa": [nomi riga 1-20], "ospite": [...]}; sponsor_loghi: lista di bytes."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=30, bottomMargin=30,
                            title="Resoconto partita")
    styles = getSampleStyleSheet()
    s_partita = ParagraphStyle("Partita", parent=styles["Normal"], fontSize=15, leading=19, fontName="Helvetica-Bold", textColor=BLU)
    s_info = ParagraphStyle("Info", parent=styles["Normal"], fontSize=9, leading=12, textColor=GRIGIO)
    s_titolo = ParagraphStyle("Titolo", parent=styles["Heading1"], fontSize=19, leading=23, textColor=colors.black, spaceBefore=10, spaceAfter=4)
    s_sommario = ParagraphStyle("Sommario", parent=styles["Normal"], fontSize=11.5, leading=15, fontName="Helvetica-Oblique", textColor=GRIGIO, spaceAfter=10)
    s_corpo = ParagraphStyle("Corpo", parent=styles["Normal"], fontSize=10.5, leading=15, spaceAfter=7, alignment=4)
    s_sezione = ParagraphStyle("Sezione", parent=styles["Heading2"], fontSize=11, leading=14, textColor=BLU, spaceBefore=12, spaceAfter=4)
    s_piccolo = ParagraphStyle("Piccolo", parent=styles["Normal"], fontSize=8.5, leading=11)
    s_piccolo_b = ParagraphStyle("PiccoloB", parent=s_piccolo, fontName="Helvetica-Bold")

    p = cronaca["partita"]
    r = cronaca.get("resoconto") or {}
    gol_casa, gol_ospite = punteggio(cronaca)
    risultato = r.get("risultato") or f"{gol_casa}-{gol_ospite}"
    story = []

    # Intestazione: squadre e risultato, campionato e data, logo a destra
    sinistra = [
        Paragraph(f"{_esc(p.get('casa') or 'Casa')} – {_esc(p.get('ospite') or 'Ospite')} &nbsp; {_esc(risultato)}", s_partita),
        Paragraph(" · ".join(_esc(x) for x in (p.get("campionato"), p.get("data")) if x) or "&nbsp;", s_info),
    ]
    logo = _carica_logo(45)
    testata = Table([[sinistra, logo or ""]], colWidths=[465, 50])
    testata.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 1, LINEA),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(testata)

    # Articolo
    if r.get("titolo"):
        story.append(Paragraph(_esc(r["titolo"]), s_titolo))
    if r.get("sommario"):
        story.append(Paragraph(_esc(r["sommario"]), s_sommario))
    for paragrafo in (r.get("articolo") or "").split("\n\n"):
        if paragrafo.strip():
            story.append(Paragraph(_esc(paragrafo.strip()).replace("\n", "<br/>"), s_corpo))

    # Tabellino
    story.append(Paragraph("TABELLINO", s_sezione))
    righe = []
    for lato in ("casa", "ospite"):
        nomi = [n for n in (giocatori or {}).get(lato, []) if n]
        if nomi:
            testo = ", ".join(_esc(n) for n in nomi[:11])
            if nomi[11:]:
                testo += ". A disposizione: " + ", ".join(_esc(n) for n in nomi[11:])
            righe.append([Paragraph(_esc(p.get(lato) or lato.upper()), s_piccolo_b), Paragraph(testo, s_piccolo)])
    for etichetta, chiave in (("Marcatori", "marcatori"), ("Ammoniti", "ammoniti"), ("Espulsi", "espulsi")):
        if r.get(chiave):
            righe.append([Paragraph(etichetta, s_piccolo_b), Paragraph(_esc(", ".join(r[chiave])), s_piccolo)])
    if r.get("note_tabellino"):
        righe.append([Paragraph("Note", s_piccolo_b), Paragraph(_esc(r["note_tabellino"]), s_piccolo)])
    if righe:
        t = Table(righe, colWidths=[95, 420])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINEA),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(t)

    # Cronologia: tutte le note originali, utili al giornalista per verificare
    note = sorted(cronaca.get("note") or [], key=lambda n: n.get("ts", 0))
    if note:
        nomi_squadre = {"casa": p.get("casa") or "Casa", "ospite": p.get("ospite") or "Ospite"}
        story.append(Paragraph("CRONOLOGIA DAGLI APPUNTI A BORDO CAMPO", s_sezione))
        dati = [[Paragraph("<b>Min.</b>", s_piccolo), Paragraph("<b>Evento</b>", s_piccolo), Paragraph("<b>Nota</b>", s_piccolo)]]
        for n in note:
            evento = n.get("tipo") or "Nota"
            if n.get("squadra") in nomi_squadre:
                evento += f" – {nomi_squadre[n['squadra']]}"
            dati.append([Paragraph(_esc(n.get("minuto")), s_piccolo), Paragraph(_esc(evento), s_piccolo),
                         Paragraph(_esc(n.get("testo")), s_piccolo)])
        t = Table(dati, colWidths=[55, 115, 345], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ("GRID", (0, 0), (-1, -1), 0.4, LINEA),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t)

    story.append(Spacer(1, 10))
    story.append(Paragraph(f"A cura dell'Ufficio Stampa A.S.D. Azzurra Due Carrare · {datetime.now():%d/%m/%Y}", s_info))

    if sponsor_loghi:
        blocco = _blocco_sponsor(ParagraphStyle("Sp", parent=s_piccolo_b, alignment=1, textColor=GRIGIO), sponsor_loghi)
        if blocco:
            story.append(Spacer(1, 14))
            story.append(blocco)

    doc.build(story)
    return buffer.getvalue()
