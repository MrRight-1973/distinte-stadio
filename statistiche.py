"""Statistiche dei giocatori dalle partite con cronaca: minuti giocati, gol, assist e cartellini.

I titolari sono i primi 11 della distinta (come nel resoconto); i minuti si contano dalle
sostituzioni e dalle espulsioni segnate in cronaca, sulla durata regolamentare (2 x minuti per tempo).
"""
import re
import unicodedata

from cronaca_manager import e_autogol, e_gol, pulisci_nome, punteggio, rosa
from estrattore import _chiave_squadra
from giornata import etichetta_giornata

TITOLARI = 11


def chiave_squadra(nome):
    return _chiave_squadra(str(nome or ""))


def nome_giocatore(nome):
    """Il nome come si stampa: senza sigle di capitano e numero tra parentesi."""
    return re.sub(r"\s+", " ", re.sub(r"\(\d+\)", "", pulisci_nome(nome))).strip().upper()


def chiave_giocatore(nome):
    """Chiave per riconoscere lo stesso giocatore anche se scritto in modo un po' diverso tra una distinta
    e l'altra: senza accenti e apostrofi, lettere doppie contate una volta, parole in qualsiasi ordine.
    "MIAZZI NICOLO'", "MIAZI NICOLÒ" e "NICOLO MIAZZI" -> "MIAZI NICOLO"."""
    testo = unicodedata.normalize("NFKD", nome_giocatore(nome))
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    testo = re.sub(r"[^A-Z0-9 ]", "", testo.upper())
    testo = re.sub(r"([A-Z])\1+", r"\1", testo)
    return " ".join(sorted(testo.split()))


def minuto_numero(minuto, durata=45):
    """Minuto della nota come numero: 23' -> 23, 45+2' -> 45, 90+3' -> 90; Pre-gara -> 0,
    Intervallo -> fine del primo tempo, Fine gara -> fine partita."""
    numeri = re.findall(r"\d+", str(minuto or ""))
    if numeri:
        return min(int(numeri[0]), 2 * durata)
    testo = str(minuto or "").strip().lower()
    if testo.startswith("pre"):
        return 0
    if testo.startswith("inter"):
        return durata
    return 2 * durata


def giocata(cronaca):
    """Una partita conta se è iniziata o ha note."""
    return bool((cronaca.get("tempi") or {}).get("primo") or cronaca.get("note"))


def statistiche_partita(cronaca, lato):
    """{chiave giocatore: {nome, numero, titolare, minuti, gol, assist, ammonizioni, espulsioni}}."""
    durata = int(cronaca.get("durata_tempo") or 45)
    fine = 2 * durata
    giocatori = {}
    for i, (numero, nome) in enumerate(rosa(cronaca, lato)):
        giocatori[chiave_giocatore(nome)] = {"nome": nome_giocatore(nome), "numero": numero, "titolare": i < TITOLARI,
                                            "in_campo_da": 0 if i < TITOLARI else None, "minuti": 0,
                                            "gol": 0, "assist": 0, "ammonizioni": 0, "espulsioni": 0}

    def trova(nome):
        return giocatori.get(chiave_giocatore(nome)) if nome else None

    for n in sorted(cronaca.get("note") or [], key=lambda n: n.get("ts") or 0):
        d = n.get("dettagli") or {}
        minuto = minuto_numero(n.get("minuto"), durata)
        tipo = n.get("tipo")
        if n.get("squadra") != lato:
            continue  # l'autogol è della squadra che lo subisce: non conta come gol per nessuno
        if tipo == "Sostituzione":  # anche i cambi "volanti" delle giovanili: si può rientrare
            esce, entra = trova(d.get("esce")), trova(d.get("entra"))
            if esce:
                _esce(esce, minuto)
            if entra and entra["in_campo_da"] is None:
                entra["in_campo_da"] = minuto
        elif e_gol(n) and not e_autogol(n):
            if trova(d.get("giocatore")):
                trova(d.get("giocatore"))["gol"] += 1
            if trova(d.get("assist")):
                trova(d.get("assist"))["assist"] += 1
        elif tipo == "Ammonizione" and trova(d.get("giocatore")):
            trova(d.get("giocatore"))["ammonizioni"] += 1
        elif tipo == "Espulsione" and trova(d.get("giocatore")):
            g = trova(d.get("giocatore"))
            g["espulsioni"] += 1
            _esce(g, minuto)

    for g in giocatori.values():
        _esce(g, fine)
        g.pop("in_campo_da")
    return giocatori


