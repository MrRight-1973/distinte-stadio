"""Avvia dall'app la GitHub Action "Classifiche" (classifica, risultati e calendario dalla LND) e dice se sta
già girando.

Serve un token GitHub con accesso al repository dell'app e il permesso "Actions: Read and write": si usa il
secret GITHUB_TOKEN_AZIONI se c'è, altrimenti GITHUB_TOKEN (quello della pagina spettatori, se ha anche
questo permesso). Il repository è GITHUB_REPO_APP, oppure quello dell'app su Streamlit.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from github_publisher import GITHUB_API, _intestazioni, normalizza_repo

REPO_APP = "MrRight-1973/distinte-stadio"
WORKFLOW = "classifiche.yml"
_ROMA = ZoneInfo("Europe/Rome")
_stato = {"quando": 0.0, "chiave": None, "valore": None}


class AzioneErrore(Exception):
    pass


def _ora(iso):
    """'2026-10-21T12:07:48Z' -> '14:07' (ora italiana)."""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(_ROMA).strftime("%H:%M")
    except (AttributeError, ValueError):
        return ""


def _secondi(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return 0


def stato(token, repo=None, fresco=False):
    """{"in_corso": bool, "dalle": "hh:mm", "esito": "success"/"failure"/..., "finita": "hh:mm"} dell'ultimo
    giro, o None se non si riesce a saperlo. Chiede a GitHub al massimo ogni 15 secondi."""
    repo = normalizza_repo(repo or REPO_APP)
    if not token:
        return None
    if not fresco and _stato["chiave"] == repo and time.time() - _stato["quando"] < 15:
        return _stato["valore"]
    valore = None
    try:
        r = requests.get(f"{GITHUB_API}/repos/{repo}/actions/workflows/{WORKFLOW}/runs?per_page=1",
                         headers=_intestazioni(token), timeout=10)
        giri = (r.json().get("workflow_runs") or []) if r.status_code == 200 else []
        if giri:
            g = giri[0]
            valore = {"in_corso": g.get("status") in ("queued", "in_progress", "waiting", "requested", "pending"),
                      "dalle": _ora(g.get("run_started_at") or g.get("created_at")),
                      "esito": g.get("conclusion") or "", "finita": _ora(g.get("updated_at")),
                      "creata": _secondi(g.get("created_at"))}
    except (requests.RequestException, ValueError):
        valore = None
    _stato.update(quando=time.time(), chiave=repo, valore=valore)
    return valore


def avvia(token, repo=None):
    """Lancia la Action sul ramo main. Errore con un messaggio chiaro se GitHub non lo permette."""
    repo = normalizza_repo(repo or REPO_APP)
    if not token:
        raise AzioneErrore("Manca il token GitHub nei secrets dell'app (GITHUB_TOKEN_AZIONI).")
    try:
        r = requests.post(f"{GITHUB_API}/repos/{repo}/actions/workflows/{WORKFLOW}/dispatches",
                          headers=_intestazioni(token), json={"ref": "main"}, timeout=15)
    except requests.RequestException as e:
        raise AzioneErrore("GitHub non risponde: riprova tra poco.") from e
    if r.status_code in (403, 404):
        raise AzioneErrore(f"GitHub non lascia avviare l'aggiornamento: il token deve avere accesso a {repo} "
                           "con il permesso \"Actions: Read and write\".")
    if r.status_code == 401:
        raise AzioneErrore("GitHub non accetta il token: è errato o scaduto.")
    if r.status_code >= 300:
        raise AzioneErrore(f"GitHub ha risposto con un errore ({r.status_code}).")
    _stato.update(quando=0.0, chiave=None, valore=None)
