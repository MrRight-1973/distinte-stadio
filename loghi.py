"""Gli stemmi delle squadre del girone, presi dalla pagina della LND dalla GitHub Action "Classifiche".

Ogni stemma si copia una volta sola nello spazio pubblico di Supabase (loghi/<nome>.png), così non si rompe
se la LND cambia gli indirizzi e la pagina spettatori lo può mostrare. L'elenco squadra -> indirizzo sta in
impostazioni/loghi.json. Sono stemmi di società: dati pubblici, niente che riguardi i ragazzi.
"""
import base64
import json
import os
import re
import time

import archivio_cloud as cloud
from cronaca_manager import _cartella_dati, _carica_online, _leggi_file

PERCORSO_ONLINE = "impostazioni/loghi.json"
TIPI = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp", "image/gif": "gif",
        "image/svg+xml": "svg"}
MASSIMO = 400_000  # byte: uno stemma più grande non è uno stemma
_letto = {"quando": 0.0, "dati": None}


def _percorso():
    return os.path.join(_cartella_dati(), "loghi.json")


def tutti(fresco=False):
    """{nome squadra: indirizzo pubblico dello stemma}."""
    if not fresco and _letto["dati"] is not None and time.time() - _letto["quando"] < 60:
        return dict(_letto["dati"])
    grezzi = None
    if cloud.attivo():
        try:
            grezzi = cloud.scarica_file(PERCORSO_ONLINE)
        except cloud.ArchivioErrore:
            grezzi = None
        if grezzi is not None:
            with open(_percorso(), "wb") as f:
                f.write(grezzi)
    try:
        dati = json.loads(grezzi if grezzi is not None else _leggi_file(_percorso(), PERCORSO_ONLINE)) or {}
    except (OSError, ValueError):
        dati = {}
    dati = dati if isinstance(dati, dict) else {}
    _letto.update(quando=time.time(), dati=dati)
    return dict(dati)


def di(squadra, loghi=None):
    """L'indirizzo dello stemma di una squadra ('' se non c'è), senza badare a maiuscole e minuscole."""
    loghi = tutti() if loghi is None else loghi
    if squadra in loghi:
        return loghi[squadra]
    chiave = str(squadra or "").strip().lower()
    return next((u for n, u in loghi.items() if n.lower() == chiave), "")


def abbina(immagini, squadre):
    """{squadra: indirizzo dell'immagine sulla pagina} da [(indirizzo, testo vicino all'immagine)]: un'immagine
    va a una squadra solo se il testo vicino nomina quella squadra e nessun'altra."""
    trovati = {}
    for src, testo in immagini:
        testo = re.sub(r"\s+", " ", str(testo or "")).strip().lower()
        if not src or not testo:
            continue
        nomi = [s for s in squadre if re.search(r"(?<![^\W\d_])" + re.escape(s.lower()) + r"(?![^\W\d_])", testo)]
        nomi = [n for n in nomi if not any(n != a and n.lower() in a.lower() for a in nomi)]  # "Real Terme" in "Polisportiva Real Terme"
        if len(nomi) == 1 and nomi[0] not in trovati:
            trovati[nomi[0]] = src
    return trovati


def _nome_file(squadra):
    return re.sub(r"[^a-z0-9]+", "-", squadra.lower()).strip("-")[:60] or "squadra"


def dati_immagine(src):
    """(byte, tipo) di un'immagine scritta dentro la pagina (data:image/png;base64,...), altrimenti None."""
    m = re.match(r"data:(image/[\w+.-]+);base64,(.+)$", src or "", re.S)
    if not m:
        return None
    try:
        return base64.b64decode(m[2]), m[1]
    except ValueError:
        return None


def salva(squadra, dati, tipo):
    """Copia lo stemma nello spazio pubblico e lo segna nell'elenco. Restituisce l'indirizzo o ''."""
    tipo = (tipo or "").split(";")[0].strip().lower()
    if tipo not in TIPI or not dati or len(dati) > MASSIMO:
        return ""
    nome = f"loghi/{_nome_file(squadra)}.{TIPI[tipo]}"
    if not cloud.carica_pubblico(nome, dati, tipo):
        return ""
    url = cloud.url_pubblico(nome)
    loghi = tutti(fresco=True)
    loghi[squadra] = url
    with open(_percorso(), "w", encoding="utf-8") as f:
        json.dump(loghi, f, ensure_ascii=False, indent=1)
    _carica_online(PERCORSO_ONLINE, _percorso(), "application/json")
    _letto.update(quando=time.time(), dati=loghi)
    return url
