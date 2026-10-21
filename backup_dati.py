"""Backup settimanale dei dati della società in uno ZIP nello spazio privato di Supabase.

Dentro: anagrafica e impostazioni, presenze, distinte ufficiali, utenti, registro delle modifiche e i dati
di tutte le partite (senza foto né note vocali, che restano dove sono). Finisce in backup/backup_<data>.zip,
nello stesso spazio privato: non va mai sulla pagina pubblica. Si tengono gli ultimi TENUTI.

Lo lancia ogni settimana la GitHub Action "Backup dati" (python backup_dati.py, con SUPABASE_URL e
SUPABASE_KEY nei secrets del repository); dall'app si può fare anche a mano in Opzioni.
"""
import io
import json
import os
import sys
import zipfile
from datetime import date, datetime

import archivio_cloud as cloud

CARTELLE = ("impostazioni", "presenze", "distinte_ufficiali", "utenti", "registro")
# Quello che si può riprendere da un backup (il registro no: è la storia, e resta com'è; le partite hanno già
# il loro backup per stagione nell'Archivio)
RIPRISTINABILI = {"impostazioni": "Anagrafica, campionati, rose e impostazioni", "presenze": "Presenze agli allenamenti",
                  "distinte_ufficiali": "Distinte (Crea distinta)", "utenti": "Utenti e password"}
CARTELLA_BACKUP = "backup"
TENUTI = 8  # circa due mesi di backup settimanali


def crea_zip():
    """(bytes dello ZIP, numero di file dentro)."""
    buffer, contati = io.BytesIO(), 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for cartella in CARTELLE:
            for nome in sorted(cloud.elenco_file(cartella)):
                dati = cloud.scarica_file(f"{cartella}/{nome}")
                if dati is not None:
                    z.writestr(f"{cartella}/{nome}", dati)
                    contati += 1
        z.writestr("partite.json", json.dumps(cloud.dati_partite(), ensure_ascii=False, indent=1))
        contati += 1
    return buffer.getvalue(), contati


def elenco_backup():
    """[(nome, byte)] dei backup salvati, dal più recente."""
    trovati = cloud.elenco_file(CARTELLA_BACKUP)
    return sorted(((n, b) for n, b in trovati.items() if n.endswith(".zip")), reverse=True)


def scarica_backup(nome):
    return cloud.scarica_file(f"{CARTELLA_BACKUP}/{nome}")


def fai_backup(oggi=None, nome=None):
    """Crea e carica il backup di oggi, poi toglie i più vecchi. Restituisce (nome, byte, file dentro)."""
    dati, contati = crea_zip()
    nome = nome or f"backup_{(oggi or date.today()).isoformat()}.zip"
    cloud.carica_file(f"{CARTELLA_BACKUP}/{nome}", dati, "application/zip")
    vecchi = [n for n, _ in elenco_backup()][TENUTI:]
    cloud.elimina_file([f"{CARTELLA_BACKUP}/{n}" for n in vecchi])
    return nome, len(dati), contati


def contenuto(dati_zip):
    """{cartella ripristinabile: [file]} dentro uno ZIP di backup."""
    trovati = {}
    for nome in zipfile.ZipFile(io.BytesIO(dati_zip)).namelist():
        cartella, _, file = nome.partition("/")
        if cartella in RIPRISTINABILI and file and "/" not in file:
            trovati.setdefault(cartella, []).append(file)
    return trovati


def ripristina(nome, cartelle):
    """Rimette i file delle cartelle scelte com'erano nel backup "nome". Prima salva un backup di adesso
    (così si può tornare indietro). I file nati dopo il backup (es. un anno sportivo nuovo) restano.
    Restituisce (file ripristinati, nome del backup di sicurezza)."""
    import registro  # qui e non in cima: l'Action del backup installa solo requests
    from cronaca_manager import _cartella_dati, _da_caricare
    dati_zip = scarica_backup(nome)
    if dati_zip is None:
        raise cloud.ArchivioErrore(f"Il backup {nome} non c'è più.")
    sicurezza = f"backup_{datetime.now():%Y-%m-%d_%H%M}_prima_del_ripristino.zip"
    fai_backup(nome=sicurezza)
    z = zipfile.ZipFile(io.BytesIO(dati_zip))
    rimessi = 0
    for cartella, file in contenuto(dati_zip).items():
        if cartella not in cartelle:
            continue
        for f in file:
            percorso = f"{cartella}/{f}"
            cloud.carica_file(percorso, z.read(percorso), "application/json")
            _da_caricare.pop(percorso, None)  # un caricamento rimasto in sospeso non deve ricoprirlo
            try:  # la copia sul disco dell'app è quella letta per prima: va tolta, si riprende da Supabase
                os.remove(os.path.join(_cartella_dati(), f))
            except OSError:
                pass
            rimessi += 1
    registro.segna("Ripristino dal backup", f"{nome}: {', '.join(c for c in cartelle)} ({rimessi} file); "
                                            f"prima salvato {sicurezza}")
    return rimessi, sicurezza


def main():
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("Secrets SUPABASE_URL / SUPABASE_KEY non configurati: niente da fare.")
        return 0
    cloud.configura(url, key)
    try:
        nome, byte, contati = fai_backup()
    except cloud.ArchivioErrore as e:
        print(f"Backup non riuscito: {e}")
        return 1
    print(f"Backup salvato: {nome} ({contati} file, {byte // 1024} KB)")  # solo nome e dimensione, mai i dati
    return 0


if __name__ == "__main__":
    sys.exit(main())
