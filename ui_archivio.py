"""Sezione "Archivio" del pannello segreteria: le partite chiuse, lo spazio occupato su Supabase,
il backup ZIP (dati, resoconto PDF, foto, note vocali) e la liberazione dello spazio."""
import json
from datetime import datetime

import streamlit as st

import archivio_cloud
from cronaca_manager import (
    ELENCHI_FOTO,
    alleggerisci_partita,
    carica_cronaca,
    conta_file,
    crea_backup,
    elimina_partita_archiviata,
    fase_in_corso,
    file_collegati,
    pulisci_file_orfani,
    partite_archiviate,
    riapri_partita,
    ripristina_backup,
    stato_archivio_online,
)
from cronaca_pdf import genera_pdf_resoconto
from giornata import campionato_e_giornata
from nomi_file import nome_file_gara

# Limiti del piano gratuito di Supabase
LIMITE_FILE = 1024 ** 3        # 1 GB per foto e note vocali
LIMITE_DATI = 500 * 1024 ** 2  # 500 MB di database
CARTELLE = ("foto", "audio", "distinte_pubblicate", "in_lavorazione")


def _misura(n):
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB".replace(".", ",")
    return f"{n / 1024 ** 3:.2f} GB".replace(".", ",")


def _spazio(tutte):
    """Indicatori dello spazio usato; restituisce {percorso online: byte} per pesare ogni partita.
    tutte: {id: dati} di tutte le partite salvate."""
    file = {}
    for cartella in CARTELLE:
        file.update({f"{cartella}/{nome}": byte for nome, byte in archivio_cloud.elenco_file(cartella).items()})
    usati_file = sum(file.values())
    usati_dati = sum(len(json.dumps(d, ensure_ascii=False).encode()) for d in tutte.values())
    with st.container(border=True):
        st.markdown("**💾 Spazio su Supabase** (piano gratuito)")
        st.progress(min(usati_file / LIMITE_FILE, 1.0),
                    text=f"Foto e note vocali: {_misura(usati_file)} su 1 GB ({usati_file / LIMITE_FILE:.0%})")
        st.progress(min(usati_dati / LIMITE_DATI, 1.0),
                    text=f"Dati delle partite: {_misura(usati_dati)} su 500 MB ({usati_dati / LIMITE_DATI:.1%})")
        if usati_file > 0.8 * LIMITE_FILE:
            st.warning("Lo spazio per le foto è quasi pieno: fai un backup delle partite vecchie e libera spazio.")
        _dettaglio_spazio(file, tutte)
    return file


def _dettaglio_spazio(file, tutte):
    """Di chi sono le foto: archivio, partita aperta, distinte pubblicate, file rimasti senza partita."""
    usati = file_collegati(tutte)
    gruppi = {"archivio": 0, "aperta": 0, "distinte": 0, "orfani": 0}
    orfani = []
    for percorso, byte in file.items():
        if percorso.startswith(("distinte_pubblicate/", "in_lavorazione/")):
            gruppi["distinte"] += byte
        elif percorso in usati["aperta"]:
            gruppi["aperta"] += byte
        elif percorso in usati["archivio"]:
            gruppi["archivio"] += byte
        else:
            gruppi["orfani"] += byte
            orfani.append(percorso)
    st.caption(f"Partite in archivio {_misura(gruppi['archivio'])} · partita aperta in Cronaca "
               f"{_misura(gruppi['aperta'])} · foto delle distinte caricate e pubblicate {_misura(gruppi['distinte'])}"
               + (f" · file non più usati {_misura(gruppi['orfani'])}" if orfani else ""))
    if orfani and st.button(f"🧽 Elimina {len(orfani)} file non più usati ({_misura(gruppi['orfani'])})",
                            use_container_width=True):
        if _prova(pulisci_file_orfani, orfani):
            st.session_state["arch_messaggio"] = f"🧽 Eliminati {len(orfani)} file che nessuna partita usava."
            st.rerun()


def _prova(funzione, *argomenti):
    try:
        funzione(*argomenti)
        return True
    except archivio_cloud.ArchivioErrore as e:
        st.error(str(e))
        return False


