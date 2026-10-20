"""PDF delle statistiche: si sceglie quali parti stampare (riepilogo, risultati, giocatori, cartellini,
minuti partita per partita). Le tabelle larghe vanno su pagine orizzontali."""
import io
from datetime import datetime
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)

from giornata import etichetta_giornata
from pdf_manager import _carica_logo, _esc

BLU = colors.HexColor("#1A365D")
GRIGIO = colors.HexColor("#4A5568")
LINEA = colors.HexColor("#CBD5E0")
SFONDO = colors.HexColor("#E2E8F0")
ORA_ITALIANA = ZoneInfo("Europe/Rome")
MARGINE = 24
PARTITE_PER_TABELLA = 16  # colonne di minuti per tabella nella griglia partita per partita

PARTI = {
    "riepilogo": "Riepilogo",
    "risultati": "Risultati: gol fatti e subiti",
    "giocatori": "Giocatori",
    "cartellini": "Cartellini",
    "minuti": "Minuti partita per partita",
}

INTESTAZIONI_GIOCATORI = [("giocatore", "Giocatore"), ("convocazioni", "Conv."), ("presenze", "Pres."),
                          ("titolare", "Tit."), ("minuti", "Minuti"), ("media", "Min/p"), ("gol", "Gol"),
                          ("assist", "Assist"), ("ammonizioni", "Amm."), ("espulsioni", "Esp.")]


def _breve(etichetta):
    """Intestazione stretta per la griglia dei minuti: "9ª giornata · 01/09/2026 · @ BOCAR" -> "9ª<br/>01/09"."""
    parti = [p for p in etichetta.split(" · ") if not p.startswith(("vs ", "@ "))]
    giornata = next((p.split()[0] for p in parti if "giornata" in p), "")
    data = next((p[:5] for p in parti if "/" in p), "")
    return "<br/>".join(_esc(x) for x in (giornata, data) if x) or _esc(etichetta[:10])


def _stile_tabella(allinea_da=1):
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SFONDO),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, LINEA),
        ("ALIGN", (allinea_da, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ])


