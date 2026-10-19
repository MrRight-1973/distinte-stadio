"""Rosa dei giocatori di ogni gruppo squadra della società (una per gruppo e anno sportivo,
vale per tutte le sue competizioni: campionato, coppa...).

Serve a preparare la distinta spuntando i convocati, senza scansione, e a scrivere i nomi
sempre allo stesso modo: anche quando la lista si legge dalla foto, i nomi della nostra squadra
vengono corretti con quelli della rosa. Salvata in impostazioni/rose.json (disco e Supabase).
"""
import json
import os
import re

import pandas as pd

from cronaca_manager import _cartella_dati, _carica_online, _leggi_file, pulisci_nome
from squadra_manager import NUM_RIGHE
from statistiche import chiave_giocatore, chiave_squadra

PERCORSO_ONLINE = "impostazioni/rose.json"


def _chiave(stagione, gruppo):
    return f"{stagione}|{gruppo}"


def _percorso():
    return os.path.join(_cartella_dati(), "rose.json")


def _tutte():
    try:
        return json.loads(_leggi_file(_percorso(), PERCORSO_ONLINE)) or {}
    except (OSError, ValueError):
        return {}


def _numero(valore):
    try:
        n = int(float(str(valore).strip()))
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 99 else None


def rosa_squadra(stagione, gruppo):
    """[{giocatore, anno, numero}] nell'ordine salvato. Le rose salvate prima dei gruppi (una per
    campionato) valgono per il gruppo che contiene quel campionato, finché non si salva quella del gruppo."""
    tutte = _tutte()
    if _chiave(stagione, gruppo) in tutte:
        return list(tutte[_chiave(stagione, gruppo)] or [])
    from stagioni import impostazioni_stagioni
    competizioni = next((g["competizioni"] for g in impostazioni_stagioni()["stagioni"].get(stagione, [])
                         if g["gruppo"] == gruppo), [])
    return pulisci_rosa([x for c in competizioni for x in tutte.get(_chiave(stagione, c)) or []])


def pulisci_rosa(giocatori):
    """Righe vuote tolte, nomi in maiuscolo, doppioni (stesso giocatore scritto in modo diverso) tolti."""
    pulita, visti = [], set()
    for g in giocatori:
        nome = re.sub(r"\s+", " ", pulisci_nome(str(g.get("giocatore") or ""))).strip().upper()
        if not nome or chiave_giocatore(nome) in visti:
            continue
        visti.add(chiave_giocatore(nome))
        anno = str(g.get("anno") or "").strip()
        anno = anno[:-2] if anno.endswith(".0") else anno
        pulita.append({"giocatore": nome, "anno": anno, "numero": _numero(g.get("numero"))})
    return pulita


def salva_rosa(stagione, gruppo, giocatori):
    tutte = _tutte()
    tutte[_chiave(stagione, gruppo)] = pulisci_rosa(giocatori)
    with open(_percorso(), "w", encoding="utf-8") as f:
        json.dump(tutte, f, ensure_ascii=False, indent=1)
    _carica_online(PERCORSO_ONLINE, _percorso(), "application/json")
    return tutte[_chiave(stagione, gruppo)]


def griglia_convocati(titolari, panchina):
    """Griglia della distinta (indice N°, GIOCATORE, ANNO): prima gli 11 titolari, poi la panchina,
    ognuno col suo numero di maglia; chi non ha numero prende il primo libero. Righe vuote fino a 20."""
    usati = {g["numero"] for g in titolari + panchina if g.get("numero")}
    liberi = (n for n in range(1, 100) if n not in usati)
    righe = []
    for g in sorted(titolari, key=lambda g: g.get("numero") or 99) + sorted(panchina, key=lambda g: g.get("numero") or 99):
        numero = g.get("numero") or next(liberi)
        righe.append({"N°": numero, "GIOCATORE": g["giocatore"], "ANNO": g.get("anno") or ""})
    while len(righe) < NUM_RIGHE:
        righe.append({"N°": next(liberi), "GIOCATORE": "", "ANNO": ""})
    return pd.DataFrame(righe[:NUM_RIGHE]).set_index("N°")


def correggi_con_rosa(giocatori, rosa):
    """I nomi letti dalla foto scritti come nella rosa (accenti, doppie, ordine), e l'anno se manca.
    giocatori: [{"N°", "GIOCATORE", "ANNO"}]. Restituisce (giocatori corretti, quanti nomi cambiati)."""
    per_chiave = {chiave_giocatore(g["giocatore"]): g for g in rosa}
    corretti, cambiati = [], 0
    for g in giocatori:
        nuovo = dict(g)
        trovato = per_chiave.get(chiave_giocatore(g.get("GIOCATORE"))) if g.get("GIOCATORE") else None
        if trovato:
            capitano = re.search(r"\s*\((C|VC)\)\s*$", str(g.get("GIOCATORE") or ""))
            nome = trovato["giocatore"] + (capitano.group(0) if capitano else "")
            if nome != g.get("GIOCATORE"):
                cambiati += 1
                nuovo["GIOCATORE"] = nome
            if not str(g.get("ANNO") or "").strip() and trovato.get("anno"):
                nuovo["ANNO"] = trovato["anno"]
        corretti.append(nuovo)
    return corretti, cambiati


def lato_nostro(nome_casa, nome_ospite, nome_societa):
    """"casa" o "ospite" se una delle due squadre è la nostra società, altrimenti None."""
    nostra = chiave_squadra(nome_societa)
    if not nostra:
        return None
    for lato, nome in (("casa", nome_casa), ("ospite", nome_ospite)):
        if nome and chiave_squadra(nome) == nostra:
            return lato
    return None


def ultima_lista(partite, competizioni, nome_societa):
    """I giocatori della nostra squadra nell'ultima partita (per data) di quelle competizioni: per riempire la rosa."""
    from statistiche import data_ordinabile, lato_della_squadra
    from cronaca_manager import rosa as lista_partita

    chiave = chiave_squadra(nome_societa)
    candidate = [p for p in partite if (p.get("partita") or {}).get("campionato") in competizioni
                 and lato_della_squadra(p, chiave)]
    if not candidate:
        return []
    ultima = max(candidate, key=data_ordinabile)
    lato = lato_della_squadra(ultima, chiave)
    anni = {pulisci_nome(g.get("GIOCATORE")): g.get("ANNO", "")
            for g in (((ultima.get("distinta") or {}).get(lato) or {}).get("giocatori") or [])}
    return [{"giocatore": nome, "anno": anni.get(nome, ""), "numero": _numero(numero)}
            for numero, nome in lista_partita(ultima, lato)]
