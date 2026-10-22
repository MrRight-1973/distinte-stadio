"""Cosa mostra la pagina spettatori tra una partita e l'altra: le prossime partite (dalle distinte preparate in
📝 Crea distinta) e gli ultimi risultati (dall'archivio). Solo dati pubblici: squadre, data, ora, campo e
risultato, mai i nomi dei ragazzi."""
import re
from datetime import date

import archivio_cloud
import loghi
from classifica import classifiche, nome_fonte, nostra_riga
from distinta_ufficiale import distinte_stagione
from stagioni import impostazioni_stagioni, stagione_di_oggi
from ui_archivio import data_ordinabile

PROSSIME, RISULTATI = 3, 5


def _parole(nome):
    return {p for p in re.findall(r"[^\W\d_]{3,}", str(nome or "").upper())} - {"ASD", "SSD", "CALCIO"}


def _giocate():
    """{data iso: [parole delle squadre]} delle partite già in archivio con il risultato."""
    giocate = {}
    for p in archivio_cloud.elenco_partite():
        a, m, g = data_ordinabile(p.get("data"))
        if a and p.get("gol_casa") is not None:
            giocate.setdefault(f"{a:04d}-{m:02d}-{g:02d}", []).append(_parole(p.get("casa")) | _parole(p.get("ospite")))
    return giocate


def da_giocare(distinte, oggi):
    """Le distinte da oggi in poi, tranne le partite già chiuse in Cronaca e archiviate (es. quella appena
    finita, che ha la data di oggi): stessa data e lo stesso avversario."""
    try:
        giocate = _giocate()
    except Exception:  # noqa: BLE001 - senza archivio si mostrano tutte
        giocate = {}
    distinte = [d for d in distinte if d.get("data", "") >= oggi]
    per_data = {}
    for d in distinte:
        per_data[d.get("data")] = per_data.get(d.get("data"), 0) + 1

    def giocata(d):
        squadre = giocate.get(d.get("data"), [])
        # nomi scritti diversi (calendario LND e foglio dell'arbitro): se quel giorno c'è una sola partita, è lei
        return bool(squadre) and (per_data[d.get("data")] == 1
                                  or any(_parole(d.get("avversario")) & s for s in squadre))
    return [d for d in distinte if not giocata(d)]


def prossime_partite(oggi=None):
    oggi = (oggi or date.today()).isoformat()
    stagione = impostazioni_stagioni().get("corrente") or stagione_di_oggi()
    distinte = [d for d in da_giocare(distinte_stagione(stagione).values(), oggi) if d.get("avversario")]
    return [{k: d.get(k, "") for k in ("data", "ora", "casa", "ospite", "competizione", "giornata", "campo", "localita")}
            for d in sorted(distinte, key=lambda d: (d.get("data", ""), d.get("ora", "")))[:PROSSIME]]


def ultimi_risultati():
    partite = [p for p in archivio_cloud.elenco_partite() if p.get("gol_casa") is not None]
    partite.sort(key=lambda p: data_ordinabile(p.get("data")), reverse=True)
    return [{"data": str(p.get("data") or "").split(" ore")[0], "casa": p.get("casa") or "",
             "ospite": p.get("ospite") or "", "gol_casa": p["gol_casa"], "gol_ospite": p["gol_ospite"],
             "competizione": p.get("campionato") or ""} for p in partite[:RISULTATI]]


def classifica_attesa(oggi=None, nome_societa=""):
    """La classifica della squadra che gioca la prossima partita (o della prima che ne ha una): solo posizione,
    squadra, punti e partite giocate."""
    stagione = impostazioni_stagioni().get("corrente") or stagione_di_oggi()
    tutte = {g: c for g, c in classifiche().items() if c.get("stagione") == stagione and c.get("righe")}
    if not tutte:
        return {}
    oggi = (oggi or date.today()).isoformat()
    prossime = sorted(da_giocare(distinte_stagione(stagione).values(), oggi),
                      key=lambda d: d.get("data", ""))
    gruppo = next((d["gruppo"] for d in prossime if d.get("gruppo") in tutte), next(iter(tutte)))
    c = tutte[gruppo]
    try:
        stemmi = loghi.tutti()
    except Exception:  # noqa: BLE001 - senza stemmi la classifica si mostra lo stesso
        stemmi = {}
    return {"gruppo": gruppo, "aggiornata": c.get("aggiornata", ""), "nostra": nostra_riga(c["righe"], nome_societa),
            "fonte": nome_fonte(c.get("fonte")),
            "righe": [{**{k: r.get(k) for k in ("pos", "squadra", "pt", "g")}, "logo": loghi.di(r["squadra"], stemmi)}
                      for r in c["righe"]]}


def dati_attesa(oggi=None, nome_societa=""):
    """{"prossime": [...], "risultati": [...], "classifica": {...}, "classifica_url": ...}; quello che non si
    riesce a leggere resta vuoto. classifica_url è la copia pubblica che l'Action "Classifiche" aggiorna mattina
    e sera: la pagina spettatori la preferisce a quella scritta qui, che resta ferma a quando si pubblica."""
    dati = {"classifica_url": archivio_cloud.url_pubblico("classifica.json")}
    for chiave, funzione in (("prossime", lambda: prossime_partite(oggi)), ("risultati", ultimi_risultati),
                             ("classifica", lambda: classifica_attesa(oggi, nome_societa))):
        try:
            dati[chiave] = funzione()
        except Exception:
            dati[chiave] = {} if chiave == "classifica" else []
    return dati