def genera_pdf_statistiche(squadra, campionato, riepilogo, per_partita, risultati, parti):
    """parti: le chiavi di PARTI da stampare, nell'ordine di PARTI."""
    buffer = io.BytesIO()
    verticale, orizzontale = A4, landscape(A4)
    doc = BaseDocTemplate(buffer, pagesize=verticale, title=f"Statistiche {squadra}",
                          leftMargin=MARGINE, rightMargin=MARGINE, topMargin=MARGINE, bottomMargin=MARGINE)
    doc.addPageTemplates([
        PageTemplate("verticale", [Frame(MARGINE, MARGINE, verticale[0] - 2 * MARGINE, verticale[1] - 2 * MARGINE)],
                     pagesize=verticale),
        PageTemplate("orizzontale", [Frame(MARGINE, MARGINE, orizzontale[0] - 2 * MARGINE,
                                           orizzontale[1] - 2 * MARGINE)], pagesize=orizzontale),
    ])
    larghezza = verticale[0] - 2 * MARGINE
    stili = getSampleStyleSheet()
    s_titolo = ParagraphStyle("T", parent=stili["Heading1"], fontSize=16, leading=19, textColor=BLU, spaceAfter=2)
    s_sezione = ParagraphStyle("S", parent=stili["Heading2"], fontSize=12, leading=14, textColor=BLU,
                               spaceBefore=10, spaceAfter=5)
    s_info = ParagraphStyle("I", parent=stili["Normal"], fontSize=8.5, leading=11, textColor=GRIGIO)
    s_cella = ParagraphStyle("C", parent=stili["Normal"], fontSize=8, leading=9.5)
    s_testa = ParagraphStyle("H", parent=s_cella, fontSize=7, leading=8.5, alignment=1)

    logo = _carica_logo()
    intestazione = [Paragraph(f"<b>STATISTICHE {_esc(squadra).upper()}</b>", s_titolo),
                    Paragraph(_esc(f"{campionato} · {len(risultati)} partite" if campionato
                                   else f"Tutti i campionati · {len(risultati)} partite"), s_info)]
    t = Table([[intestazione, logo or ""]], colWidths=[larghezza - 60, 60])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("LINEBELOW", (0, 0), (-1, -1), 1, LINEA),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story = [t]

    if "riepilogo" in parti:
        fatti, subiti = sum(r["fatti"] for r in risultati), sum(r["subiti"] for r in risultati)
        vinte = sum(r["fatti"] > r["subiti"] for r in risultati)
        pari = sum(r["fatti"] == r["subiti"] for r in risultati)
        dati = [["Partite", "Vinte", "Pari", "Perse", "Gol fatti", "Gol subiti", "Ammonizioni", "Espulsioni"],
                [len(risultati), vinte, pari, len(risultati) - vinte - pari, fatti, subiti,
                 sum(r["ammonizioni"] for r in riepilogo), sum(r["espulsioni"] for r in riepilogo)]]
        tab = Table(dati, colWidths=[larghezza / 8] * 8)
        tab.setStyle(_stile_tabella(0))
        story += [Paragraph(PARTI["riepilogo"], s_sezione), tab]

    if "risultati" in parti and risultati:
        dati = [["Giornata", "Data", "Avversario", "", "Fatti", "Subiti"]]
        for r in risultati:
            dati.append([etichetta_giornata(r["giornata"]), r["data"], Paragraph(_esc(r["avversario"]), s_cella),
                         "Casa" if r["in_casa"] else "Trasferta", r["fatti"], r["subiti"]])
        dati.append(["", "", Paragraph("<b>Totale</b>", s_cella), "",
                     sum(r["fatti"] for r in risultati), sum(r["subiti"] for r in risultati)])
        tab = Table(dati, colWidths=[70, 70, larghezza - 290, 60, 45, 45], repeatRows=1)
        stile = _stile_tabella(3)
        stile.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
        tab.setStyle(stile)
        story += [Paragraph(PARTI["risultati"], s_sezione), tab]

    if "giocatori" in parti and riepilogo:
        dati = [[testo for _, testo in INTESTAZIONI_GIOCATORI]]
        for r in riepilogo:
            media = round(r["minuti"] / r["presenze"]) if r["presenze"] else 0
            dati.append([Paragraph(_esc(r["giocatore"]), s_cella)]
                        + [media if k == "media" else r[k] for k, _ in INTESTAZIONI_GIOCATORI[1:]])
        tab = Table(dati, colWidths=[larghezza - 9 * 42] + [42] * 9, repeatRows=1)
        tab.setStyle(_stile_tabella())
        story += [Paragraph(PARTI["giocatori"], s_sezione), tab]

    if "cartellini" in parti:
        ammoniti = sorted((r for r in riepilogo if r["ammonizioni"] or r["espulsioni"]),
                          key=lambda r: (-r["espulsioni"], -r["ammonizioni"], r["giocatore"]))
        story.append(Paragraph(PARTI["cartellini"], s_sezione))
        if ammoniti:
            dati = [["Giocatore", "Ammonizioni", "Espulsioni", "Presenze"]]
            dati += [[Paragraph(_esc(r["giocatore"]), s_cella), r["ammonizioni"], r["espulsioni"], r["presenze"]]
                     for r in ammoniti]
            tab = Table(dati, colWidths=[larghezza - 210, 70, 70, 70], repeatRows=1)
            tab.setStyle(_stile_tabella())
            story.append(tab)
        else:
            story.append(Paragraph("Nessun cartellino.", s_info))

    if "minuti" in parti and per_partita:
        story += [NextPageTemplate("orizzontale"), PageBreak(), Paragraph(PARTI["minuti"], s_sezione)]
        larga = orizzontale[0] - 2 * MARGINE
        giocatori = [r["giocatore"] for r in riepilogo]
        for inizio in range(0, len(per_partita), PARTITE_PER_TABELLA):
            gruppo = per_partita[inizio:inizio + PARTITE_PER_TABELLA]
            intestazioni = [Paragraph(f"<b>{_breve(e)}</b>", s_testa) for e, _ in gruppo]
            dati = [["Giocatore"] + intestazioni]
            for g in giocatori:
                dati.append([Paragraph(_esc(g), s_cella)] + [m.get(g, 0) or "" for _, m in gruppo])
            colonna = min(42, (larga - 150) / len(gruppo))
            tab = Table(dati, colWidths=[min(170, larga - colonna * len(gruppo))] + [colonna] * len(gruppo),
                        repeatRows=1, hAlign="LEFT")
            tab.setStyle(_stile_tabella())
            story += [tab, Spacer(1, 8)]

    story += [Spacer(1, 10), Paragraph(
        "Minuti calcolati dalle sostituzioni e dalle espulsioni segnate in cronaca, sulla durata regolamentare. "
        f"Statistiche del {datetime.now(ORA_ITALIANA):%d/%m/%Y alle %H:%M}.", s_info)]
    doc.build(story)
    return buffer.getvalue()



