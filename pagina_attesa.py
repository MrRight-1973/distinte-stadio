"""Cosa mostra la pagina spettatori tra una partita e l'altra: le prossime partite (dalle distinte preparate in
📝 Crea distinta) e gli ultimi risultati (dall'archivio). Solo dati pubblici: squadre, data, ora, campo e
risultato, mai i nomi dei ragazzi."""
import re
from datetime import date

import archivio_cloud
import loghi
from classifica import classifiche, nome_fonte, nostra_riga
from distinta_ufficiale import distinte_stagione
from stagioni import gruppi_correnti, gruppo_di, impostazioni_stagioni, stagione_di_oggi, stagione_partita
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


def _prossima(d):
    return {k: d.get(k, "") for k in ("data", "ora", "casa", "ospite", "competizione", "giornata", "campo", "localita")}


def _risultato(p):
    return {"data": str(p.get("data") or "").split(" ore")[0], "casa": p.get("casa") or "",
            "ospite": p.get("ospite") or "", "gol_casa": p["gol_casa"], "gol_ospite": p["gol_ospite"],
            "competizione": p.get("campionato") or ""}


def _da_giocare_ordinate(stagione, oggi):
    distinte = [d for d in da_giocare(distinte_stagione(stagione).values(), oggi) if d.get("avversario")]
    return sorted(distinte, key=lambda d: (d.get("data", ""), d.get("ora", "")))


def _archiviate():
    partite = [p for p in archivio_cloud.elenco_partite() if p.get("gol_casa") is not None]
    return sorted(partite, key=lambda p: data_ordinabile(p.get("data")), reverse=True)


def prossime_partite(oggi=None):
    oggi = (oggi or date.today()).isoformat()
    stagione = impostazioni_stagioni().get("corrente") or stagione_di_oggi()
    return [_prossima(d) for d in _da_giocare_ordinate(stagione, oggi)[:PROSSIME]]


def ultimi_risultati():
    return [_risultato(p) for p in _archiviate()[:RISULTATI]]


def _classifica_pubblica(gruppo, c, stemmi, nome_societa):
    """Solo posizione, squadra, punti, partite giocate e stemma."""
    return {"gruppo": gruppo, "aggiornata": c.get("aggiornata", ""), "nostra": nostra_riga(c["righe"], nome_societa),
            "fonte": nome_fonte(c.get("fonte")),
            "righe": [{**{k: r.get(k) for k in ("pos", "squadra", "pt", "g")}, "logo": loghi.di(r["squadra"], stemmi)}
                      for r in c["righe"]]}


def _classifiche_stagione(stagione):
    return {g: c for g, c in classifiche().items() if c.get("stagione") == stagione and c.get("righe")}


def _stemmi():
    try:
        return loghi.tutti()
    except Exception:  # noqa: BLE001 - senza stemmi la classifica si mostra lo stesso
        return {}


def classifica_attesa(oggi=None, nome_societa=""):
    """La classifica della squadra che gioca la prossima partita (o della prima che ne ha una)."""
    stagione = impostazioni_stagioni().get("corrente") or stagione_di_oggi()
    tutte = _classifiche_stagione(stagione)
    if not tutte:
        return {}
    oggi = (oggi or date.today()).isoformat()
    prossime = sorted(da_giocare(distinte_stagione(stagione).values(), oggi),
                      key=lambda d: d.get("data", ""))
    gruppo = next((d["gruppo"] for d in prossime if d.get("gruppo") in tutte), next(iter(tutte)))
    return _classifica_pubblica(gruppo, tutte[gruppo], _stemmi(), nome_societa)


def classifiche_attesa(nome_societa=""):
    """{gruppo: classifica pubblica} di tutte le squadre della stagione in corso che hanno una classifica."""
    stagione = impostazioni_stagioni().get("corrente") or stagione_di_oggi()
    stemmi = _stemmi()
    return {g: _classifica_pubblica(g, c, stemmi, nome_societa) for g, c in _classifiche_stagione(stagione).items()}


def squadre_attesa(oggi=None, nome_societa=""):
    """Una sezione per squadra della società: [{"gruppo", "prossime", "risultati", "classifica"}], prima le
    squadre che giocano prima. Solo le squadre che hanno qualcosa da mostrare."""
    oggi = (oggi or date.today()).isoformat()
    stagione, gruppi = gruppi_correnti()
    stagione = stagione or stagione_di_oggi()
    ordine = [g["gruppo"] for g in gruppi]
    sezioni = {g: {"gruppo": g, "prossime": [], "risultati": [], "classifica": {}} for g in ordine}

    def sezione(gruppo):
        if gruppo not in sezioni:
            ordine.append(gruppo)
            sezioni[gruppo] = {"gruppo": gruppo, "prossime": [], "risultati": [], "classifica": {}}
        return sezioni[gruppo]

    for d in _da_giocare_ordinate(stagione, oggi):
        if d.get("gruppo") and len(sezione(d["gruppo"])["prossime"]) < PROSSIME:
            sezioni[d["gruppo"]]["prossime"].append(_prossima(d))
    try:
        archiviate = _archiviate()
    except Exception:  # noqa: BLE001 - senza archivio niente risultati
        archiviate = []
    for p in archiviate:
        if stagione_partita(p) != stagione:
            continue
        gruppo = gruppo_di(p.get("campionato"), stagione)
        if gruppo and len(sezione(gruppo)["risultati"]) < RISULTATI:
            sezioni[gruppo]["risultati"].append(_risultato(p))
    try:
        for g, c in classifiche_attesa(nome_societa).items():
            sezione(g)["classifica"] = c
    except Exception:  # noqa: BLE001 - senza classifiche le sezioni restano
        pass
    piene = [sezioni[g] for g in ordine if sezioni[g]["prossime"] or sezioni[g]["risultati"] or sezioni[g]["classifica"]]
    # prima chi gioca prima; le squadre senza partite in programma restano nell'ordine dei gruppi
    return sorted(piene, key=lambda s: (s["prossime"][0]["data"] + s["prossime"][0]["ora"]) if s["prossime"] else "~")


def dati_attesa(oggi=None, nome_societa=""):
    """{"prossime": [...], "risultati": [...], "classifica": {...}, "squadre": [...], "classifica_url": ...};
    "squadre" divide le stesse cose per squadra (la pagina mostra una scheda per squadra). Quello che non si
    riesce a leggere resta vuoto. classifica_url è la copia pubblica che l'Action "Classifiche" aggiorna mattina
    e sera: la pagina spettatori la preferisce a quella scritta qui, che resta ferma a quando si pubblica."""
    dati = {"classifica_url": archivio_cloud.url_pubblico("classifica.json")}
    for chiave, funzione in (("prossime", lambda: prossime_partite(oggi)), ("risultati", ultimi_risultati),
                             ("classifica", lambda: classifica_attesa(oggi, nome_societa)),
                             ("squadre", lambda: squadre_attesa(oggi, nome_societa))):
        try:
            dati[chiave] = funzione()
        except Exception:
            dati[chiave] = {} if chiave == "classifica" else []
    return dati
