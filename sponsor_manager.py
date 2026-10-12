"""Gestione dei loghi sponsor: pulizia automatica, ordine, pubblicazione su GitHub.

Gli sponsor vivono nel repository della pagina spettatori:
    sponsor/NN_nome_xxxxxx.png   i loghi (già puliti e ridimensionati)
    sponsor.json                 l'elenco, nell'ordine in cui vanno mostrati

La pagina web e il PDF leggono entrambi da lì, quindi si aggiornano in un solo posto.
Questo modulo non dipende da Streamlit.
"""
import hashlib
import io
import json
import math
import os
import re
import time
import unicodedata
from datetime import datetime, timezone

from PIL import Image, ImageChops, ImageOps

from github_publisher import PubblicazioneErrore, elenca_cartella, leggi_file, pubblica_su_github

MAX_SPONSOR = 15
MAX_BYTE_UPLOAD = 8 * 1024 * 1024        # un logo più pesante di così non serve
LOGO_MAX_LARGHEZZA = 600                 # px: abbondante per pagina web e stampa A4
LOGO_MAX_ALTEZZA = 300
CARTELLA = "sponsor"
MANIFEST = "sponsor.json"
_NOME_FILE_VALIDO = re.compile(r"^[A-Za-z0-9_.\-]+$")


def prepara_logo(dati):
    """Rende uniforme un logo caricato: PNG su fondo bianco, senza margini vuoti, non gigante.

    Solleva ValueError con un messaggio comprensibile se il file non è utilizzabile.
    """
    if len(dati) > MAX_BYTE_UPLOAD:
        raise ValueError(f"file troppo grande (massimo {MAX_BYTE_UPLOAD // (1024 * 1024)} MB)")
    try:
        img = Image.open(io.BytesIO(dati))
        img.load()
    except Exception:
        raise ValueError("non è un'immagine leggibile (usa PNG o JPG)") from None

    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        fondo = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        fondo.alpha_composite(rgba)
        img = fondo
    img = img.convert("RGB")

    # ritaglia i margini bianchi, così ogni logo occupa tutto lo spazio che gli spetta
    bianco = Image.new("RGB", img.size, (255, 255, 255))
    diff = ImageChops.difference(img, bianco).convert("L").point(lambda p: 255 if p > 24 else 0)
    riquadro = diff.getbbox()
    if riquadro is None:
        raise ValueError("l'immagine sembra vuota o tutta bianca")
    margine = max(4, int(0.03 * max(img.size)))
    img = img.crop((
        max(riquadro[0] - margine, 0), max(riquadro[1] - margine, 0),
        min(riquadro[2] + margine, img.width), min(riquadro[3] + margine, img.height),
    ))
    if min(img.size) < 16:
        raise ValueError("l'immagine è troppo piccola per essere un logo")

    img.thumbnail((LOGO_MAX_LARGHEZZA, LOGO_MAX_ALTEZZA), Image.LANCZOS)  # rimpicciolisce soltanto
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def nome_leggibile(nome_file):
    """'cosmap_logo-2024.png' -> 'Cosmap Logo 2024' (usato come testo alternativo)."""
    base = os.path.splitext(os.path.basename(str(nome_file)))[0]
    return re.sub(r"[\s_\-]+", " ", base).strip().title() or "Sponsor"


def _slug(nome):
    base = os.path.splitext(os.path.basename(str(nome)))[0]
    s = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:30] or "logo"


def nome_file(indice, nome, png):
    """Nome del file nel repository: posizione + nome + impronta del contenuto.

    L'impronta evita che i telefoni mostrino un logo vecchio dalla cache
    quando si sostituisce un logo mantenendo lo stesso nome.
    """
    return f"{indice:02d}_{_slug(nome)}_{hashlib.sha1(png).hexdigest()[:6]}.png"


def distribuisci_righe(n, max_colonne):
    """Quanti loghi per riga, con righe equilibrate: 15 -> [5, 5, 5]; 10 -> [5, 5]; 9 -> [5, 4]; 7 -> [4, 3]."""
    if n <= 0:
        return []
    righe = math.ceil(n / max_colonne)
    base, extra = divmod(n, righe)
    return [base + 1 if i < extra else base for i in range(righe)]


def costruisci_pubblicazione(sponsor, file_esistenti):
    """Prepara i file da scrivere (e quelli da eliminare) per il nuovo elenco sponsor.

    sponsor: lista di {"nome": str, "png": bytes} nell'ordine desiderato.
    file_esistenti: nomi dei file già presenti nella cartella sponsor del repository.
    """
    if len(sponsor) > MAX_SPONSOR:
        raise ValueError(f"Massimo {MAX_SPONSOR} sponsor.")

    file_da_pubblicare = {}
    voci = []
    for i, s in enumerate(sponsor, start=1):
        nome = nome_file(i, s["nome"], s["png"])
        file_da_pubblicare[f"{CARTELLA}/{nome}"] = s["png"]
        voci.append({"file": nome, "nome": nome_leggibile(s["nome"])})

    manifest = {"sponsor": voci, "aggiornato": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    file_da_pubblicare[MANIFEST] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")

    mantenuti = {v["file"] for v in voci}
    for esistente in file_esistenti:
        if esistente not in mantenuti:
            file_da_pubblicare[f"{CARTELLA}/{esistente}"] = None  # logo tolto: va eliminato
    return file_da_pubblicare, manifest


def leggi_sponsor_pubblicati(token, repo, branch=None):
    """Sponsor attualmente pubblicati, come lista di {"nome", "png", "file"}.

    Restituisce None se nel repository non esiste ancora un elenco (sponsor.json).
    """
    grezzo = leggi_file(token, repo, MANIFEST, branch)
    if grezzo is None:
        return None
    try:
        voci = json.loads(grezzo.decode("utf-8")).get("sponsor", [])
    except (ValueError, AttributeError):
        raise PubblicazioneErrore("Il file sponsor.json nel repository non è valido.") from None

    risultato = []
    for v in voci[:MAX_SPONSOR]:
        nome_f = str(v.get("file", "")) if isinstance(v, dict) else ""
        if not _NOME_FILE_VALIDO.match(nome_f):
            continue
        png = None
        for tentativo in range(3):  # un file appena pubblicato può impiegare qualche secondo a essere leggibile
            png = leggi_file(token, repo, f"{CARTELLA}/{nome_f}", branch)
            if png is not None:
                break
            time.sleep(1.0)
        if png is None:
            continue  # file davvero mancante: lo si salta, il resto resta utilizzabile
        risultato.append({"nome": str(v.get("nome") or nome_f), "png": png, "file": nome_f})
    return risultato


def salva_sponsor(token, repo, sponsor, branch=None):
    """Pubblica l'elenco sponsor (nuovi loghi, ordine, eliminazioni) con un solo commit."""
    esistenti = elenca_cartella(token, repo, CARTELLA, branch)
    file_da_pubblicare, _ = costruisci_pubblicazione(sponsor, esistenti)
    return pubblica_su_github(token, repo, file_da_pubblicare, "Aggiornamento sponsor", branch)