LEGENDA_PRESENZE = {"C": "COMPLETO", "A": "ASSENTE", "P": "PARZIALE", "D": "DIFFERENZIATO", "Z": "PRESENZA",
                    "I": "INFORTUNATO", "G": "GIUSTIFICATO"}
SEDUTE_PER_TABELLA = 22


def genera_pdf_presenze(squadra, stagione, periodo, righe, sedute, sigle):
    """PDF delle presenze come le tabelle del mister: una riga per ragazzo con la sigla di ogni allenamento,
    poi quante volte e in che percentuale per ogni sigla.
    righe: [(nome, anno, [sigla o "" per ogni seduta])]; sedute: intestazioni ("01-set");
    sigle: le sigle di cui mostrare i totali, nell'ordine (es. ["C", "A", "P", "D", "Z"])."""
    buffer = io.BytesIO()
    pagina = landscape(A4)
    doc = BaseDocTemplate(buffer, pagesize=pagina, title=f"Presenze {squadra}",
                          leftMargin=MARGINE, rightMargin=MARGINE, topMargin=MARGINE, bottomMargin=MARGINE)
    doc.addPageTemplates([PageTemplate("orizzontale", [Frame(MARGINE, MARGINE, pagina[0] - 2 * MARGINE,
                                                              pagina[1] - 2 * MARGINE)], pagesize=pagina)])
    larga = pagina[0] - 2 * MARGINE
    stili = getSampleStyleSheet()
    s_titolo = ParagraphStyle("T", parent=stili["Heading1"], fontSize=15, leading=18, textColor=BLU, spaceAfter=2)
    s_info = ParagraphStyle("I", parent=stili["Normal"], fontSize=8.5, leading=11, textColor=GRIGIO)
    s_cella = ParagraphStyle("C", parent=stili["Normal"], fontSize=7.5, leading=9)
    s_testa = ParagraphStyle("H", parent=s_cella, fontSize=6.5, leading=8, alignment=1)

    legenda = "<br/>".join(f"<b>{k}</b> = {LEGENDA_PRESENZE[k]}" for k in sigle)
    logo = _carica_logo()

    def intestazione(cosa):
        testo = [Paragraph(f"<b>PRESENZA ALLENAMENTI {_esc(periodo).upper()}</b>", s_titolo),
                 Paragraph(_esc(f"{squadra} · stagione {stagione} · numero allenamenti {len(sedute)} · {cosa}"),
                           s_info)]
        t = Table([[testo, Paragraph(legenda, s_info), _carica_logo() if logo else ""]],
                  colWidths=[larga - 190, 130, 60])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("LINEBELOW", (0, 0), (-1, -1), 1, LINEA),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        return [t, Spacer(1, 8)]

    def totali(segnate):
        n = len([x for x in segnate if x]) or 1
        celle = []
        for k in sigle:
            quante = segnate.count(k)
            celle += [quante, f"{round(100 * quante / n)}%"]
        return celle

    testa_totali = [Paragraph(f"<b>{x}</b>", s_testa) for k in sigle for x in (k, f"{k}%")]
    colonna, nome_l, anno_l, tot_l = 24, 125, 32, 22
    insieme = nome_l + anno_l + colonna * len(sedute) + tot_l * len(testa_totali) <= larga
    blocchi = [range(0, len(sedute))] if insieme else \
        [range(i, min(i + SEDUTE_PER_TABELLA, len(sedute))) for i in range(0, len(sedute), SEDUTE_PER_TABELLA)]
    story = []
    for n_blocco, blocco in enumerate(blocchi, start=1):  # una tabella per foglio
        cosa = "allenamento per allenamento" + (f" ({n_blocco}/{len(blocchi)})" if len(blocchi) > 1 else "")
        dati = [[Paragraph("<b>NOME E COGNOME</b>", s_cella), Paragraph("<b>ANNO</b>", s_testa)]
                + [Paragraph("<b>" + _esc(sedute[i]).replace("-", "<br/>") + "</b>", s_testa) for i in blocco]
                + (testa_totali if insieme else [])]
        for nome, anno, segnate in righe:
            dati.append([Paragraph(_esc(nome), s_cella), anno] + [segnate[i] for i in blocco]
                        + (totali(segnate) if insieme else []))
        tab = Table(dati, colWidths=[nome_l, anno_l] + [colonna] * len(blocco)
                    + ([tot_l] * len(testa_totali) if insieme else []), repeatRows=1, hAlign="LEFT")
        stile = _stile_tabella()
        stile.add("FONTSIZE", (0, 0), (-1, -1), 7)
        for i, (_, _, segnate) in enumerate(righe, start=1):
            for j, b in enumerate(blocco):
                colore = {"A": "#FED7D7", "D": "#FEFCBF", "P": "#E9D8FD", "Z": "#BEE3F8", "I": "#FBD38D",
                          "G": "#E2E8F0"}.get(segnate[b])
                if colore:
                    stile.add("BACKGROUND", (2 + j, i), (2 + j, i), colors.HexColor(colore))
        tab.setStyle(stile)
        story += intestazione(cosa) + [tab, PageBreak()]
    if not insieme:
        dati = [[Paragraph("<b>NOME E COGNOME</b>", s_cella), Paragraph("<b>ANNO</b>", s_testa)] + testa_totali]
        dati += [[Paragraph(_esc(nome), s_cella), anno] + totali(segnate) for nome, anno, segnate in righe]
        tab = Table(dati, colWidths=[nome_l, anno_l] + [30] * len(testa_totali), repeatRows=1, hAlign="LEFT")
        tab.setStyle(_stile_tabella())
        story += intestazione("totali") + [tab, PageBreak()]

    story += intestazione("percentuale di allenamenti svolti") + [_grafico_presenze(righe, larga)]
    story += [Spacer(1, 6), Paragraph(
        "Allenamenti svolti = completo, parziale o differenziato (C, P, D), sugli allenamenti in cui il ragazzo è "
        f"segnato; la linea tratteggiata è la media. Stampato il {datetime.now(ORA_ITALIANA):%d/%m/%Y alle %H:%M}.",
        s_info)]
    doc.build(story)
    return buffer.getvalue()


