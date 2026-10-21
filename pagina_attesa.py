"""Cosa mostra la pagina spettatori tra una partita e l'altra: le prossime partite (dalle distinte preparate in
📝 Crea distinta) e gli ultimi risultati (dall'archivio). Solo dati pubblici: squadre, data, ora, campo e
risultato, mai i nomi dei ragazzi."""
from datetime import date

import archivio_cloud
from classifica import classifiche, nostra_riga
from distinta_ufficiale import distinte_stagione
from stagioni import impostazioni_stagioni, stagione_di_oggi
from ui_archivio import data_ordinabile

PROSSIME, RISULTATI = 3, 5


def prossime_partite(oggi=None):
    oggi = (oggi or date.today()).isoformat()
    stagione = impostazioni_stagioni().get("corrente") or stagione_di_oggi()
    distinte = [d for d in distinte_stagione(stagione).values() if d.get("data", "") >= oggi and d.get("avversario")]
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
    prossime = sorted((d for d in distinte_stagione(stagione).values() if d.get("data", "") >= oggi),
                      key=lambda d: d.get("data", ""))
    gruppo = next((d["gruppo"] for d in prossime if d.get("gruppo") in tutte), next(iter(tutte)))
    c = tutte[gruppo]
    return {"gruppo": gruppo, "aggiornata": c.get("aggiornata", ""), "nostra": nostra_riga(c["righe"], nome_societa),
            "righe": [{k: r.get(k) for k in ("pos", "squadra", "pt", "g")} for r in c["righe"]]}


def dati_attesa(oggi=None, nome_societa=""):
    """{"prossime": [...], "risultati": [...], "classifica": {...}}; quello che non si riesce a leggere resta
    vuoto."""
    dati = {}
    for chiave, funzione in (("prossime", lambda: prossime_partite(oggi)), ("risultati", ultimi_risultati),
                             ("classifica", lambda: classifica_attesa(oggi, nome_societa))):
        try:
            dati[chiave] = funzione()
        except Exception:
            dati[chiave] = {} if chiave == "classifica" else []
    return dati
