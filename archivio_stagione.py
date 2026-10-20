"""📦 Chiudi stagione: un unico ZIP con tutto quello che riguarda un anno sportivo.

Dentro: le partite (dati, resoconto PDF, foto, note vocali, come il backup dell'archivio), le statistiche
in PDF per squadra, le presenze agli allenamenti (PDF come le tabelle del mister e dati), l'anagrafica dei
ragazzi in CSV e le impostazioni dell'anno. Dopo averlo scaricato si può liberare spazio su Supabase;
l'anagrafica resta nell'app, perché i ragazzi passano all'anno dopo.
"""
import csv
import io
import json
import re
import zipfile
from datetime import datetime

import archivio_cloud
from anagrafica import anno_di, elenco_ragazzi, nome_completo
from cronaca_manager import scrivi_partite
from presenze import (SIGLE, SIGLE_TABELLA, etichetta_corta, ordina, presenze_stagione, statistiche)
from stagioni import gruppo_di, impostazioni_stagioni, stagione_partita
from statistiche import chiave_squadra, risultati_squadra, squadre_presenti, statistiche_squadra
from statistiche_pdf import PARTI, genera_pdf_presenze, genera_pdf_statistiche

CAMPI_CSV = [("cognome", "Cognome"), ("nome", "Nome"), ("nascita", "Data di nascita"), ("matricola", "Matricola"),
             ("ruolo", "Ruolo"), ("documento_tipo", "Tipo documento"), ("documento_numero", "Numero documento"),
             ("documento_rilascio", "Rilasciato da"), ("documento_scadenza", "Scadenza documento"),
             ("certificato_scadenza", "Scadenza certificato"), ("genitore", "Genitore"), ("telefono", "Telefono")]


def _file(nome):
    return re.sub(r"[^\w\-. ]+", "-", nome).strip(" -") or "senza nome"


def partite_della_stagione(stagione):
    """{id: dati} delle partite archiviate di quell'anno sportivo."""
    return {i: d for i, d in archivio_cloud.dati_partite().items()
            if d and stagione_partita(d.get("partita")) == stagione}


def _csv_anagrafica(stagione):
    testo = io.StringIO()
    w = csv.writer(testo, delimiter=";")
    w.writerow([t for _, t in CAMPI_CSV] + [f"Squadra {stagione}"])
    for r in elenco_ragazzi():
        squadra = (r.get("gruppi") or {}).get(stagione, "")
        if squadra:
            w.writerow([r.get(k, "") for k, _ in CAMPI_CSV] + [squadra])
    return testo.getvalue().encode("utf-8-sig")


def _pdf_presenze(stagione, gruppo, allenamenti, schede):
    sedute = ordina(allenamenti)
    conti = statistiche(allenamenti)
    nome = {i: nome_completo(schede[i]) if i in schede else "(scheda eliminata)" for i in conti}
    ordine = sorted(conti, key=lambda i: nome[i])
    righe = [(nome[i], anno_di(schede.get(i, {})), [SIGLE.get(allenamenti[s].get(i), "") for s in sedute])
             for i in ordine]
    sigle = SIGLE_TABELLA + [SIGLE[s] for s in ("infortunato", "giustificato") if any(v[s] for v in conti.values())]
    return genera_pdf_presenze(gruppo, stagione, f"stagione {stagione}", righe,
                               [etichetta_corta(s) for s in sedute], sigle)


def crea_archivio_stagione(stagione, nome_societa, genera_pdf_resoconto=None):
    """Lo ZIP dell'anno sportivo; restituisce (bytes, riepilogo per il LEGGIMI e la pagina)."""
    partite = partite_della_stagione(stagione)
    presenze = presenze_stagione(stagione)
    schede = {r["id"]: r for r in elenco_ragazzi()}
    fatto = {"partite": len(partite), "statistiche": [], "presenze": [], "ragazzi": 0, "problemi": []}

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        scrivi_partite(z, sorted(partite), genera_pdf_resoconto, "partite")

        # Statistiche per squadra (e di tutte insieme se le squadre sono più di una)
        elenco = list(partite.values())
        for p in elenco:
            p["_gruppo"] = gruppo_di((p.get("partita") or {}).get("campionato"), stagione)
        squadre = squadre_presenti(elenco)
        if squadre:
            nostra = chiave_squadra(nome_societa) if nome_societa else ""
            chiave = nostra if any(k == nostra for k, _ in squadre) else squadre[0][0]
            nominati = sorted({p["_gruppo"] for p in elenco} - {""})
            tutte = len(nominati) != 1 or any(not p["_gruppo"] for p in elenco)
            for gruppo in nominati + ([None] if tutte else []):
                scelte = [p for p in elenco if gruppo is None or p["_gruppo"] == gruppo]
                riepilogo, per_partita = statistiche_squadra(scelte, chiave)
                if not per_partita:
                    continue
                titolo = gruppo or "Tutte le squadre"
                try:
                    z.writestr(f"statistiche/Statistiche {_file(titolo)}.pdf", genera_pdf_statistiche(
                        dict(squadre)[chiave], f"{stagione} · {titolo}", riepilogo, per_partita,
                        risultati_squadra(scelte, chiave), list(PARTI)))
                    fatto["statistiche"].append(titolo)
                except Exception as e:  # un PDF non riuscito non deve bloccare il resto
                    fatto["problemi"].append(f"Statistiche {titolo}: {e}")

        # Presenze agli allenamenti
        for gruppo, allenamenti in sorted(presenze.items()):
            if not allenamenti:
                continue
            try:
                z.writestr(f"allenamenti/Presenze {_file(gruppo)}.pdf",
                           _pdf_presenze(stagione, gruppo, allenamenti, schede))
                fatto["presenze"].append(f"{gruppo} ({len(allenamenti)} allenamenti)")
            except Exception as e:
                fatto["problemi"].append(f"Presenze {gruppo}: {e}")
        z.writestr("allenamenti/presenze.json", json.dumps({
            g: {s: {nome_completo(schede[i]) if i in schede else i: v for i, v in segnati.items()}
                for s, segnati in a.items()} for g, a in presenze.items()}, ensure_ascii=False, indent=1))

        # Anagrafica e impostazioni dell'anno
        z.writestr("anagrafica/ragazzi.csv", _csv_anagrafica(stagione))
        fatto["ragazzi"] = sum(1 for r in schede.values() if (r.get("gruppi") or {}).get(stagione))
        z.writestr("impostazioni/squadre_e_competizioni.json", json.dumps(
            impostazioni_stagioni()["stagioni"].get(stagione, []), ensure_ascii=False, indent=1))

        z.writestr("LEGGIMI.txt", "\n".join([
            f"Archivio della stagione {stagione} · {nome_societa}",
            f"Creato il {datetime.now():%d/%m/%Y alle %H:%M}",
            "",
            f"partite/       {fatto['partite']} partite: dati, resoconto PDF, foto e note vocali",
            f"statistiche/   {', '.join(fatto['statistiche']) or 'nessuna'}",
            f"allenamenti/   {', '.join(fatto['presenze']) or 'nessuna presenza segnata'}",
            f"anagrafica/    {fatto['ragazzi']} ragazzi con una squadra nella stagione (dati personali: "
            "conservare in un posto protetto)",
            "",
            "Le partite si possono rimettere nell'app con «Ripristina da un backup» in Archivio "
            "(serve uno ZIP con le sole cartelle delle partite).",
        ] + (["", "Problemi:"] + fatto["problemi"] if fatto["problemi"] else [])))
    return buffer.getvalue(), fatto