def _riga_partita(p, cronaca, dati_file):
    gol = "–" if p.get("gol_casa") is None else f"{p['gol_casa']} – {p['gol_ospite']}"
    with st.container(border=True):
        st.checkbox(f"**{p.get('casa') or 'Casa'} {gol} {p.get('ospite') or 'Ospite'}**", key=f"arch_sel_{p['id']}")
        info = [x for x in (p.get("data"), campionato_e_giornata(p.get("campionato"), p.get("giornata"))) if x]
        if dati_file:
            info.append(dati_file)
        st.caption(" · ".join(info) or "Senza data")

        if st.session_state.get("arch_da_eliminare") == p["id"]:
            st.warning("Eliminare definitivamente questa partita, con foto e note vocali?")
            c1, c2 = st.columns(2)
            if c1.button("🗑️ Sì, elimina", key=f"arch_si_{p['id']}", type="primary", use_container_width=True):
                if _prova(elimina_partita_archiviata, p["id"]):
                    st.session_state.pop("arch_da_eliminare", None)
                    st.rerun()
            if c2.button("Annulla", key=f"arch_no_{p['id']}", use_container_width=True):
                st.session_state.pop("arch_da_eliminare", None)
                st.rerun()
            return
        c1, c2 = st.columns(2)
        if c1.button("📂 Riapri in Cronaca", key=f"arch_apri_{p['id']}", use_container_width=True):
            if fase_in_corso(cronaca):
                st.error("C'è un tempo in corso nella Cronaca: chiudilo prima di riaprire un'altra partita.")
            else:
                if not _prova(riapri_partita, cronaca, p["id"]):
                    return
                st.session_state["vai_a_sezione"] = "🎙️ Cronaca partita"
                st.session_state["cronaca_messaggio"] = ("success", "📂 Partita riaperta: quella di prima è in archivio.")
                st.rerun()
        if c2.button("🗑️ Elimina", key=f"arch_elimina_{p['id']}", use_container_width=True):
            st.session_state["arch_da_eliminare"] = p["id"]
            st.rerun()


def _descrizione_file(dati_partita, file_online):
    """Testo tipo "📷 4 foto · 🎙️ 2 vocali · 3,1 MB" oppure "📦 solo dati" per una partita."""
    if dati_partita.get("alleggerita"):
        a = dati_partita["alleggerita"]
        return f"📦 solo dati: foto e vocali tolti il {a.get('il', '')} (sono nel backup)"
    foto, audio = conta_file(dati_partita)
    if not foto and not audio:
        return ""
    nomi = [f"foto/{n}" for e in ELENCHI_FOTO for n in dati_partita.get(e) or []]
    nomi += [f"audio/{n['audio']}" for n in dati_partita.get("note") or [] if n.get("audio")]
    byte = sum(file_online.get(n, 0) for n in nomi)
    parti = [f"📷 {foto} foto"] if foto else []
    if audio:
        parti.append(f"🎙️ {audio} vocali")
    return " · ".join(parti + [_misura(byte)])


def _azioni_selezione(selezionate, loghi_sponsor, cronaca):
    st.subheader(f"☑️ {len(selezionate)} partite selezionate")
    chiave = tuple(sorted(p["id"] for p in selezionate))
    backup = st.session_state.get("arch_backup")
    if not backup or backup["ids"] != chiave:
        st.caption("Il backup è un file ZIP con dati, resoconto PDF, foto e note vocali: salvalo sul PC o su Google Drive.")
        if st.button("📦 Prepara backup", type="primary", use_container_width=True):
            with st.spinner("Preparo il backup (scarico foto e creo i PDF)..."):
                loghi = loghi_sponsor()
                try:
                    zip_ = crea_backup(chiave, lambda c: genera_pdf_resoconto(c, sponsor_loghi=loghi))
                except archivio_cloud.ArchivioErrore as e:
                    st.error(str(e))
                    return
            st.session_state["arch_backup"] = {"ids": chiave, "zip": zip_, "scaricato": False}
            st.rerun()
        return

    if len(selezionate) == 1:
        p = selezionate[0]
        nome = nome_file_gara("Backup", p.get("data"), p.get("casa"), p.get("ospite"), "zip")
    else:
        nome = f"Backup_{len(selezionate)}_partite_{datetime.now():%Y-%m-%d}.zip"

    def scaricato():
        st.session_state["arch_backup"]["scaricato"] = True

    st.download_button(f"⬇️ Scarica backup ({_misura(len(backup['zip']))})", backup["zip"], file_name=nome,
                       mime="application/zip", on_click=scaricato, type="primary", use_container_width=True)
    if not backup["scaricato"]:
        st.caption("Dopo aver scaricato il backup potrai liberare spazio.")
        return

    st.markdown("**🧹 Libera spazio**")
    scelta = st.radio("Cosa togliere da Supabase?", [
        "Solo foto e note vocali: note, tabellino, articolo e statistiche restano",
        "Tutta la partita: resta solo nel backup",
    ], key="arch_cosa_togliere")
    conferma = st.checkbox("Ho salvato il backup in un posto sicuro", key="arch_conferma_backup")
    if st.button("🧹 Libera spazio", disabled=not conferma, use_container_width=True):
        azione = alleggerisci_partita if scelta.startswith("Solo") else elimina_partita_archiviata
        for id_partita in chiave:
            if not _prova(azione, id_partita):
                return
        st.session_state["arch_deseleziona"] = chiave  # le caselle si azzerano al giro successivo
        st.session_state.pop("arch_backup", None)
        st.session_state["arch_messaggio"] = f"🧹 Spazio liberato per {len(chiave)} partite."
        st.rerun()


