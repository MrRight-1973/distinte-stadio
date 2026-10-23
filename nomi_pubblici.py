"""Come compaiono i giocatori sulla pagina pubblica (distinta e diretta): la scelta per gruppo squadra.

Per le giovanili si mostrano solo cognome e iniziale del nome, senza anno di nascita e senza il PDF; chi ha
detto No al nome in pubblico (consenso in 👦 Anagrafica) compare solo col numero. I nomi completi restano
nell'app, nel PDF per la segreteria e su Supabase privato: nei file pubblici va solo la versione ridotta.
Salvato in impostazioni/nomi_pubblici.json (disco dell'app e Supabase), uguale per tutti i dispositivi.
"""
import json
import os
import re

from cronaca_manager import _cartella_dati, _carica_online, _leggi_file

PERCORSO_ONLINE = "impostazioni/nomi_pubblici.json"
COMPLETI, INIZIALE, NUMERI = "completi", "iniziale", "numeri"
MODI = {COMPLETI: "👤 Nomi completi", INIZIALE: "🔤 Cognome e iniziale del nome", NUMERI: "🔢 Solo i numeri"}
_FASCIA = re.compile(r"\s*\((?:C|VC|K)\)\s*$", re.IGNORECASE)  # (C) e (VC) del capitano restano


def _percorso():
    return os.path.join(_cartella_dati(), "nomi_pubblici.json")


def scelte_salvate():
    """{gruppo: modo} scelti in ⚙️ Opzioni."""
    try:
        dati = json.loads(_leggi_file(_percorso(), PERCORSO_ONLINE)) or {}
    except (OSError, ValueError):
        dati = {}
    return {g: m for g, m in dati.items() if m in MODI}


def salva_scelta(gruppo, modo):
    dati = {**scelte_salvate(), gruppo: modo}
    with open(_percorso(), "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1)
    _carica_online(PERCORSO_ONLINE, _percorso(), "application/json")


def predefinito(gruppo):
    """Nomi completi solo per le squadre dei grandi (Prima Squadra, Seconda...); giovanili e squadre non
    riconosciute partono da cognome e iniziale."""
    from pagina_attesa import eta
    return COMPLETI if eta(gruppo)[0] == 0 else INIZIALE


def modo_gruppo(gruppo, scelte=None):
    scelte = scelte_salvate() if scelte is None else scelte
    return scelte.get(gruppo) or predefinito(gruppo)


def _parole(testo):
    return re.findall(r"[^\W\d_]+", str(testo or "").upper())


def _persona(nome, persone):
    """La persona dell'anagrafica con quel nome (cognome e nome tutti presenti), se c'è."""
    parole = set(_parole(nome))
    for p in persone:
        sue = _parole(p.get("cognome")) + _parole(p.get("nome"))
        if sue and set(sue) <= parole:
            return p
    return None


def nome_ridotto(nome, modo, persone=()):
    """"ROSSI MARIO (C)" -> "ROSSI M. (C)" con INIZIALE; "" con NUMERI o senza consenso."""
    testo = str(nome or "").strip()
    persona = _persona(testo, persone) if testo else None
    if not testo or modo == NUMERI or (persona and persona.get("consenso_nome") == "No"):
        return ""
    if modo == COMPLETI:
        return testo
    fascia = _FASCIA.search(testo)
    base = testo[:fascia.start()] if fascia else testo
    if persona and persona.get("nome"):  # dall'anagrafica si sa qual è il cognome
        base = f"{persona['cognome']} {persona['nome'][0]}."
    else:
        parole = base.split()
        if len(parole) > 1:  # sulle distinte prima il cognome: l'ultima parola è il nome
            parole[-1] = parole[-1][0] + "."
        base = " ".join(parole)
    return base + (fascia.group(0) if fascia else "")


def squadra_pubblica(dati, modo, persone=()):
    """La squadra come va sulla pagina pubblica: nomi ridotti e, se non sono completi, niente anno di nascita.
    Le righe senza nome restano col numero solo se c'era un giocatore (chi non ha il consenso)."""
    giocatori = []
    for g in (dati or {}).get("giocatori") or []:
        nome = str(g.get("GIOCATORE") or "").strip()
        if not nome:
            giocatori.append({**g, "ANNO": ""} if modo != COMPLETI else g)
            continue
        ridotto = nome_ridotto(nome, modo, persone)
        giocatori.append({**g, "GIOCATORE": ridotto or "—", "ANNO": g.get("ANNO", "") if modo == COMPLETI else ""})
    return {**(dati or {}), "giocatori": giocatori}


def evento_pubblico(testo, modo, persone=()):
    """Il giocatore di un evento della diretta; le sostituzioni sono "entra X, esce Y"."""
    parti = []
    for parte in str(testo or "").split(", "):
        m = re.match(r"(?i)(entra|esce)\s+(.*)", parte)
        if m:
            parti.append(f"{m.group(1)} {nome_ridotto(m.group(2), modo, persone) or '—'}")
        else:
            parti.append(nome_ridotto(parte, modo, persone))
    return ", ".join(p for p in parti if p)


def modo_partita(info_gara):
    """Il modo della squadra di una partita, dalla competizione scelta nella distinta."""
    from stagioni import gruppi_correnti, gruppo_di
    stagione, _ = gruppi_correnti()
    return modo_gruppo(gruppo_di((info_gara or {}).get("campionato"), stagione))


def persone_anagrafica():
    try:
        from anagrafica import elenco_ragazzi
        return elenco_ragazzi()
    except Exception:  # noqa: BLE001 - senza anagrafica si applica solo la scelta della squadra
        return []


_COMPLETA_ONLINE = "impostazioni/ultima_distinta.json"


def salva_distinta_completa(pacchetto):
    """La distinta pubblicata con i nomi completi, nello spazio privato: dopo un riavvio la cronaca la riprende
    da qui e non da distinta.json, che per le giovanili ha i nomi ridotti. Non deve mai bloccare la pubblicazione."""
    try:
        percorso = os.path.join(_cartella_dati(), "ultima_distinta.json")
        with open(percorso, "w", encoding="utf-8") as f:
            json.dump(pacchetto, f, ensure_ascii=False)
        _carica_online(_COMPLETA_ONLINE, percorso, "application/json")
    except Exception:  # noqa: BLE001
        pass


def leggi_distinta_completa():
    try:
        return json.loads(_leggi_file(os.path.join(_cartella_dati(), "ultima_distinta.json"), _COMPLETA_ONLINE))
    except Exception:  # noqa: BLE001
        return None
