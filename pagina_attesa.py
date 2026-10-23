"""Cosa mostra la pagina spettatori tra una partita e l'altra: le prossime partite (dalle distinte preparate in
📝 Crea distinta) e gli ultimi risultati (dall'archivio). Solo dati pubblici: squadre, data, ora, campo e
risultato, mai i nomi dei ragazzi."""
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import archivio_cloud
import girone
import loghi
from classifica import classifiche, nome_fonte, nostra_riga
from distinta_ufficiale import distinte_stagione
from stagioni import gruppi_correnti, gruppo_di, impostazioni_stagioni, stagione_di_oggi, stagione_partita
from ui_archivio import data_ordinabile

PROSSIME, RISULTATI = 3, 5
DURATA = timedelta(hours=2)  # una partita resta "prossima" fino a due ore dopo il calcio d'inizio
FUSO = ZoneInfo("Europe/Rome")


# dai più grandi ai più piccoli; "Under 17" e simili si ordinano per età
_CATEGORIE = [("ECCELLENZA", 0), ("PROMOZIONE", 0), ("PRIMA", 0), ("SECONDA", 0), ("TERZA", 0), ("SENIOR", 0),
              ("AMATORI", 0), ("JUNIORES", 19), ("ALLIEVI", 17), ("GIOVANISSIMI", 15), ("ESORDIENTI", 13),
              ("PULCINI", 11), ("PRIMI CALCI", 9), ("PICCOLI AMICI", 7)]


def eta(gruppo):
    """Per ordinare le squadre: 0 la prima squadra, poi l'età della categoria al contrario (Under 19 prima di
    Under 15). Le squadre non riconosciute vanno in fondo."""
    nome = str(gruppo or "").upper()
    under = re.search(r"\b(?:UNDER|U)\s*(\d{1,2})\b", nome)
    if under:
        return (1, -int(under[1]), nome)
    for parola, anni in _CATEGORIE:
        if parola in nome:
            return (0, 0, nome) if anni == 0 else (1, -anni, nome)
    return (2, 0, nome)


def ancora_da_giocare(p, adesso):
    """Con data e ora: fino a due ore dopo l'inizio. Senza ora: per tutto il giorno."""
    try:
        giorno = datetime.strptime(p.get("data", ""), "%Y-%m-%d")
    except ValueError:
        return True
    try:
        h, m = (int(x) for x in str(p.get("ora") or "").replace(".", ":").split(":")[:2])
        fine = giorno.replace(hour=h, minute=m) + DURATA
    except ValueError:
        fine = giorno + timedelta(days=1)
    return fine > adesso


def _adesso(oggi):
    """L'ora italiana senza fuso (come le date delle partite); con un giorno dato (prove): la sua mezzanotte."""
    if oggi:
        return datetime(oggi.year, oggi.month, oggi.day)
    return datetime.now(FUSO).replace(tzinfo=None)


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


_SIGLE = {"ASD", "SSD", "SSDARL", "ARL", "SRL", "AC", "AS", "US", "USD", "FC", "SC", "GS", "ACD", "APD", "ASDC",
          "CF", "CS", "PD", "VE", "VI", "TV", "VR", "RO", "BL", "II", "III"}


def leggibile(nome):
    """"A.S.D. AZZURRA DUE CARRARE" -> "A.S.D. Azzurra Due Carrare", come scrive la LND; i nomi già scritti
    con maiuscole e minuscole restano come sono."""
    nome = str(nome or "")
    if not nome.isupper():
        return nome
    parole = []
    for w in nome.split():
        if w.replace(".", "") in _SIGLE or re.fullmatch(r"(?:[A-Z]\.)+[A-Z]?\.?", w):
            parole.append(w)
        else:
            parole.append(re.sub(r"[^\W\d_]+", lambda m: m[0].capitalize(), w))
    return " ".join(parole)


def _gg_mm_aaaa(iso):
    """"2026-10-19" -> "19/10/2026", come le date dell'archivio."""
    parti = str(iso or "").split("-")
    return f"{parti[2]}/{parti[1]}/{parti[0]}" if len(parti) == 3 else ""


