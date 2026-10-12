"""Pubblicazione della distinta su un repository GitHub (servito da GitHub Pages).

Tutti i file vengono scritti in UN SOLO commit, così la pagina pubblica non può
mai mostrare un JSON nuovo con un PDF vecchio (o viceversa) e GitHub Pages
ricostruisce il sito una volta sola.

Il repository della pagina è pubblico e le distinte contengono nomi e anni di
nascita di ragazzi minorenni: per questo il nuovo commit NON ha genitori e
sostituisce il ramo. Il ramo contiene sempre un solo commit con lo stato
attuale, e le distinte delle partite passate non restano nella cronologia.

Il token deve essere un "fine-grained personal access token" con accesso al
repository della pagina e il permesso "Contents: Read and write".
"""
import base64
import re

import requests

GITHUB_API = "https://api.github.com"


class PubblicazioneErrore(Exception):
    """Errore comprensibile da mostrare alla segreteria."""


def normalizza_repo(repo):
    """Accetta 'utente/nome', ma anche un URL copiato dal browser o con '.git' finale."""
    if not repo:
        return ""
    r = str(repo).strip().strip("/")
    r = re.sub(r"^(?:https?://)?(?:www\.)?github\.com/", "", r, flags=re.IGNORECASE)
    r = re.sub(r"\.git$", "", r)
    return r.strip("/")


def _intestazioni(token, accept=None):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept or "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _chiama(metodo, url, token, timeout, ammetti_404=False, accept=None, **kwargs):
    try:
        r = requests.request(metodo, url, headers=_intestazioni(token, accept), timeout=timeout, **kwargs)
    except requests.RequestException as e:
        raise PubblicazioneErrore(f"GitHub non raggiungibile: {e}") from e

    if r.status_code == 401:
        raise PubblicazioneErrore("GitHub non accetta il token: GITHUB_TOKEN è errato o scaduto.")
    if r.status_code == 403:
        raise PubblicazioneErrore(
            "GitHub ha negato l'operazione: al token manca il permesso 'Contents: Read and write' "
            "sul repository (oppure è stato superato un limite di richieste)."
        )
    if r.status_code == 404 and not ammetti_404:
        raise PubblicazioneErrore("Risorsa non trovata su GitHub (HTTP 404).")
    if r.status_code == 409:
        raise PubblicazioneErrore(
            "Il repository è vuoto: carica prima almeno un file (per esempio index.html)."
        )
    return r


def _diagnosi_404(base, repo, branch, token, timeout):
    """Capisce COSA non è stato trovato e lo dice con precisione."""
    r = _chiama("GET", base, token, timeout, ammetti_404=True)
    if r.status_code == 404:
        return PubblicazioneErrore(
            f"Repository '{repo}' non trovato. Controlla che GITHUB_REPO sia scritto esattamente come "
            "'utente/nome-repository' e, soprattutto, che il token abbia accesso a QUESTO repository: "
            "nelle impostazioni del token (Repository access) deve essere incluso, e il proprietario "
            "(Resource owner) deve essere l'utente o l'organizzazione che possiede il repository."
        )
    if r.status_code == 200:
        predefinito = r.json().get("default_branch")
        if predefinito and predefinito != branch:
            return PubblicazioneErrore(
                f"Il ramo '{branch}' non esiste, ma il ramo principale del repository si chiama "
                f"'{predefinito}': imposta GITHUB_BRANCH = \"{predefinito}\" nei secrets "
                "(oppure toglilo, e verrà usato quello principale)."
            )
        return PubblicazioneErrore(
            f"Il ramo '{branch}' non è stato trovato. Se il repository è appena stato creato, "
            "carica prima almeno un file (per esempio index.html) con Add file → Upload files."
        )
    return PubblicazioneErrore(f"Lettura del repository fallita (HTTP {r.status_code}).")


