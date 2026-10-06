import io
import os
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sponsor_manager import MAX_SPONSOR, distribuisci_righe

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "logo_azzurra.png")

# Gli sponsor arrivano normalmente dal repository della pagina (li gestisce la segreteria
# dal pannello). Questa cartella locale resta come riserva se GitHub non è raggiungibile
# o non ha ancora un elenco: basta aggiungere/togliere file (png, jpg), in ordine alfabetico.
SPONSOR_DIR = os.path.join(BASE_DIR, "sponsor")
SPONSOR_COLONNE = 5          # massimo di loghi per riga
SPONSOR_BOX_W = 100          # dimensione massima del singolo logo (punti)
SPONSOR_BOX_H = 50


def _elenco_sponsor():
    if not os.path.isdir(SPONSOR_DIR):
        return []
    return sorted(
        os.path.join(SPONSOR_DIR, f)
        for f in os.listdir(SPONSOR_DIR)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    )


def numero_sponsor():
    """Quanti loghi ci sono nella cartella locale di riserva."""
    return len(_elenco_sponsor())


def loghi_da_cartella_locale():
    """Contenuto (bytes) dei loghi nella cartella locale di riserva."""
    loghi = []
    for percorso in _elenco_sponsor():
        try:
            with open(percorso, "rb") as f:
                loghi.append(f.read())
        except OSError:
            continue
    return loghi


def _blocco_sponsor(stile_titolo, loghi_bytes):
    """Fascia sponsor a righe equilibrate e centrate; None se non ci sono loghi."""
    loghi = []
    for dati in list(loghi_bytes)[:MAX_SPONSOR]:
        try:
            w, h = ImageReader(io.BytesIO(dati)).getSize()
            scala = min(SPONSOR_BOX_W / w, SPONSOR_BOX_H / h)
            loghi.append(RLImage(io.BytesIO(dati), width=w * scala, height=h * scala))
        except Exception:
            continue  # un file illeggibile non deve bloccare il PDF
    if not loghi:
        return None

    larghezza_cella = SPONSOR_BOX_W + 6
    altezza_riga = SPONSOR_BOX_H + 8
    # Una tabella per ogni riga, così ogni riga resta centrata e le righe sono equilibrate
    righe_tabelle = []
    inizio = 0
    for quanti in distribuisci_righe(len(loghi), SPONSOR_COLONNE):
        gruppo = loghi[inizio:inizio + quanti]
        inizio += quanti
        riga = Table([gruppo], colWidths=[larghezza_cella] * len(gruppo), rowHeights=[altezza_riga])
        riga.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        righe_tabelle.append([riga])
    griglia = Table(righe_tabelle, colWidths=[520])
    griglia.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER')]))

    blocco = Table([[Paragraph("I NOSTRI SPONSOR", stile_titolo)], [griglia]], colWidths=[520])
    blocco.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('LINEABOVE', (0, 0), (-1, 0), 0.8, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 4),
    ]))
    return blocco


def _esc(valore):
    """Testo sicuro per i Paragraph di reportlab (che interpretano il markup)."""
    return "" if valore is None else escape(str(valore))


def _carica_logo(larghezza_target=50.0):
    if not os.path.exists(LOGO_PATH):
        return None
    try:
        w, h = ImageReader(LOGO_PATH).getSize()
        return RLImage(LOGO_PATH, width=larghezza_target, height=(h / w) * larghezza_target)
    except Exception:
        return None


