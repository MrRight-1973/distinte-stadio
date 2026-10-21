"""Aggiorna da solo le classifiche salvate nell'app: per ogni squadra con un link (gare.lnd.it o Tuttocampo)
apre la pagina con un browser vero (la pagina della LND si costruisce nel browser), ne legge il testo e salva
la classifica in Supabase, come se l'avessero copiata e incollata.

Lo lancia la GitHub Action "Classifiche" (con SUPABASE_URL e SUPABASE_KEY nei secrets del repository).
Nel log solo il nome della squadra e quante righe ha letto.
"""
import os
import sys

import archivio_cloud as cloud
from classifica import ClassificaErrore, classifiche, leggi, link_attuale, nome_fonte, salva


def testo_della_pagina(browser, url):
    pagina = browser.new_page(locale="it-IT")
    try:
        pagina.goto(url, wait_until="networkidle", timeout=90_000)
        pagina.wait_for_timeout(5_000)  # i dati arrivano dopo il caricamento
        return pagina.inner_text("body")
    finally:
        pagina.close()


def main():
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("Secrets SUPABASE_URL / SUPABASE_KEY non configurati: niente da fare.")
        return 0
    cloud.configura(url, key)
    da_fare = {g: c for g, c in classifiche(fresca=True).items() if nome_fonte(c.get("fonte"))}
    if not da_fare:
        print("Nessuna classifica con un link salvato: niente da fare.")
        return 0
    from playwright.sync_api import sync_playwright
    errori = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        for gruppo, c in da_fare.items():
            try:
                righe = leggi(testo_della_pagina(browser, link_attuale(c["fonte"])))
            except (ClassificaErrore, Exception) as e:  # noqa: BLE001 - una squadra non blocca le altre
                print(f"{gruppo}: classifica non letta ({type(e).__name__}: {str(e)[:150]})")
                errori += 1
                continue
            salva(gruppo, c.get("stagione", ""), righe, link_attuale(c["fonte"]))
            print(f"{gruppo}: classifica aggiornata ({len(righe)} squadre, fonte {nome_fonte(c['fonte'])})")
        browser.close()
    return 1 if errori == len(da_fare) else 0


if __name__ == "__main__":
    sys.exit(main())