def _ripristino(cronaca):
    with st.expander("♻️ Ripristina da un backup"):
        st.caption("Rimette nell'archivio le partite di un file ZIP creato qui, con foto e note vocali.")
        f = st.file_uploader("File di backup (.zip)", type=["zip"], key=f"arch_zip_{st.session_state.get('arch_zip_n', 0)}")
        if f and st.button("♻️ Ripristina", use_container_width=True):
            try:
                nomi, saltate = ripristina_backup(f.getvalue(), cronaca.get("id", ""))
            except Exception as e:
                st.error(f"Backup non leggibile: {e}")
                return
            st.session_state["arch_zip_n"] = st.session_state.get("arch_zip_n", 0) + 1
            st.session_state["arch_messaggio"] = (f"♻️ Ripristinate {len(nomi)} partite: " + ", ".join(nomi)) if nomi \
                else "Nel file non c'erano partite da ripristinare."
            if saltate:
                st.session_state["arch_messaggio"] += (" La partita aperta nella Cronaca non è stata toccata: "
                                                       "per ripristinarla, apri prima una nuova partita.")
            st.rerun()


def render_archivio(loghi_sponsor=lambda: None):
    st.header("📚 Archivio partite")
    if stato_archivio_online() is None:
        st.info("L'archivio funziona con Supabase: aggiungi SUPABASE_URL e SUPABASE_KEY nei secrets dell'app.")
        return
    messaggio = st.session_state.pop("arch_messaggio", None)
    if messaggio:
        st.success(messaggio)

    for id_partita in st.session_state.pop("arch_deseleziona", ()):
        st.session_state[f"arch_sel_{id_partita}"] = False
    cronaca = carica_cronaca()
    try:
        dettagli = archivio_cloud.dati_partite()
        file_online = _spazio(dettagli)
        partite = partite_archiviate(cronaca)
    except archivio_cloud.ArchivioErrore as e:
        st.warning(str(e))
        return

    if not partite:
        st.caption("Nessuna partita in archivio: ci finiscono con \"🆕 Nuova partita\" nella Cronaca.")
    else:
        st.caption("Le partite chiuse, dalla più recente. La partita aperta è nella Cronaca.")
        c1, c2 = st.columns(2)
        if c1.button("☑️ Seleziona tutte", use_container_width=True):
            for p in partite:
                st.session_state[f"arch_sel_{p['id']}"] = True
            st.rerun()
        if c2.button("Nessuna", use_container_width=True):
            for p in partite:
                st.session_state[f"arch_sel_{p['id']}"] = False
            st.rerun()
        for p in partite:
            _riga_partita(p, cronaca, _descrizione_file(dettagli.get(p["id"], {}), file_online))
        selezionate = [p for p in partite if st.session_state.get(f"arch_sel_{p['id']}")]
        if selezionate:
            st.markdown("---")
            _azioni_selezione(selezionate, loghi_sponsor, cronaca)
    st.markdown("---")
    _ripristino(cronaca)