def genera_pdf(casa, ospite, info_gara, qr_code_bytes=None, sponsor_loghi=None):
    """sponsor_loghi: lista di loghi (bytes) nell'ordine voluto; None = usa la cartella locale."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = elementi_distinta(casa, ospite, info_gara, qr_code_bytes)

    if sponsor_loghi is None:
        sponsor_loghi = loghi_da_cartella_locale()
    sponsor = _blocco_sponsor(_stile_didascalia(), sponsor_loghi)
    if sponsor is not None:
        story.append(Spacer(1, 14))
        story.append(sponsor)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _stile_didascalia():
    return ParagraphStyle('QrText', parent=getSampleStyleSheet()['Normal'], fontSize=7.5, leading=10,
                          textColor=colors.HexColor("#4A5568"), fontName="Helvetica-Bold", alignment=1)


def elementi_distinta(casa, ospite, info_gara, qr_code_bytes=None):
    """Intestazione gara e liste delle due squadre (con QR code se passato), come elementi del PDF.

    Serve sia al PDF della distinta sia al resoconto della cronaca, che la riporta senza QR.
    """
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=14, leading=16, textColor=colors.HexColor("#1A365D"), spaceAfter=2)
    info_style = ParagraphStyle('InfoStyle', parent=styles['Normal'], fontSize=8.5, leading=11, textColor=colors.HexColor("#2D3748"))
    team_title_style = ParagraphStyle('TeamTitle', parent=styles['Heading2'], fontSize=11, leading=13, textColor=colors.HexColor("#2B6CB0"), spaceBefore=2, spaceAfter=4)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=8, leading=9.5)
    bold_style = ParagraphStyle('BoldStyle', parent=styles['Normal'], fontSize=8, leading=9.5, fontName="Helvetica-Bold")
    qr_text_style = _stile_didascalia()

    elementi_sinistra = [
        Paragraph("<b>DISTINTE DI GARA UFFICIALI</b>", title_style),
        Spacer(1, 4),
    ]

    def campo(etichetta, chiave):
        valore = _esc(info_gara.get(chiave)).strip() or "—"
        return Paragraph(f"<b>{etichetta}:</b> {valore}", info_style)

    # Il campionato ha una riga intera (anche se lungo resta su una riga sola);
    # sotto, due colonne ordinate: data / arbitro e assistenti.
    tabella_info_dati = [
        [campo("CAMPIONATO", "campionato"), ""],
        [campo("DATA GARA", "data"), campo("ARBITRO", "arbitro")],
        [campo("ASSISTENTE 1", "assistente1"), campo("ASSISTENTE 2", "assistente2")],
    ]
    t_info = Table(tabella_info_dati, colWidths=[200, 260])
    t_info.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elementi_sinistra.append(t_info)

    img_logo = _carica_logo()
    t_header = Table([[elementi_sinistra, img_logo if img_logo else ""]], colWidths=[460, 50])
    t_header.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E0")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t_header)
    story.append(Spacer(1, 6))

    def genera_tabella_squadra(dati):
        elementi_squadra = [
            Paragraph(f"<b>{_esc(dati.get('squadra') or 'SQUADRA')}</b>", team_title_style),
            Paragraph(f"<b>ALLENATORE:</b> {_esc(dati.get('allenatore'))}", normal_style),
            Spacer(1, 5),
        ]

        tabella_dati = [[Paragraph("<b>N°</b>", bold_style), Paragraph("<b>GIOCATORE</b>", bold_style), Paragraph("<b>ANNO</b>", bold_style)]]
        for index, g in enumerate(dati.get('giocatori', [])):
            tabella_dati.append([
                Paragraph(_esc(g.get('N°') or index + 1), normal_style),
                Paragraph(_esc(g.get('GIOCATORE')), normal_style),
                Paragraph(_esc(g.get('ANNO')), normal_style),
            ])

        t = Table(tabella_dati, colWidths=[25, 185, 45])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2.2),
            ('TOPPADDING', (0, 0), (-1, -1), 2.2),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elementi_squadra.append(t)
        return elementi_squadra

    macro_tabella = Table(
        [[genera_tabella_squadra(casa), Paragraph("", normal_style), genera_tabella_squadra(ospite)]],
        colWidths=[255, 10, 255],
    )
    macro_tabella.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(macro_tabella)

    if qr_code_bytes:
        story.append(Spacer(1, 15))
        img_qr_pdf = RLImage(io.BytesIO(qr_code_bytes), width=90, height=90)

        t_qr_footer = Table([
            [img_qr_pdf],
            [Spacer(1, 3)],
            [Paragraph("INQUADRA DA SMARTPHONE PER ACCEDERE ALLA DISTINTA DIGITAL LIVE", qr_text_style)],
        ], colWidths=[520])
        t_qr_footer.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(t_qr_footer)

    return story