def _grafico_presenze(righe, larghezza):
    """Barre orizzontali con la percentuale di allenamenti svolti (C, P, D) di ogni ragazzo, dal più presente."""
    from reportlab.graphics.shapes import Drawing, Line, Rect, String

    valori = []
    for nome, _, segnate in righe:
        segnati = [x for x in segnate if x]
        valori.append((nome, round(100 * sum(x in ("C", "P", "D") for x in segnati) / len(segnati)) if segnati else 0))
    valori.sort(key=lambda v: (-v[1], v[0]))
    riga, etichette, margine = 15, 150, 40
    alto = riga * len(valori) + 24
    barra_max = larghezza - etichette - margine
    disegno = Drawing(larghezza, alto)
    for x in (0, 25, 50, 75, 100):
        px = etichette + barra_max * x / 100
        disegno.add(Line(px, 12, px, alto, strokeColor=LINEA, strokeWidth=0.4))
        disegno.add(String(px, 2, f"{x}%", fontName="Helvetica", fontSize=6.5, fillColor=GRIGIO, textAnchor="middle"))
    for i, (nome, perc) in enumerate(valori):
        y = alto - (i + 1) * riga
        colore = "#2F855A" if perc >= 80 else "#D69E2E" if perc >= 60 else "#C53030"
        disegno.add(String(etichette - 6, y + 4, nome[:28], fontName="Helvetica", fontSize=7, textAnchor="end"))
        disegno.add(Rect(etichette, y + 1, barra_max * perc / 100, riga - 4, fillColor=colors.HexColor(colore),
                         strokeColor=None))
        disegno.add(String(etichette + barra_max * perc / 100 + 4, y + 4, f"{perc}%", fontName="Helvetica", fontSize=7))
    if valori:
        media = sum(p for _, p in valori) / len(valori)
        px = etichette + barra_max * media / 100
        disegno.add(Line(px, 12, px, alto, strokeColor=BLU, strokeWidth=1, strokeDashArray=[3, 2]))
    return disegno