def _esce(g, minuto):
    if g["in_campo_da"] is not None:
        g["minuti"] += max(0, minuto - g["in_campo_da"])
        g["in_campo_da"] = None


def data_ordinabile(cronaca):
    """(anno, mese, giorno) dalla data "dd/mm/yyyy ...", per mettere le partite in ordine."""
    numeri = re.findall(r"\d+", str((cronaca.get("partita") or {}).get("data") or ""))
    if len(numeri) >= 3:
        anno = int(numeri[2]) + (2000 if len(numeri[2]) == 2 else 0)
        return (anno, int(numeri[1]), int(numeri[0]))
    return (9999, 0, 0)


def lato_della_squadra(cronaca, chiave):
    p = cronaca.get("partita") or {}
    distinta = cronaca.get("distinta") or {}
    for lato in ("casa", "ospite"):
        nome = ((distinta.get(lato) or {}).get("squadra")) or p.get(lato)
        if chiave and chiave_squadra(nome) == chiave:
            return lato
    return None


def squadre_presenti(partite):
    """[(chiave, nome)] delle squadre nelle partite, dalla più frequente."""
    conteggio, nomi = {}, {}
    for c in partite:
        for lato in ("casa", "ospite"):
            nome = (c.get("partita") or {}).get(lato)
            if nome and rosa(c, lato):
                k = chiave_squadra(nome)
                conteggio[k] = conteggio.get(k, 0) + 1
                nomi.setdefault(k, nome)
    return [(k, nomi[k]) for k in sorted(conteggio, key=lambda k: -conteggio[k])]


def etichetta_partita(cronaca, lato):
    p = cronaca.get("partita") or {}
    avversario = p.get("ospite" if lato == "casa" else "casa") or "?"
    giornata = etichetta_giornata(p.get("giornata"))
    data = str(p.get("data") or "").split(" ore")[0]
    return " · ".join(x for x in (giornata, data, ("vs " if lato == "casa" else "@ ") + avversario) if x)


def statistiche_squadra(partite, chiave):
    """(riepilogo per giocatore, minuti per partita).

    riepilogo: [{giocatore, convocazioni, presenze, titolare, minuti, gol, assist, ammonizioni, espulsioni}]
    per_partita: [(etichetta partita, {giocatore: minuti})]
    Lo stesso giocatore scritto in modo diverso tra le partite (accenti, doppie) si conta una volta sola,
    col nome scritto più spesso.
    """
    totali, per_partita, nomi = {}, [], {}
    for c in sorted(partite, key=data_ordinabile):
        lato = lato_della_squadra(c, chiave)
        if not lato or not giocata(c):
            continue
        partita = statistiche_partita(c, lato)
        per_partita.append((etichetta_partita(c, lato), {k: g["minuti"] for k, g in partita.items()}))
        for k, g in partita.items():
            conta = nomi.setdefault(k, {})
            conta[g["nome"]] = conta.get(g["nome"], 0) + 1
            t = totali.setdefault(k, {"giocatore": "", "convocazioni": 0, "presenze": 0, "titolare": 0,
                                      "minuti": 0, "gol": 0, "assist": 0, "ammonizioni": 0, "espulsioni": 0})
            t["convocazioni"] += 1
            t["presenze"] += g["minuti"] > 0
            t["titolare"] += g["titolare"]
            for campo in ("minuti", "gol", "assist", "ammonizioni", "espulsioni"):
                t[campo] += g[campo]
    nome = {k: max(conta, key=lambda n: (conta[n], len(n))) for k, conta in nomi.items()}
    for k, t in totali.items():
        t["giocatore"] = nome[k]
    per_partita = [(etichetta, {nome[k]: minuti for k, minuti in m.items()}) for etichetta, m in per_partita]
    riepilogo = sorted(totali.values(), key=lambda t: (-t["minuti"], t["giocatore"]))
    return riepilogo, per_partita


def risultati_squadra(partite, chiave):
    """Le partite giocate dalla squadra, dalla più vecchia: [{giornata, data, avversario, in_casa, fatti, subiti}]."""
    risultati = []
    for c in sorted(partite, key=data_ordinabile):
        lato = lato_della_squadra(c, chiave)
        if not lato or not giocata(c):
            continue
        p = c.get("partita") or {}
        gol = dict(zip(("casa", "ospite"), punteggio(c)))
        altro = "ospite" if lato == "casa" else "casa"
        risultati.append({"giornata": p.get("giornata") or "", "data": str(p.get("data") or "").split(" ore")[0],
                          "avversario": p.get(altro) or "?", "in_casa": lato == "casa",
                          "fatti": gol[lato], "subiti": gol[altro]})
    return risultati