def _aggiungi_dal_girone(sezione, giornate, oggi, nome_societa):
    """Completa la sezione di una squadra con il calendario LND letto dall'Action "Classifiche": le partite in
    programma che non hanno ancora una distinta e i risultati che non sono in archivio (stessa data = stessa
    partita)."""
    squadre = girone.squadre_del_girone(giornate)
    pos = nostra_riga([{"pos": i, "squadra": n} for i, n in enumerate(squadre)], nome_societa)
    if pos is None:
        return
    noi = squadre[pos]
    prossime = {p["data"]: p for p in sezione["prossime"]}
    risultati = {data_ordinabile(r["data"]): r for r in sezione["risultati"]}
    for k, p in girone.partite_di(giornate, noi):
        if p.get("gol_casa") is None:
            gia = prossime.get(p.get("data"))
            if gia:  # la stessa partita della distinta: i nomi come li scrive la LND, e i dati che mancano
                gia.update(casa=p["casa"], ospite=p["ospite"])
                gia["giornata"] = gia.get("giornata") or girone.etichetta(k)
                gia["campo"] = gia.get("campo") or p.get("campo", "")
            elif p.get("data", "") >= oggi:
                sezione["prossime"].append({"data": p.get("data", ""), "ora": p.get("ora", ""), "casa": p["casa"],
                                            "ospite": p["ospite"], "competizione": "", "giornata": girone.etichetta(k),
                                            "campo": p.get("campo", ""), "localita": ""})
        else:
            gia = risultati.get(data_ordinabile(_gg_mm_aaaa(p.get("data"))))
            if gia:
                gia.update(casa=p["casa"], ospite=p["ospite"])
            else:
                sezione["risultati"].append({"data": _gg_mm_aaaa(p.get("data")), "casa": p["casa"],
                                             "ospite": p["ospite"], "gol_casa": p["gol_casa"],
                                             "gol_ospite": p["gol_ospite"], "competizione": ""})
    sezione["prossime"] = sorted(sezione["prossime"], key=lambda x: (x["data"], x["ora"]))[:PROSSIME]
    sezione["risultati"] = sorted(sezione["risultati"], key=lambda x: data_ordinabile(x["data"]),
                                  reverse=True)[:RISULTATI]


def squadre_attesa(oggi=None, nome_societa=""):
    """Una sezione per squadra della società: [{"gruppo", "prossime", "risultati", "classifica"}], dai più grandi
    ai più piccoli. Prossime partite dalle distinte preparate e dal calendario LND (solo quelle non ancora finite,
    guardando data e ora), risultati dall'archivio e dalla LND. Solo le squadre che hanno qualcosa da mostrare."""
    adesso = _adesso(oggi)
    oggi = adesso.date().isoformat()
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
        dal_girone = girone.tutti()
    except Exception:  # noqa: BLE001 - senza calendario LND restano distinte e archivio
        dal_girone = {}
    for g, dati in dal_girone.items():
        if dati.get("stagione") == stagione and dati.get("giornate"):
            _aggiungi_dal_girone(sezione(g), dati["giornate"], oggi, nome_societa)
    try:
        for g, c in classifiche_attesa(nome_societa).items():
            sezione(g)["classifica"] = c
    except Exception:  # noqa: BLE001 - senza classifiche le sezioni restano
        pass
    for sez in sezioni.values():  # quella di stamattina, già finita, non è più "prossima"
        sez["prossime"] = [p for p in sez["prossime"] if ancora_da_giocare(p, adesso)]
    for sez in sezioni.values():  # le partite senza LND (coppe, amichevoli): niente nomi tutti maiuscoli
        for p in sez["prossime"] + sez["risultati"]:
            for k in ("casa", "ospite", "campo", "localita"):
                if k in p:
                    p[k] = leggibile(p[k])
    piene = [sezioni[g] for g in ordine if sezioni[g]["prossime"] or sezioni[g]["risultati"] or sezioni[g]["classifica"]]
    return sorted(piene, key=lambda s: eta(s["gruppo"]))


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
