"""Controllo delle liste dopo la scansione (o le correzioni a mano).

Segnala solo ciò che conviene ricontrollare sul foglio prima di pubblicare:
non corregge niente da solo.
"""
import re
import statistics
from datetime import datetime

MINIMO_GIOCATORI = 11      # sotto questo numero la lista è probabilmente incompleta
ETA_MINIMA, ETA_MASSIMA = 6, 60
SCARTO_GIOVANILI = 2       # nelle giovanili, anni di distanza dalla maggior parte della squadra


def _anno(testo, anno_corrente):
    cifre = re.sub(r"\D", "", str(testo or ""))
    if len(cifre) == 4:
        return int(cifre)
    if len(cifre) == 2:
        anno = 2000 + int(cifre)
        return anno if anno <= anno_corrente else anno - 100
    return None


def _nome_pulito(nome):
    return re.sub(r"\s*\((C|VC|\d+)\)", "", nome).strip().upper()


def controlla_lista(squadra, giocatori, allenatore="", anno_corrente=None):
    """Avvisi per una squadra. giocatori: [{"N°", "GIOCATORE", "ANNO"}] come nella griglia."""
    anno_corrente = anno_corrente or datetime.now().year
    etichetta = squadra or "Squadra senza nome"
    compilati = [g for g in giocatori if str(g.get("GIOCATORE") or "").strip()]
    avvisi = []

    if not compilati:
        return [f"{etichetta}: la lista è vuota."]
    if len(compilati) < MINIMO_GIOCATORI:
        avvisi.append(f"{etichetta}: solo {len(compilati)} giocatori, controlla che non manchi nessuno.")

    capitani = [g["N°"] for g in compilati if "(C)" in g["GIOCATORE"]]
    vice = [g["N°"] for g in compilati if "(VC)" in g["GIOCATORE"]]
    if not capitani:
        avvisi.append(f"{etichetta}: manca il capitano (C).")
    elif len(capitani) > 1:
        avvisi.append(f"{etichetta}: {len(capitani)} capitani (righe {', '.join(map(str, capitani))}).")
    if len(vice) > 1:
        avvisi.append(f"{etichetta}: {len(vice)} vice capitani (righe {', '.join(map(str, vice))}).")

    visti = {}
    for g in compilati:
        visti.setdefault(_nome_pulito(g["GIOCATORE"]), []).append(g["N°"])
    for nome, righe in visti.items():
        if len(righe) > 1:
            avvisi.append(f"{etichetta}: {nome} compare più volte (righe {', '.join(map(str, righe))}).")

    for g in compilati:
        if re.search(r"\(\d+\)", g["GIOCATORE"]):
            avvisi.append(f"{etichetta}: riga {g['N°']}, {g['GIOCATORE']}: il numero di maglia tra parentesi "
                          "non corrisponde alla riga, sistemalo.")

    anni = {}
    for g in compilati:
        anno = _anno(g.get("ANNO"), anno_corrente)
        if anno is None:
            avvisi.append(f"{etichetta}: riga {g['N°']}, {g['GIOCATORE']} è senza anno di nascita.")
        elif not ETA_MINIMA <= anno_corrente - anno <= ETA_MASSIMA:
            avvisi.append(f"{etichetta}: riga {g['N°']}, {g['GIOCATORE']} ha un anno di nascita strano ({anno}).")
        else:
            anni[g["N°"]] = anno
    if len(anni) >= 5:
        tipico = statistics.median(anni.values())
        if anno_corrente - tipico <= 18:  # giovanili: annate vicine tra loro
            for g in compilati:
                anno = anni.get(g["N°"])
                if anno and abs(anno - tipico) > SCARTO_GIOVANILI:
                    avvisi.append(f"{etichetta}: riga {g['N°']}, {g['GIOCATORE']} è del {anno}, lontano dalle "
                                  "annate del resto della squadra: controlla l'anno.")

    if not str(allenatore or "").strip():
        avvisi.append(f"{etichetta}: manca l'allenatore.")
    return avvisi
