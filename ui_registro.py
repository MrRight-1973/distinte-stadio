"""Opzioni → 🗂️ Registro e backup (solo admin): chi ha cambiato cosa, e i backup settimanali dei dati."""
import pandas as pd
import streamlit as st

import archivio_cloud
import backup_dati
import registro


def _render_registro():
    st.markdown("##### 📜 Registro delle modifiche")
    st.caption("Chi ha cambiato cosa in Anagrafica, Distinte, Allenamenti e Utenti. Si segnano solo i campi "
               "cambiati, mai i valori.")
    mesi = registro.mesi_disponibili()
    c1, c2 = st.columns(2)
    mese = c1.selectbox("Mese", mesi, key="reg_mese",
                        format_func=lambda m: f"{m[5:]}/{m[:4]}")
    voci = list(reversed(registro.voci_del_mese(mese)))
    chi = c2.selectbox("Utente", ["Tutti"] + sorted({v.get("chi") or "—" for v in voci}), key="reg_chi")
    cerca = st.text_input("Cerca", key="reg_cerca", placeholder="es. ROSSI, distinta, password")
    if chi != "Tutti":
        voci = [v for v in voci if (v.get("chi") or "—") == chi]
    if cerca.strip():
        t = cerca.strip().lower()
        voci = [v for v in voci if t in f"{v.get('cosa', '')} {v.get('dettaglio', '')}".lower()]
    if not voci:
        st.caption("Nessuna modifica segnata in questo mese.")
        return
    st.dataframe(pd.DataFrame([{"Quando": v.get("quando", ""), "Chi": v.get("chi") or "—", "Cosa": v.get("cosa", ""),
                                "Dettaglio": v.get("dettaglio", "")} for v in voci]),
                 hide_index=True, use_container_width=True)


def _render_backup():
    st.markdown("##### 🗄️ Backup automatici dei dati")
    st.caption(f"Ogni lunedì notte uno ZIP con anagrafica, presenze, distinte, utenti, registro e dati delle "
               f"partite (senza foto) nello spazio privato di Supabase. Si tengono gli ultimi {backup_dati.TENUTI}.")
    if not archivio_cloud.attivo():
        st.info("Serve l'archivio online (SUPABASE_URL e SUPABASE_KEY nei secrets).")
        return
    if st.button("🗄️ Fai un backup ora", key="bk_ora"):
        with st.spinner("Preparo il backup..."):
            try:
                nome, byte, contati = backup_dati.fai_backup()
                st.success(f"Backup {nome} salvato ({contati} file, {byte // 1024} KB).")
            except archivio_cloud.ArchivioErrore as e:
                st.error(f"Backup non riuscito: {e}")
    try:
        salvati = backup_dati.elenco_backup()
    except archivio_cloud.ArchivioErrore as e:
        st.error(str(e))
        return
    if not salvati:
        st.caption("Ancora nessun backup.")
        return
    for nome, byte in salvati:
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"📦 {nome} · {byte // 1024} KB")
        pronto = st.session_state.get("bk_pronto")
        if pronto and pronto[0] == nome:
            c2.download_button("💾 Scarica", pronto[1], file_name=nome, mime="application/zip",
                               key=f"bk_scarica_{nome}", use_container_width=True)
        elif c2.button("⬇️ Prepara", key=f"bk_prepara_{nome}", use_container_width=True):
            try:
                st.session_state["bk_pronto"] = (nome, backup_dati.scarica_backup(nome))
            except archivio_cloud.ArchivioErrore as e:
                st.error(str(e))
            st.rerun()


def render_registro_e_backup():
    st.subheader("🗂️ Registro e backup")
    _render_registro()
    st.divider()
    _render_backup()
