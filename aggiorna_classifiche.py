"""Aggiorna da solo le classifiche salvate nell'app: per ogni squadra con un link (gare.lnd.it o Tuttocampo)
apre la pagina con un browser vero (la pagina della LND si costruisce nel browser), ne legge il testo e salva
la classifica in Supabase, come se l'avessero copiata e incollata.

Lo lancia la GitHub Action "Classifiche" (con SUPABASE_URL e SUPABASE_KEY nei secrets del repository).
Per le pagine della LND legge anche tutte le giornate (andata e ritorno) con risultati e calendario, così
l'app ha i numeri di tutte le squadre del girone (📊 Statistiche → 📅 Risultati e 🔍 Avversari). Le giornate già
finite non si rileggono. Dalla classifica prende anche gli stemmi delle squadre (una volta sola per squadra).
Alla fine scrive nello spazio pubblico di Supabase classifica.json: la classifica che mostra la pagina
spettatori mentre aspetta la prossima partita (posizione, squadra, punti, partite e stemma).

Nel log solo il nome della squadra e quante righe o partite ha letto (sono dati pubblici).
"""
import os
import sys
from datetime import date, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import json

import archivio_cloud as cloud
import girone
import loghi
from classifica import ClassificaErrore, classifiche, leggi, link_attuale, nome_fonte, salva


# per ogni immagine della pagina: il suo indirizzo e il testo più vicino (la riga con il nome della squadra)
_IMMAGINI_JS = """() => [...document.images].map(i => {
  let n = i, t = "";
  for (let k = 0; k < 4 && n && !t; k++) { n = n.parentElement; t = n ? (n.innerText || "").trim() : ""; }
  return [i.currentSrc || i.src || "", t.slice(0, 300)];
})"""


def testo_della_pagina(browser, url, immagini=None):
    """Il testo della pagina; se `immagini` è una lista, ci aggiunge [(indirizzo, testo vicino)] delle immagini."""
    pagina = browser.new_page(locale="it-IT")
    try:
        pagina.goto(url, wait_until="networkidle", timeout=90_000)
        pagina.wait_for_timeout(5_000)  # i dati arrivano dopo il caricamento
        if immagini is not None:
            immagini.extend(pagina.evaluate(_IMMAGINI_JS))
        return pagina.inner_text("body")
    finally:
        pagina.close()


def aggiorna_loghi(browser, gruppo, immagini, righe):
    """Copia gli stemmi delle squadre che non l'hanno ancora. Restituisce quanti ne ha aggiunti."""
    gia = loghi.tutti(fresco=True)
    nuovi = 0
    for squadra, src in loghi.abbina(immagini, [r["squadra"] for r in righe]).items():
        if loghi.di(squadra, gia):
            continue
        try:
            dentro = loghi.dati_immagine(src)
            if dentro:
                dati, tipo = dentro
            else:
                pagina = browser.new_page()
                try:
                    r = pagina.request.get(src, timeout=20_000)
                    dati, tipo = (r.body(), r.headers.get("content-type", "")) if r.ok else (b"", "")
                finally:
                    pagina.close()
            nuovi += 1 if loghi.salva(squadra, dati, tipo) else 0
        except Exception:  # noqa: BLE001 - uno stemma mancante non è un problema
            continue
    print(f"{gruppo}: stemmi {len(gia) + nuovi} in tutto ({nuovi} nuovi)")
    return nuovi


def pubblica_classifica_attesa():
    """classifica.json nello spazio pubblico: la legge la pagina spettatori in attesa della prossima partita."""
    from pagina_attesa import classifica_attesa
    dati = classifica_attesa(nome_societa=os.environ.get("NOME_SOCIETA", ""))
    if dati and cloud.carica_pubblico("classifica.json", json.dumps(dati, ensure_ascii=False).encode("utf-8")):
        print(f"Pagina spettatori: classifica di {dati['gruppo']} pubblicata")


