"""Diffide e squalifiche dai cartellini segnati in Cronaca, per avvisare in 📝 Crea distinta.

Le ammonizioni si contano per competizione (il campionato e la coppa a parte) nell'anno sportivo. La squalifica
per somma di ammonizioni scatta alle soglie del Comunicato LND (alla 5ª, poi alla 9ª, 12ª, 14ª e da lì ogni 2);
un'espulsione dà almeno una giornata: quante, lo decide il Giudice Sportivo. La squalifica si sconta nella partita
successiva della stessa competizione. È un promemoria: fa fede il Comunicato Ufficiale.
"""
from statistiche import (chiave_giocatore, chiave_squadra, data_ordinabile, giocata, lato_della_squadra,
                         statistiche_partita)
from stagioni import gruppo_di, stagione_partita

SOGLIE = (5, 9, 12, 14)  # dopo l'ultima, una squalifica ogni 2 ammonizioni
DIFFIDATO, SQUALIFICATO = "diffidato", "squalificato"


def soglia(n):
    """True se alla n-esima ammonizione scatta la squalifica."""
    return n in SOGLIE or (n > SOGLIE[-1] and (n - SOGLIE[-1]) % 2 == 0)


def tipo_competizione(nome):
    return "coppa" if "COPPA" in str(nome or "").upper() else "campionato"


def _data_iso(iso):
    try:
        a, m, g = (int(x) for x in str(iso or "")[:10].split("-"))
        return (a, m, g)
    except ValueError:
        return (9999, 0, 0)


def partite_della_competizione(partite, nomi_squadra, stagione, gruppo, competizione, prima_del):
    """[(data, {chiave giocatore: (nome, ammonizioni, espulsioni)})] delle partite giocate dalla nostra squadra
    nella stessa competizione (stesso anno, gruppo e tipo: campionato o coppa) prima della data (yyyy-mm-dd)."""
    chiavi = {chiave_squadra(n) for n in nomi_squadra if n}
    limite, tipo = _data_iso(prima_del), tipo_competizione(competizione)
    elenco = []
    for c in partite:
        p = c.get("partita") or {}
        if (not giocata(c) or stagione_partita(p) != stagione or gruppo_di(p.get("campionato"), stagione) != gruppo
                or tipo_competizione(p.get("campionato")) != tipo or data_ordinabile(c) >= limite):
            continue
        lato = next((lato for lato in (lato_della_squadra(c, k) for k in chiavi) if lato), None)
        if lato:
            cartellini = {k: (g["nome"], g["ammonizioni"], g["espulsioni"])
                          for k, g in statistiche_partita(c, lato).items()}
            elenco.append((data_ordinabile(c), cartellini))
    return sorted(elenco, key=lambda x: x[0])


def situazione(giocate):
    """{chiave giocatore: (stato, motivo)} per la prossima partita, dalle partite giocate in ordine.
    Squalificato se nell'ultima partita ha raggiunto una soglia di ammonizioni o è stato espulso (le squalifiche
    delle partite prima le ha già scontate); diffidato se alla prossima ammonizione scatta la squalifica."""
    totali, stato = {}, {}
    for i, (_, cartellini) in enumerate(giocate):
        ultima = i == len(giocate) - 1
        for k, (nome, amm, esp) in cartellini.items():
            prima = totali.get(k, 0)
            totali[k] = prima + amm
            if not ultima:
                continue
            if esp:
                stato[k] = (SQUALIFICATO, "espulso nell'ultima partita: quante giornate lo dice il Comunicato")
            elif any(soglia(n) for n in range(prima + 1, totali[k] + 1)):
                stato[k] = (SQUALIFICATO, f"{totali[k]}ª ammonizione nell'ultima partita")
    for k, n in totali.items():
        if k not in stato and soglia(n + 1):
            stato[k] = (DIFFIDATO, f"{n} ammonizioni: alla prossima è squalificato")
    return stato


def per_persona(stato, persone):
    """{id anagrafica: (stato, motivo)}: i giocatori dell'anagrafica riconosciuti dal nome."""
    return {i: stato[chiave_giocatore(f"{r.get('cognome', '')} {r.get('nome', '')}")]
            for i, r in persone.items()
            if chiave_giocatore(f"{r.get('cognome', '')} {r.get('nome', '')}") in stato}
