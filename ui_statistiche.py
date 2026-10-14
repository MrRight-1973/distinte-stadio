"""Sezione "Statistiche": minuti giocati, gol, assist e cartellini dei giocatori, dalle partite con cronaca."""
import pandas as pd
import streamlit as st

import archivio_cloud
from cronaca_manager import carica_cronaca
from statistiche import squadre_presenti, statistiche_squadra

COLONNE = {"giocatore": "Giocatore", "convocazioni": "Convocato", "presenze": "Presenze", "titolare": "Da titolare",
           "minuti": "Minuti", "media": "Min/partita", "gol": "⚽ Gol", "assist": "🅰️ Assist",
           "ammonizioni": "🟨", "espulsioni": "🟥"}


def _partite():
    """Tutte le partite: quelle archiviate e quella aperta."""
    partite = {}
    if archivio_cloud.attivo():
        try:
            partite.update(archivio_cloud.dati_partite())
        except archivio_cloud.ArchivioErrore as e:
            st.warning(f"Archivio online non raggiungibile, conto solo la partita aperta: {e}")
    aperta = carica_cronaca()
    partite[aperta.get("id")] = aperta
    return [p for p in partite.values() if p]


def render_statistiche():
    partite = _partite()
    squadre = squadre_presenti(partite)
    if not squadre:
        st.info("Non ci sono ancora partite con la distinta collegata alla cronaca: le statistiche si riempiono "
                "partita dopo partita.")
        return

    c1, c2 = st.columns(2)
    chiave = c1.selectbox("Squadra", [k for k, _ in squadre], format_func=dict(squadre).get, key="stat_squadra")
    campionati = sorted({(p.get("partita") or {}).get("campionato") or "" for p in partite} - {""})
    campionato = c2.selectbox("Campionato", ["Tutti"] + campionati, key="stat_campionato")
    if campionato != "Tutti":
        partite = [p for p in partite if (p.get("partita") or {}).get("campionato") == campionato]

    riepilogo, per_partita = statistiche_squadra(partite, chiave)
    if not per_partita:
        st.info("Nessuna partita giocata per questa squadra con i filtri scelti.")
        return

    m = st.columns(4)
    m[0].metric("Partite", len(per_partita))
    m[1].metric("Gol", sum(r["gol"] for r in riepilogo))
    m[2].metric("🟨 Ammonizioni", sum(r["ammonizioni"] for r in riepilogo))
    m[3].metric("🟥 Espulsioni", sum(r["espulsioni"] for r in riepilogo))

    tabella = pd.DataFrame(riepilogo)
    tabella["media"] = [round(r["minuti"] / r["presenze"]) if r["presenze"] else 0 for r in riepilogo]
    tabella = tabella[list(COLONNE)].rename(columns=COLONNE)
    st.markdown("**👥 Giocatori**")
    st.dataframe(tabella, hide_index=True, use_container_width=True)
    st.download_button("⬇️ Scarica le statistiche (CSV)", tabella.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       file_name="statistiche_giocatori.csv", mime="text/csv")

    cartellini = tabella[(tabella["🟨"] > 0) | (tabella["🟥"] > 0)].sort_values(["🟥", "🟨"], ascending=False)
    with st.expander(f"🟨 Cartellini ({len(cartellini)} giocatori)", expanded=False):
        if cartellini.empty:
            st.caption("Nessun cartellino.")
        else:
            st.dataframe(cartellini[["Giocatore", "🟨", "🟥", "Presenze"]], hide_index=True, use_container_width=True)

    with st.expander("⏱️ Minuti partita per partita"):
        corte = [e.split(" · ")[0] for e, _ in per_partita]  # "3ª giornata" o la data
        intestazioni = corte if len(set(corte)) == len(corte) else [e for e, _ in per_partita]
        griglia = pd.DataFrame({t: minuti for t, (_, minuti) in zip(intestazioni, per_partita)})
        griglia = griglia.reindex([r["giocatore"] for r in riepilogo]).fillna(0).astype(int)
        st.dataframe(griglia, use_container_width=True)

    st.caption("I titolari sono i primi 11 della distinta. I minuti si calcolano dalle sostituzioni e dalle "
               "espulsioni segnate in cronaca, sulla durata regolamentare: perché siano giusti, nelle note scegli "
               "sempre i giocatori dai menu. Contano le partite iniziate o con almeno una nota.")
