"""Contatore anonimo delle visite alla pagina spettatori: ogni apertura manda alla funzione conta_visita di
Supabase la partita mostrata e un numero a caso che il telefono si tiene (niente nomi né indirizzi IP).

Serve la tabella di supabase/visite.sql e, nei secrets, SUPABASE_PUBBLICA: la chiave pubblica di Supabase
("publishable" o "anon"), fatta apposta per stare nelle pagine web. Con quella la pagina può solo aggiungere
una visita; leggere il riepilogo può solo l'app, con la chiave segreta."""
import requests

import archivio_cloud as cloud


def dati_visite(chiave_pubblica, partita):
    """Quello che la pagina spettatori deve sapere per contare la visita; {} se il contatore non è attivo."""
    if not (chiave_pubblica and cloud.attivo()):
        return {}
    return {"url": f"{cloud._config['url']}/rest/v1/rpc/conta_visita", "chiave": str(chiave_pubblica).strip(),
            "partita": str(partita or "Pagina")[:200]}


class VisiteErrore(Exception):
    pass


def riepilogo():
    """[{partita, primo_giorno, ultimo_giorno, aperture, dispositivi}] dalla più recente. Non passa da
    archivio_cloud._chiama: un contatore non ancora preparato non è un errore dell'archivio."""
    if not cloud.attivo():
        raise VisiteErrore("Archivio online non configurato.")
    try:
        r = requests.post(f"{cloud._config['url']}/rest/v1/rpc/riepilogo_visite", json={},
                          headers=cloud._intestazioni(), timeout=cloud.TIMEOUT)
    except requests.RequestException as e:
        raise VisiteErrore("Supabase non raggiungibile.") from e
    if r.status_code == 404 or "riepilogo_visite" in r.text and r.status_code >= 400:
        raise VisiteErrore("manca")
    if r.status_code >= 400:
        raise VisiteErrore(f"Errore {r.status_code} da Supabase.")
    return r.json()
