"""Classifica del girone, letta dalla pagina di Tuttocampo oppure dal testo copiato da quella pagina o da quella
della LND (gare.lnd.it, che si costruisce nel browser e quindi si può solo copiare e incollare).

Tuttocampo non ha un servizio ufficiale per questi dati: la pagina si legge come la leggerebbe un browser,
quindi un giorno può cambiare o bloccare le letture automatiche. Per questo c'è sempre la riserva:
si apre la pagina, si copia tutto (Ctrl+A, Ctrl+C) e si incolla nell'app. Il lettore è lo stesso.

Salvata in impostazioni/classifiche.json (una per squadra della società); sono dati pubblici
(squadre e punti) e possono andare sulla pagina spettatori.
"""
import json
import os
import re
import time
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests

import archivio_cloud as cloud

from cronaca_manager import _cartella_dati, _carica_online, _leggi_file

PERCORSO_ONLINE = "impostazioni/classifiche.json"
CAMPI = ("pt", "g", "v", "n", "p", "gf", "gs")
# Ordini delle colonne dopo il nome della squadra, provati uno dopo l'altro
ORDINI = (("pt", "g", "v", "n", "p", "gf", "gs"),
          ("g", "v", "n", "p", "gf", "gs", "dr", "pt"),
          ("g", "v", "n", "p", "gf", "gs", "pt"),
          ("pt", "g", "v", "p", "n", "gf", "gs"),
          ("g", "v", "n", "p", "dr", "pt"))  # gare.lnd.it: PG V N S DR P, senza gol fatti e subiti
_NUMERO = re.compile(r"^[+-]?\d+$")


class ClassificaErrore(Exception):
    pass


# --- Lettura ---------------------------------------------------------------------

class _Testo(HTMLParser):
    """I pezzi di testo di una pagina HTML, in ordine, senza script e stili."""
    def __init__(self):
        super().__init__()
        self.pezzi, self._salta = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "head"):
            self._salta += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "head") and self._salta:
            self._salta -= 1

    def handle_data(self, data):
        if not self._salta and data.strip():
            self.pezzi.append(data.strip())


def _parole(testo):
    if "<" in testo and ">" in testo and re.search(r"<(html|table|div|tr|td|span)\b", testo, re.I):
        p = _Testo()
        p.feed(testo)
        pezzi = p.pezzi
    else:
        pezzi = testo.split("\n")
    return [w for pezzo in pezzi for w in re.split(r"[\s\t]+", pezzo.replace("\xa0", " ")) if w]


def _numero(parola):
    parola = parola.rstrip("°º.")
    return int(parola) if _NUMERO.match(parola) else None


def _righe_grezze(parole):
    """[(posizione, squadra, [numeri])] cercando 1, 2, 3... seguiti dal nome e da almeno 7 numeri."""
    righe, attesa, i = [], 1, 0
    while i < len(parole):
        if _numero(parole[i]) == attesa or (righe and _numero(parole[i]) is not None
                                            and righe[-1][0] < _numero(parole[i]) <= righe[-1][0] + 3):
            pos, j, nome = _numero(parole[i]), i + 1, []
            # il nome: parole fino ai numeri (un anno come "1913" fa parte del nome)
            while j < len(parole) and (_numero(parole[j]) is None or (_numero(parole[j]) > 200 and nome)):
                nome.append(parole[j])
                j += 1
            numeri = []
            while j < len(parole) and _numero(parole[j]) is not None:
                if _numero(parole[j]) == pos + 1 and j + 1 < len(parole) and _numero(parole[j + 1]) is None:
                    break  # comincia la riga della squadra dopo
                numeri.append(_numero(parole[j]))
                j += 1
            if nome and len(numeri) >= 6 and len(nome) <= 8:
                righe.append((pos, " ".join(nome).strip(" .-"), numeri))
                attesa, i = pos + 1, j
                continue
        i += 1
    return righe


def _valida(r):
    return r["v"] + r["n"] + r["p"] == r["g"] and 0 <= r["g"] <= 60 and r["pt"] <= 3 * r["v"] + r["n"] \
        and r["pt"] >= 3 * r["v"] + r["n"] - 15


