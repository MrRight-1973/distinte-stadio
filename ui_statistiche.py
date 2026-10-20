"""Sezione "Statistiche": minuti giocati, gol, assist e cartellini dei giocatori, dalle partite con cronaca."""
from datetime import datetime

import pandas as pd
import streamlit as st

import archivio_cloud
from anagrafica import calciatori, elenco_ragazzi, trova_per_nome
from cronaca_manager import carica_cronaca
from giornata import etichetta_giornata
from presenze import allenato_complessivo
from stagioni import gruppo_di, impostazioni_stagioni, stagione_partita
from statistiche import chiave_squadra, risultati_squadra, squadre_presenti, statistiche_squadra
from statistiche_pdf import PARTI, genera_pdf_statistiche

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
    partite.pop(aperta.get("archivio_id"), None)  # partita riaperta dall'archivio: conta la copia in Cronaca
    partite[aperta.get("id")] = aperta
    return [p for p in partite.values() if p]


def _allenato(stagioni, gruppi, riepilogo):
    """{nome del giocatore come nelle distinte: % di allenamenti svolti}, dai dati di 🏃 Allenamenti."""
    totali = allenato_complessivo(stagioni, gruppi)
    if not totali:
        return {}
    ragazzi = calciatori(elenco_ragazzi())
    risultato = {}
    for r in riepilogo:
        scheda = trova_per_nome(r["giocatore"], "", ragazzi, set(totali))
        if scheda and totali.get(scheda["id"], (0, 0))[1]:
            svolti, segnati = totali[scheda["id"]]
            risultato[r["giocatore"]] = round(100 * svolti / segnati)
    return risultato


