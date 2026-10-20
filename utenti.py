"""Utenti della segreteria, salvati su Supabase con la password cifrata (mai in chiaro).

Quattro livelli: "admin" vede tutte le sezioni e gestisce gli utenti; "segreteria" vede Distinta,
Cronaca partita e tutta l'Anagrafica; "allenatore" vede Distinta, Cronaca e nell'Anagrafica solo i
ragazzi dei suoi gruppi squadra; "user" vede solo Distinta e Cronaca partita (niente dati dei ragazzi).
Per ogni utente non amministratore si possono scegliere a mano le aree visibili ("aree"); il ruolo
decide comunque quali ragazzi vede (tutti per la segreteria, solo i suoi gruppi per gli altri). La password SEGRETERIA_PASSWORD dei secrets resta sempre
valida come accesso admin di emergenza (utente "admin" o nome vuoto).
"""
import hashlib
import hmac
import json
import os
import re
import secrets

from cronaca_manager import _cartella_dati, _carica_online, _leggi_file

RUOLI = {"admin": "Amministratore (tutto)", "segreteria": "Segreteria (Distinta, Cronaca, Anagrafica)",
         "allenatore": "Allenatore (Distinta, Cronaca, i suoi ragazzi)", "user": "Utente (Distinta e Cronaca)"}
ITERAZIONI = 200_000
LUNGHEZZA_MINIMA = 8
PERCORSO_ONLINE = "utenti/utenti.json"


class UtentiErrore(Exception):
    """Errore comprensibile da mostrare in pagina."""


def cifra_password(password, sale=None, iterazioni=ITERAZIONI):
    sale = sale or secrets.token_hex(16)
    impronta = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(sale), iterazioni).hex()
    return f"pbkdf2_sha256${iterazioni}${sale}${impronta}"


def password_giusta(password, cifrata):
    try:
        _, iterazioni, sale, impronta = cifrata.split("$")
        prova = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(sale), int(iterazioni)).hex()
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(prova, impronta)


def normalizza_nome(nome):
    return re.sub(r"\s+", "", str(nome or "")).lower()


def _percorso():
    return os.path.join(_cartella_dati(), "utenti.json")


def elenco_utenti():
    """{nome: {"ruolo", "password"}}"""
    try:
        return json.loads(_leggi_file(_percorso(), PERCORSO_ONLINE))
    except (OSError, ValueError):
        return {}


def _salva(utenti):
    with open(_percorso(), "w", encoding="utf-8") as f:
        json.dump(utenti, f, ensure_ascii=False)
    _carica_online(PERCORSO_ONLINE, _percorso(), "application/json")


def _controlla_password(password):
    if len(password or "") < LUNGHEZZA_MINIMA:
        raise UtentiErrore(f"La password deve avere almeno {LUNGHEZZA_MINIMA} caratteri.")


def aggiungi_utente(nome, password, ruolo):
    nome = normalizza_nome(nome)
    if not nome or nome == "admin":
        raise UtentiErrore("Scegli un nome utente (\"admin\" è riservato all'accesso di emergenza).")
    if ruolo not in RUOLI:
        raise UtentiErrore("Ruolo non valido.")
    _controlla_password(password)
    utenti = elenco_utenti()
    if nome in utenti:
        raise UtentiErrore(f"L'utente {nome} esiste già.")
    utenti[nome] = {"ruolo": ruolo, "password": cifra_password(password)}
    _salva(utenti)
    return nome


def cambia_password(nome, password):
    _controlla_password(password)
    utenti = elenco_utenti()
    if nome not in utenti:
        raise UtentiErrore(f"L'utente {nome} non esiste.")
    utenti[nome]["password"] = cifra_password(password)
    _salva(utenti)


def cambia_ruolo(nome, ruolo):
    """Cambiando ruolo, le aree tornano quelle del nuovo ruolo."""
    utenti = elenco_utenti()
    if nome in utenti and ruolo in RUOLI:
        utenti[nome]["ruolo"] = ruolo
        utenti[nome].pop("aree", None)
        _salva(utenti)


def cambia_aree(nome, aree):
    """Le aree (sezioni e pagine di Opzioni) che l'utente vede; None = quelle del suo ruolo."""
    utenti = elenco_utenti()
    if nome in utenti:
        if aree is None:
            utenti[nome].pop("aree", None)
        else:
            utenti[nome]["aree"] = list(aree)
        _salva(utenti)


def aree_utente(nome):
    """Le aree scelte per l'utente, oppure None se valgono quelle del ruolo."""
    aree = (elenco_utenti().get(nome) or {}).get("aree")
    return list(aree) if isinstance(aree, list) else None


def cambia_gruppi(nome, gruppi):
    """I gruppi squadra di un allenatore: nell'Anagrafica vede solo i ragazzi di questi gruppi."""
    utenti = elenco_utenti()
    if nome in utenti:
        utenti[nome]["gruppi"] = sorted(set(gruppi))
        _salva(utenti)


def gruppi_utente(nome):
    return list((elenco_utenti().get(nome) or {}).get("gruppi") or [])


def rinomina_gruppo_allenatori(vecchio, nuovo):
    utenti = elenco_utenti()
    cambiati = False
    for dati in utenti.values():
        if vecchio in (dati.get("gruppi") or []):
            dati["gruppi"] = sorted({nuovo if g == vecchio else g for g in dati["gruppi"]})
            cambiati = True
    if cambiati:
        _salva(utenti)


def elimina_utente(nome):
    utenti = elenco_utenti()
    if utenti.pop(nome, None) is not None:
        _salva(utenti)


def accedi(nome, password, password_emergenza):
    """(nome, ruolo) se le credenziali sono giuste, altrimenti None."""
    nome = normalizza_nome(nome)
    if nome in ("", "admin"):
        if password_emergenza and hmac.compare_digest(password.encode(), str(password_emergenza).encode()):
            return "admin", "admin"
        return None
    utente = elenco_utenti().get(nome)
    if utente and password_giusta(password, utente.get("password", "")):
        return nome, utente.get("ruolo", "user")
    return None
