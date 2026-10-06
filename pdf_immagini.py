"""Trasforma un PDF caricato (distinta o referto) in immagini, una per pagina.

Le distinte e il referto possono arrivare come foto oppure come PDF (per esempio
la distinta ufficiale LND scaricata dal portale): da qui in poi l'app li tratta
sempre come immagini.
"""
import io

MAX_PAGINE = 10
DPI = 200  # abbastanza per leggere i nomi in tabella senza file enormi


def e_pdf(dati):
    return dati[:5] == b"%PDF-"


def pagine_pdf(dati, max_pagine=MAX_PAGINE):
    """Immagini PIL (RGB) delle prime pagine del PDF."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(dati)
    try:
        immagini = []
        for indice in range(min(len(pdf), max_pagine)):
            pagina = pdf[indice]
            immagini.append(pagina.render(scale=DPI / 72).to_pil().convert("RGB"))
        return immagini
    finally:
        pdf.close()


def immagini_jpeg(dati):
    """Il file come lista di immagini JPEG (bytes): una per pagina se è un PDF, altrimenti sé stesso."""
    if not e_pdf(dati):
        return [dati]
    risultato = []
    for img in pagine_pdf(dati):
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=90)
        risultato.append(buffer.getvalue())
    return risultato
