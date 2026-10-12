"""Utenti della segreteria, salvati su Supabase con la password cifrata (mai in chiaro).

Due livelli: "admin" vede tutte le sezioni e gestisce gli utenti, "user" vede solo
Distinta e Cronaca partita. La password SEGRETERIA_PASSWORD dei secrets resta sempre
valida come accesso admin di emergenza (utente "admin" o nome vuoto).
"""
import hashlib
import hmac
import json
import os
import re
import secrets

from cronaca_manager import _cartella_dati, _carica_online, _leggi_file

RUOLI = {"admin": "Amministratore (tutto)", "user": "Utente (Distinta e Cronaca)"}
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
    utenti = elenco_utenti()
    if nome in utenti and ruolo in RUOLI:
        utenti[nome]["ruolo"] = ruolo
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
