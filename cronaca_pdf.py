"""PDF del resoconto di gara per i giornalisti.

Pagina 1: "Resoconto di gara ufficiale" con le liste della distinta (senza QR code), i gol
accanto ai nomi delle squadre, marcatori e cartellini, gli sponsor. Poi le foto del referto
dell'arbitro, la cronaca (titolo e articolo) e per ultima la cronologia degli appunti.
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image as RLImage
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from cronaca_manager import descrizione_nota, eventi_correnti, gol_da_eventi, leggi_foto_referto
from pdf_manager import _blocco_sponsor, _esc, _stile_didascalia, elementi_distinta

BLU = colors.HexColor("#1A365D")
GRIGIO = colors.HexColor("#4A5568")
LINEA = colors.HexColor("#CBD5E0")
LARGHEZZA = 555  # A4 meno i margini


def _foto_referto(nome, larghezza_max, altezza_max):
    try:
        dati = leggi_foto_referto(nome)
        w, h = ImageReader(io.BytesIO(dati)).getSize()
    except Exception:
        return None  # una foto illeggibile non deve bloccare il PDF
    scala = min(larghezza_max / w, altezza_max / h)
    return RLImage(io.BytesIO(dati), width=w * scala, height=h * scala)


def genera_pdf_resoconto(cronaca, giocatori=None, sponsor_loghi=None):
    """sponsor_loghi: lista di bytes. giocatori non serve più (le liste vengono dalla distinta)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20,
                            title="Resoconto di gara ufficiale")
    styles = getSampleStyleSheet()
    s_sezione = ParagraphStyle("Sezione", parent=styles["Heading1"], fontSize=14, leading=16, textColor=BLU, spaceAfter=8)
    s_titolo = ParagraphStyle("Titolo", parent=styles["Heading1"], fontSize=19, leading=23, textColor=colors.black, spaceAfter=10)
    s_corpo = ParagraphStyle("Corpo", parent=styles["Normal"], fontSize=10.5, leading=15, spaceAfter=7, alignment=4)
    s_info = ParagraphStyle("Info", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=GRIGIO)
    s_piccolo = ParagraphStyle("Piccolo", parent=styles["Normal"], fontSize=8, leading=9.5)

    p = cronaca["partita"]
    r = cronaca.get("resoconto") or {}
    distinta = cronaca.get("distinta") or {}
    eventi = eventi_correnti(cronaca)
    story = []

    # 1. Resoconto di gara: liste, gol accanto alle squadre, marcatori e cartellini, sponsor
    casa = distinta.get("casa") or {"squadra": p.get("casa"), "giocatori": []}
    ospite = distinta.get("ospite") or {"squadra": p.get("ospite"), "giocatori": []}
    info = distinta.get("info_gara") or {"campionato": p.get("campionato"), "data": p.get("data")}
    story += elementi_distinta(casa, ospite, info, titolo="RESOCONTO DI GARA UFFICIALE",
                               gol=gol_da_eventi(eventi), eventi=eventi)
    if sponsor_loghi:
        blocco = _blocco_sponsor(_stile_didascalia(), sponsor_loghi)
        if blocco:
            story += [Spacer(1, 14), blocco]

    # 2. Referto dell'arbitro: una foto per pagina
    for nome in cronaca.get("referto") or []:
        foto = _foto_referto(nome, LARGHEZZA, 760)
        if foto:
            story += [PageBreak(), Paragraph("REFERTO DI GARA", s_sezione), foto]

    # 3. Cronaca: solo titolo e articolo
    if r.get("titolo") or r.get("articolo"):
        story += [PageBreak(), Paragraph("CRONACA DELLA PARTITA", s_sezione)]
        if r.get("titolo"):
            story.append(Paragraph(_esc(r["titolo"]), s_titolo))
        for paragrafo in (r.get("articolo") or "").split("\n\n"):
            if paragrafo.strip():
                story.append(Paragraph(_esc(paragrafo.strip()).replace("\n", "<br/>"), s_corpo))

    # 4. Cronologia: tutte le note originali, utili al giornalista per verificare
    note = sorted(cronaca.get("note") or [], key=lambda n: n.get("ts", 0))
    if note:
        nomi_squadre = {"casa": p.get("casa") or "Casa", "ospite": p.get("ospite") or "Ospite"}
        story += [PageBreak(), Paragraph("CRONOLOGIA DAGLI APPUNTI A BORDO CAMPO", s_sezione)]
        dati = [[Paragraph("<b>Min.</b>", s_piccolo), Paragraph("<b>Evento</b>", s_piccolo), Paragraph("<b>Nota</b>", s_piccolo)]]
        for n in note:
            evento = n.get("tipo") or "Nota"
            if n.get("squadra") in nomi_squadre:
                evento += f" – {nomi_squadre[n['squadra']]}"
            giocatori = descrizione_nota(n)
            nota = f"<b>{_esc(giocatori)}</b>" if giocatori else ""
            if n.get("testo"):
                nota += (" – " if nota else "") + _esc(n.get("testo"))
            dati.append([Paragraph(_esc(n.get("minuto")), s_piccolo), Paragraph(_esc(evento), s_piccolo),
                         Paragraph(nota, s_piccolo)])
        t = Table(dati, colWidths=[55, 130, LARGHEZZA - 185], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ("GRID", (0, 0), (-1, -1), 0.5, LINEA),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]))
        story.append(t)

    story += [Spacer(1, 10),
              Paragraph(f"A cura dell'Ufficio Stampa A.S.D. Azzurra Due Carrare · {datetime.now():%d/%m/%Y}", s_info)]
    doc.build(story)
    return buffer.getvalue()