def pubblica_su_github(token, repo, file_da_pubblicare, messaggio, branch=None,
                       api_base=GITHUB_API, timeout=20):
    """Scrive i file nel repository con un solo commit.

    file_da_pubblicare: dict {percorso_nel_repo: contenuto in bytes}.
        Un valore None significa "elimina questo file" (deve esistere nel repository).
    branch: se omesso si usa il ramo principale del repository.
    Restituisce lo sha del nuovo commit.
    """
    repo = normalizza_repo(repo)
    token = (token or "").strip()
    if not token or not repo:
        raise PubblicazioneErrore("GITHUB_TOKEN o GITHUB_REPO non configurati nei secrets.")
    if repo.count("/") != 1:
        raise PubblicazioneErrore(
            f"GITHUB_REPO ('{repo}') non è nel formato 'utente/nome-repository'."
        )
    if not file_da_pubblicare:
        raise PubblicazioneErrore("Nessun file da pubblicare.")

    base = f"{api_base}/repos/{repo}"

    branch = (branch or "").strip()
    if not branch:
        r = _chiama("GET", base, token, timeout, ammetti_404=True)
        if r.status_code == 404:
            raise _diagnosi_404(base, repo, "main", token, timeout)
        if r.status_code != 200:
            raise PubblicazioneErrore(f"Lettura del repository fallita (HTTP {r.status_code}).")
        branch = r.json().get("default_branch") or "main"

    for tentativo in range(2):  # secondo giro solo se qualcuno ha scritto nel frattempo
        # 1) ultimo commit del ramo
        r = _chiama("GET", f"{base}/git/ref/heads/{branch}", token, timeout, ammetti_404=True)
        if r.status_code == 404:
            raise _diagnosi_404(base, repo, branch, token, timeout)
        if r.status_code != 200:
            raise PubblicazioneErrore(f"Lettura del ramo '{branch}' fallita (HTTP {r.status_code}).")
        sha_commit = r.json()["object"]["sha"]

        r = _chiama("GET", f"{base}/git/commits/{sha_commit}", token, timeout)
        if r.status_code != 200:
            raise PubblicazioneErrore(f"Lettura del commit fallita (HTTP {r.status_code}).")
        sha_albero = r.json()["tree"]["sha"]

        # 2) un blob per ogni file
        voci = []
        for percorso, contenuto in file_da_pubblicare.items():
            if contenuto is None:  # eliminazione: nell'albero il file ha sha nullo
                voci.append({"path": percorso, "mode": "100644", "type": "blob", "sha": None})
                continue
            r = _chiama(
                "POST", f"{base}/git/blobs", token, timeout,
                json={"content": base64.b64encode(contenuto).decode("ascii"), "encoding": "base64"},
            )
            if r.status_code != 201:
                raise PubblicazioneErrore(f"Caricamento di {percorso} fallito (HTTP {r.status_code}).")
            voci.append({"path": percorso, "mode": "100644", "type": "blob", "sha": r.json()["sha"]})

        # 3) nuovo albero, nuovo commit, aggiornamento del ramo
        r = _chiama("POST", f"{base}/git/trees", token, timeout,
                    json={"base_tree": sha_albero, "tree": voci})
        if r.status_code != 201:
            raise PubblicazioneErrore(f"Creazione dell'albero fallita (HTTP {r.status_code}).")
        nuovo_albero = r.json()["sha"]

        r = _chiama("POST", f"{base}/git/commits", token, timeout,
                    json={"message": messaggio, "tree": nuovo_albero, "parents": []})
        if r.status_code != 201:
            raise PubblicazioneErrore(f"Creazione del commit fallita (HTTP {r.status_code}).")
        nuovo_commit = r.json()["sha"]

        # Il commit senza genitori si sostituisce al ramo solo forzando: prima si controlla
        # che nel frattempo nessuno (es. il salvataggio degli sponsor) abbia scritto.
        r = _chiama("GET", f"{base}/git/ref/heads/{branch}", token, timeout)
        if r.status_code == 200 and r.json()["object"]["sha"] != sha_commit:
            if tentativo == 0:
                continue  # il ramo si è mosso: si riparte dall'ultimo commit
            raise PubblicazioneErrore("Il repository è stato modificato durante la pubblicazione: riprova.")
        r = _chiama("PATCH", f"{base}/git/refs/heads/{branch}", token, timeout,
                    json={"sha": nuovo_commit, "force": True})
        if r.status_code == 200:
            return nuovo_commit
        raise PubblicazioneErrore(f"Aggiornamento del ramo fallito (HTTP {r.status_code}).")

    raise PubblicazioneErrore("Pubblicazione non riuscita: riprova tra qualche istante.")


def leggi_file(token, repo, percorso, branch=None, api_base=GITHUB_API, timeout=20):
    """Contenuto (bytes) di un file del repository; None se il file non esiste."""
    repo = normalizza_repo(repo)
    if not token or not repo:
        raise PubblicazioneErrore("GITHUB_TOKEN o GITHUB_REPO non configurati nei secrets.")
    r = _chiama(
        "GET", f"{api_base}/repos/{repo}/contents/{percorso}", token.strip(), timeout,
        ammetti_404=True, accept="application/vnd.github.raw+json",
        params={"ref": branch} if branch else None,
    )
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise PubblicazioneErrore(f"Lettura di {percorso} fallita (HTTP {r.status_code}).")
    return r.content


def elenca_cartella(token, repo, percorso, branch=None, api_base=GITHUB_API, timeout=20):
    """Nomi dei file contenuti in una cartella del repository (lista vuota se non esiste)."""
    repo = normalizza_repo(repo)
    if not token or not repo:
        raise PubblicazioneErrore("GITHUB_TOKEN o GITHUB_REPO non configurati nei secrets.")
    r = _chiama(
        "GET", f"{api_base}/repos/{repo}/contents/{percorso}", token.strip(), timeout,
        ammetti_404=True, params={"ref": branch} if branch else None,
    )
    if r.status_code == 404:
        return []
    if r.status_code != 200:
        raise PubblicazioneErrore(f"Lettura della cartella {percorso} fallita (HTTP {r.status_code}).")
    dati = r.json()
    if not isinstance(dati, list):
        return []
    return [voce["name"] for voce in dati if voce.get("type") == "file"]


def url_pagina_da_repo(repo):
    """URL standard di GitHub Pages per un repository 'utente/nome'."""
    repo = normalizza_repo(repo)
    try:
        utente, nome = repo.split("/", 1)
    except ValueError:
        return None
    if not utente or not nome:
        return None
    if nome.lower() == f"{utente.lower()}.github.io":
        return f"https://{utente}.github.io/"
    return f"https://{utente}.github.io/{nome}/"