def leggi(testo):
    """[{pos, squadra, pt, g, v, n, p, gf, gs, dr}] (gf e gs None se la pagina non li ha) dalla pagina (HTML) o dal testo copiato. Errore se non trova
    una classifica credibile (partite = vinte + pareggiate + perse per quasi tutte le squadre)."""
    grezze = _righe_grezze(_parole(testo or ""))
    if len(grezze) < 4:
        raise ClassificaErrore("Non trovo la classifica in questa pagina.")
    migliore, valide = None, -1
    for ordine in ORDINI:
        righe = [{"pos": pos, "squadra": nome, **dict(zip(ordine, numeri))} for pos, nome, numeri in grezze]
        quante = sum(1 for r, (_, _, numeri) in zip(righe, grezze) if len(numeri) >= len(ordine) and _valida(r))
        if quante > valide:
            migliore, valide = righe, quante
    if valide < len(grezze) * 0.8:
        raise ClassificaErrore("Ho trovato una tabella, ma i numeri non sembrano una classifica.")
    return [{"pos": r["pos"], "squadra": r["squadra"], **{k: r.get(k) for k in CAMPI},
             "dr": r["dr"] if "dr" in r else r["gf"] - r["gs"]} for r in migliore]


def scarica(url):
    """Il testo della pagina di Tuttocampo. Errore con un messaggio chiaro se non si riesce."""
    indirizzo = urlparse(url.strip())
    if indirizzo.scheme not in ("http", "https") or not (indirizzo.hostname or "").endswith("tuttocampo.it"):
        if (indirizzo.hostname or "").endswith("lnd.it"):
            raise ClassificaErrore("La pagina della LND si costruisce nel browser e non si legge dal link: aprila, "
                                   "copia tutto il testo e incollalo qui sotto.")
        raise ClassificaErrore("Serve il link di una pagina di tuttocampo.it.")
    try:
        r = requests.get(url.strip(), timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0 Safari/537.36", "Accept-Language": "it-IT,it;q=0.9"})
    except requests.RequestException as e:
        raise ClassificaErrore("Tuttocampo non risponde.") from e
    if r.status_code in (401, 403, 429, 503):
        raise ClassificaErrore("Tuttocampo non lascia leggere la pagina in automatico: copia e incolla il testo.")
    if r.status_code >= 400:
        raise ClassificaErrore(f"Tuttocampo risponde con un errore ({r.status_code}): controlla il link.")
    return r.text


# --- Salvataggio -------------------------------------------------------------------

def _percorso():
    return os.path.join(_cartella_dati(), "classifiche.json")


_letta = {"quando": 0.0, "dati": None}  # per non rileggerla da Supabase a ogni clic


def classifiche(fresca=False):
    """{gruppo squadra: {"fonte", "aggiornata", "stagione", "righe"}}. Si legge prima da Supabase (il file
    può averlo aggiornato la GitHub Action "Classifiche"), poi dalla copia sul disco."""
    if not fresca and _letta["dati"] is not None and time.time() - _letta["quando"] < 60:
        return json.loads(json.dumps(_letta["dati"]))
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
    _letta.update(quando=time.time(), dati=dati)
    return json.loads(json.dumps(dati))


def salva(gruppo, stagione, righe, fonte=""):
    dati = classifiche(fresca=True)
    dati[gruppo] = {"stagione": stagione, "fonte": fonte, "righe": righe,
                    "aggiornata": datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open(_percorso(), "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1)
    _carica_online(PERCORSO_ONLINE, _percorso(), "application/json")
    _letta.update(quando=time.time(), dati=dati)
    return dati[gruppo]


def link_attuale(link):
    """Il link senza la giornata (giornata=7, leg=first...): così la pagina della LND mostra sempre l'ultima,
    e la classifica non resta ferma alla giornata in cui è stato copiato il link."""
    from urllib.parse import parse_qsl, urlencode, urlunparse
    indirizzo = urlparse(str(link or "").strip())
    if not indirizzo.query:
        return str(link or "").strip()
    resto = [(k, v) for k, v in parse_qsl(indirizzo.query, keep_blank_values=True)
             if k.lower() not in ("giornata", "turno", "round", "matchday", "leg")]
    return urlunparse(indirizzo._replace(query=urlencode(resto)))


def nome_fonte(link):
    host = urlparse(str(link or "").strip()).hostname or ""
    return "LND" if host.endswith("lnd.it") else "Tuttocampo" if host.endswith("tuttocampo.it") else ""


def nostra_riga(righe, nome_societa):
    """La posizione della nostra squadra (per evidenziarla), o None."""
    parole = {p for p in re.findall(r"[A-Z]{3,}", (nome_societa or "").upper()) if p not in ("ASD", "SSD", "A.S.D")}
    for r in righe:
        nome = r["squadra"].upper()
        if parole and sum(1 for p in parole if p in nome) >= min(2, len(parole)):
            return r["pos"]
    return None