def link_giornata(link, numero, fase):
    """Il link della pagina di una giornata: giornata=6&leg=first (andata) o leg=second (ritorno)."""
    indirizzo = urlparse(link_attuale(link))
    parametri = parse_qsl(indirizzo.query, keep_blank_values=True)
    parametri += [("giornata", str(numero)), ("leg", "first" if fase == "A" else "second")]
    return urlunparse(indirizzo._replace(query=urlencode(parametri)))


def da_rileggere(partite, oggi=None):
    """Una giornata si rilegge se manca, se ha ancora partite senza risultato e non è lontana nel futuro
    (le date possono cambiare: quelle oltre tre settimane si rileggono quando si avvicinano)."""
    if not partite:
        return True
    if girone.completa(partite):
        return False
    oggi = oggi or date.today()
    return min(p.get("data") or "9999" for p in partite) <= (oggi + timedelta(days=21)).isoformat()


def aggiorna_giornate(browser, gruppo, c, righe, mostra_testo=False):
    """Legge le giornate del girone dalla LND e le salva. Restituisce quante pagine ha letto."""
    squadre = [r["squadra"] for r in righe]
    per_fase = len(squadre) - 1 if len(squadre) % 2 == 0 else len(squadre)
    salvato = girone.tutti(fresco=True).get(gruppo) or {}
    vecchie = salvato.get("giornate", {}) if salvato.get("stagione") == c.get("stagione", "") else {}
    nuove, lette, vuote = {}, 0, 0
    for fase in ("A", "R"):
        for numero in range(1, per_fase + 1):
            if not da_rileggere(vecchie.get(girone.chiave(fase, numero))):
                continue
            try:
                testo = testo_della_pagina(browser, link_giornata(c["fonte"], numero, fase))
            except Exception as e:  # noqa: BLE001 - una giornata non blocca le altre
                print(f"{gruppo}: {girone.etichetta(girone.chiave(fase, numero))} non letta ({type(e).__name__})")
                continue
            lette += 1
            partite = girone.leggi_giornata(testo, squadre)
            if mostra_testo and lette == 1:
                print("--- inizio del testo della pagina ---\n" + testo[:1500] + "\n--- fine ---")
            if not partite:
                vuote += 1
                continue
            nuove[girone.giornata_della_pagina(testo) or girone.chiave(fase, numero)] = partite
    if nuove:
        girone.salva(gruppo, c.get("stagione", ""), nuove, link_attuale(c["fonte"]))
    giocate = sum(1 for p in nuove.values() for x in p if x.get("gol_casa") is not None)
    print(f"{gruppo}: {len(nuove)} giornate aggiornate su {lette} lette ({giocate} partite con risultato"
          + (f", {vuote} pagine senza partite riconosciute" if vuote else "") + ")")
    return lette


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
                immagini = []
                righe = leggi(testo_della_pagina(browser, link_attuale(c["fonte"]), immagini))
            except (ClassificaErrore, Exception) as e:  # noqa: BLE001 - una squadra non blocca le altre
                print(f"{gruppo}: classifica non letta ({type(e).__name__}: {str(e)[:150]})")
                errori += 1
                continue
            salva(gruppo, c.get("stagione", ""), righe, link_attuale(c["fonte"]))
            print(f"{gruppo}: classifica aggiornata ({len(righe)} squadre, fonte {nome_fonte(c['fonte'])})")
            aggiorna_loghi(browser, gruppo, immagini, righe)
            if nome_fonte(c["fonte"]) == "LND":
                aggiorna_giornate(browser, gruppo, c, righe, os.environ.get("MOSTRA_TESTO") == "si")
        browser.close()
    try:
        pubblica_classifica_attesa()
    except Exception as e:  # noqa: BLE001
        print(f"Pagina spettatori: classifica non pubblicata ({type(e).__name__})")
    return 1 if errori == len(da_fare) else 0


if __name__ == "__main__":
    sys.exit(main())
