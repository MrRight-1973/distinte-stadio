"""Cosa mostra la pagina spettatori tra una partita e l'altra: le prossime partite (dalle distinte preparate in
📝 Crea distinta) e gli ultimi risultati (dall'archivio). Solo dati pubblici: squadre, data, ora, campo e
risultato, mai i nomi dei ragazzi."""
from datetime import date

import archivio_cloud
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


def dati_attesa(oggi=None):
    """{"prossime": [...], "risultati": [...]}; quello che non si riesce a leggere resta vuoto."""
    dati = {}
    for chiave, funzione in (("prossime", lambda: prossime_partite(oggi)), ("risultati", ultimi_risultati)):
        try:
            dati[chiave] = funzione()
        except Exception:
            dati[chiave] = []
    return dati
