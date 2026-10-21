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
from datetime import date

import archivio_cloud as cloud

CARTELLE = ("impostazioni", "presenze", "distinte_ufficiali", "utenti", "registro")
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


def fai_backup(oggi=None):
    """Crea e carica il backup di oggi, poi toglie i più vecchi. Restituisce (nome, byte, file dentro)."""
    dati, contati = crea_zip()
    nome = f"backup_{(oggi or date.today()).isoformat()}.zip"
    cloud.carica_file(f"{CARTELLA_BACKUP}/{nome}", dati, "application/zip")
    vecchi = [n for n, _ in elenco_backup()][TENUTI:]
    cloud.elimina_file([f"{CARTELLA_BACKUP}/{n}" for n in vecchi])
    return nome, len(dati), contati


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