def render_statistiche(nome_societa=""):
    partite = _partite()
    squadre = squadre_presenti(partite)
    if not squadre:
        st.info("Non ci sono ancora partite con la distinta collegata alla cronaca: le statistiche si riempiono "
                "partita dopo partita.")
        return

    # Solo la nostra società: quella nei secrets (NOME_SOCIETA) o, se manca, quella presente in più partite
    nostra = chiave_squadra(nome_societa) if nome_societa else ""
    chiave = nostra if any(k == nostra for k, _ in squadre) else squadre[0][0]
    st.caption(f"Giocatori di {dict(squadre)[chiave]}")
    # Anno sportivo, gruppo squadra e competizione: ogni squadra della società (prima squadra, giovanili)
    # ha le sue statistiche, sommando campionato e coppa oppure una competizione sola
    corrente = impostazioni_stagioni()["corrente"]
    anni = sorted({stagione_partita(p.get("partita")) for p in partite} - {""}, reverse=True)
    c1, c2, c3 = st.columns(3)
    scelte_anni = ["Tutti gli anni"] + anni
    anno = c1.selectbox("📅 Anno sportivo", scelte_anni, key="stat_anno",
                        index=scelte_anni.index(corrente) if corrente in anni else 0)
    if anno != "Tutti gli anni":
        partite = [p for p in partite if stagione_partita(p.get("partita")) == anno]
    for p in partite:
        info = p.get("partita") or {}
        p["_gruppo"] = gruppo_di(info.get("campionato"), stagione_partita(info))
    gruppi = sorted({p["_gruppo"] for p in partite} - {""})
    gruppo = c2.selectbox("👥 Squadra", ["Tutte"] + gruppi, key="stat_gruppo", index=1 if len(gruppi) == 1 else 0)
    if gruppo != "Tutte":
        partite = [p for p in partite if p["_gruppo"] == gruppo]
    campionati = sorted({(p.get("partita") or {}).get("campionato") or "" for p in partite} - {""})
    campionato = c3.selectbox("🏆 Competizione", ["Tutte"] + campionati, key=f"stat_campionato_{gruppo}",
                              index=1 if len(campionati) == 1 else 0)
    if campionato != "Tutte":
        partite = [p for p in partite if (p.get("partita") or {}).get("campionato") == campionato]
    # Per il titolo del PDF: es. "2026/27 · Prima Squadra · Coppa Veneto" (il gruppo non si ripete se è la competizione)
    filtro = tuple(x for x in dict.fromkeys((anno, gruppo, campionato)) if not x.startswith("Tutt"))

    riepilogo, per_partita = statistiche_squadra(partite, chiave)
    risultati = risultati_squadra(partite, chiave)
    if not per_partita:
        st.info("Nessuna partita giocata per questa squadra con i filtri scelti.")
        return

    fatti, subiti = sum(r["fatti"] for r in risultati), sum(r["subiti"] for r in risultati)
    m = st.columns(5)
    m[0].metric("Partite", len(per_partita))
    m[1].metric("⚽ Gol fatti", fatti)
    m[2].metric("🥅 Gol subiti", subiti)
    m[3].metric("🟨 Ammonizioni", sum(r["ammonizioni"] for r in riepilogo))
    m[4].metric("🟥 Espulsioni", sum(r["espulsioni"] for r in riepilogo))

    allenato = _allenato(anni if anno == "Tutti gli anni" else [anno], None if gruppo == "Tutte" else [gruppo],
                         riepilogo)
    for r in riepilogo:
        r["allenato"] = allenato.get(r["giocatore"])
    tabella = pd.DataFrame(riepilogo)
    tabella["media"] = [round(r["minuti"] / r["presenze"]) if r["presenze"] else 0 for r in riepilogo]
    colonne = {**COLONNE, **({"allenato": "🏃 Allenato %"} if allenato else {})}
    tabella = tabella[list(colonne)].rename(columns=colonne)
    if allenato:
        tabella["🏃 Allenato %"] = pd.array(tabella["🏃 Allenato %"], dtype="Int64")

    with st.expander(f"📅 Risultati: {fatti} gol fatti, {subiti} subiti"):
        st.dataframe(pd.DataFrame([{
            "Giornata": etichetta_giornata(r["giornata"]), "Data": r["data"], "Avversario": r["avversario"],
            "": "🏠 Casa" if r["in_casa"] else "🚌 Trasferta", "Fatti": r["fatti"], "Subiti": r["subiti"],
        } for r in reversed(risultati)]), hide_index=True, use_container_width=True)

    with st.expander(f"👥 Giocatori ({len(riepilogo)})"):
        st.dataframe(tabella, hide_index=True, use_container_width=True,
                     column_config={"🏃 Allenato %": st.column_config.NumberColumn(format="%d%%")})
        if allenato:
            st.caption("🏃 Allenato %: allenamenti svolti (C, P o D) su quelli segnati in 🏃 Allenamenti, "
                       "nello stesso anno e squadra. Vuoto se il giocatore non è in anagrafica.")
        st.download_button("⬇️ Scarica le statistiche (CSV)", tabella.to_csv(index=False, sep=";").encode("utf-8-sig"),
                           file_name="statistiche_giocatori.csv", mime="text/csv")

    cartellini = tabella[(tabella["🟨"] > 0) | (tabella["🟥"] > 0)].sort_values(["🟥", "🟨"], ascending=False)
    with st.expander(f"🟨 Cartellini ({len(cartellini)} giocatori)"):
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

    with st.expander("🖨️ Crea PDF delle statistiche"):
        scelte = [k for k, testo in PARTI.items() if st.checkbox(testo, value=k != "minuti", key=f"stat_pdf_{k}")]
        if st.button("🖨️ Crea PDF", type="primary", use_container_width=True, disabled=not scelte):
            st.session_state["stat_pdf"] = (filtro, scelte, genera_pdf_statistiche(
                dict(squadre)[chiave], " · ".join(filtro),
                riepilogo, per_partita, risultati, scelte))
        pronto = st.session_state.get("stat_pdf")
        if pronto and pronto[:2] == (filtro, scelte):  # cambiate le scelte: si ricrea
            st.download_button("⬇️ Scarica il PDF", pronto[2], mime="application/pdf",
                               file_name=f"Statistiche_{datetime.now():%Y-%m-%d}.pdf", use_container_width=True)

    st.caption("I titolari sono i primi 11 della distinta. I minuti si calcolano dalle sostituzioni e dalle "
               "espulsioni segnate in cronaca, sulla durata regolamentare: perché siano giusti, nelle note scegli "
               "sempre i giocatori dai menu. Contano le partite iniziate o con almeno una nota. Lo stesso giocatore "
               "scritto in modo diverso (accenti, doppie) si conta una volta sola.")
