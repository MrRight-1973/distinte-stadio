"""⚖️ Squalifiche dal Comunicato: le giornate (o la data) decise dal Giudice Sportivo, segnate a mano.

Dai cartellini l'app sa solo che un espulso salta almeno la partita dopo; quando il Comunicato Ufficiale dà più
giornate (o una squalifica a tempo) si segna qui. Le giornate si contano sulle partite giocate in 🎙️ Cronaca
dopo la data del Comunicato, nella stessa squadra e competizione (campionato o coppa); la squalifica a tempo vale
per tutte le partite fino alla data. Salvato in impostazioni/squalifiche.json (disco dell'app e Supabase privato).
"""
import json
import os
import uuid

from cronaca_manager import _cartella_dati, _carica_online, _leggi_file
from disciplina import SQUALIFICATO, _data_iso

PERCORSO_ONLINE = "impostazioni/squalifiche.json"


def _percorso():
    return os.path.join(_cartella_dati(), "squalifiche.json")


def elenco():
    try:
        dati = json.loads(_leggi_file(_percorso(), PERCORSO_ONLINE)) or []
    except (OSError, ValueError):
        dati = []
    return [s for s in dati if isinstance(s, dict) and s.get("id") and s.get("persona")]


def _salva(dati):
    with open(_percorso(), "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1)
    _carica_online(PERCORSO_ONLINE, _percorso(), "application/json")


def aggiungi(persona, stagione, gruppo, tipo, data_cu, giornate=0, fino_al="", autore=""):
    s = {"id": uuid.uuid4().hex[:10], "persona": persona, "stagione": stagione, "gruppo": gruppo, "tipo": tipo,
         "data_cu": data_cu, "giornate": int(giornate or 0), "fino_al": fino_al or "", "autore": autore}
    _salva(elenco() + [s])
    return s


def elimina(id_squalifica):
    _salva([s for s in elenco() if s["id"] != id_squalifica])


def _gg_mm(iso):
    a, m, g = _data_iso(iso)
    return f"{g:02d}/{m:02d}/{a}"


def restano(s, giocate, giorno):
    """Giornate ancora da scontare alla partita del giorno (yyyy-mm-dd), o per la squalifica a tempo 1 se il
    giorno è entro la data e 0 se è passata. giocate: le date delle partite giocate prima, nella stessa
    squadra e competizione (da partite_della_competizione)."""
    if s.get("fino_al"):
        return 1 if _data_iso(giorno) <= _data_iso(s["fino_al"]) else 0
    cu = _data_iso(s.get("data_cu"))
    # vale dal giorno dopo il Comunicato: le partite di quel giorno o prima non contano
    scontate = sum(1 for d in giocate if d > cu)
    return max(int(s.get("giornate") or 0) - scontate, 0)


def stato(s, giocate, giorno):
    """(SQUALIFICATO, motivo) se alla partita del giorno la squalifica non è ancora scontata, altrimenti None."""
    n = restano(s, giocate, giorno)
    if not n:
        return None
    if s.get("fino_al"):
        return SQUALIFICATO, f"squalificato fino al {_gg_mm(s['fino_al'])} (Comunicato del {_gg_mm(s['data_cu'])})"
    return SQUALIFICATO, (f"squalifica di {s['giornate']} giornate dal Comunicato del {_gg_mm(s['data_cu'])}: "
                          f"{'resta questa' if n == 1 else f'restano {n}'}")


def per_partita(squalifiche, stagione, gruppo, tipo, giocate, giorno):
    """{id anagrafica: (SQUALIFICATO, motivo)} per la partita del giorno: le squalifiche a giornate della
    stessa squadra e competizione, e quelle a tempo di qualsiasi squadra."""
    date_giocate = [d for d, _ in giocate]
    esito = {}
    for s in squalifiche:
        if s.get("stagione") != stagione or _data_iso(s.get("data_cu")) >= _data_iso(giorno):
            continue
        if not s.get("fino_al") and (s.get("gruppo") != gruppo or s.get("tipo") != tipo):
            continue
        st = stato(s, date_giocate, giorno)
        if st:
            esito[s["persona"]] = st
    return esito

