"""🏃 Allenamenti: l'allenatore segna chi c'era e vede le statistiche delle presenze.

Un allenatore vede solo i gruppi squadra assegnati in ⚙️ Opzioni → 👥 Utenti; segreteria e
amministratori li vedono tutti. I ragazzi sono quelli dell'👦 Anagrafica nel gruppo dell'anno.
"""
from datetime import date

import pandas as pd
import streamlit as st

from anagrafica import data_da_iso, elenco_ragazzi, nome_completo, ragazzi_del_gruppo
from presenze import IN_CAMPO, STATI, elimina_allenamento, presenze_gruppo, salva_allenamento, sposta_allenamento, \
    statistiche
from stagioni import gruppi_correnti
from statistiche_pdf import SIGLE_PRESENZE, genera_pdf_presenze
from utenti import gruppi_utente

ETICHETTE = {"presente": "✅ Presente", "differenziato": "🔄 Differenziato", "infortunato": "🩹 Infortunato",
             "assente": "❌ Assente", "giustificato": "🟡 Giustificato"}
DA_ETICHETTA = {v: k for k, v in ETICHETTE.items()}
COLONNE_STATI = {"presente": "Presente", "differenziato": "Differenz.", "infortunato": "Infortunato",
                 "assente": "Assente", "giustificato": "Giustif."}


def _messaggio(tipo, testo):
    st.session_state["pres_messaggi"] = [(tipo, testo)]


def _inizio_stagione(stagione):
    """1° luglio del primo anno dell'anno sportivo (es. "2026/27" -> 2026-07-01)."""
    try:
        return date(int(str(stagione)[:4]), 7, 1)
    except ValueError:
        return date(date.today().year, 1, 1)


def _gg(giorno_iso):
    return data_da_iso(giorno_iso).strftime("%d/%m/%Y")


def _riassunto(segnati):
    return " · ".join(f"{ETICHETTE[s].split()[0]} {n}" for s in STATI
                      if (n := sum(1 for v in segnati.values() if v == s)))


def render_presenze(utente, ruolo):
    st.subheader("🏃 Presenze allenamenti")
    for tipo, testo in st.session_state.pop("pres_messaggi", []):
        getattr(st, tipo)(testo)

    stagione, gruppi = gruppi_correnti()
    nomi_gruppi = [g["gruppo"] for g in gruppi]
    staff = ruolo in ("admin", "segreteria")
    miei = nomi_gruppi if staff else [g for g in gruppi_utente(utente) if g in nomi_gruppi]
    if not miei:
        st.info("Nessuna squadra disponibile: " + ("crea i gruppi squadra in ⚙️ Opzioni → 🏆 Campionati."
                if staff else "chiedi all'amministratore di assegnartene una in ⚙️ Opzioni → 👥 Utenti."))
        return
    gruppo = st.selectbox(f"👥 Squadra ({stagione})", miei, key="pres_gruppo")
    ragazzi = ragazzi_del_gruppo(stagione, gruppo)
    allenamenti = presenze_gruppo(stagione, gruppo)

    segna, numeri = st.tabs(["✅ Segna presenze", "📈 Statistiche"])
    with segna:
        _segna(stagione, gruppo, ragazzi, allenamenti)
    with numeri:
        _statistiche(stagione, gruppo, ragazzi, allenamenti)


def _segna(stagione, gruppo, ragazzi, allenamenti):
    if not ragazzi:
        st.info(f"Nessun ragazzo in 👦 Anagrafica nella squadra {gruppo} per il {stagione}.")
        return
    if "pres_apri" in st.session_state:  # "✏️ Modifica" dall'elenco: il giorno va scelto prima del widget
        st.session_state["pres_giorno"] = st.session_state.pop("pres_apri")
    oggi = date.today()
    st.session_state.setdefault("pres_giorno", oggi)
    giorno = st.date_input("📅 Allenamento del", max_value=oggi, format="DD/MM/YYYY", key="pres_giorno")
    chiave = giorno.strftime("%Y-%m-%d")
    gia = allenamenti.get(chiave)
    n = st.session_state.get("pres_n", 0)
    nuovo_giorno = chiave
    if gia:
        st.info(f"✏️ Stai modificando l'allenamento del {_gg(chiave)}: cambia le presenze e salva.")
        sposta = st.date_input("Sposta a un altro giorno (se la data era sbagliata)", value=giorno, max_value=oggi,
                               format="DD/MM/YYYY", key=f"pres_sposta_{gruppo}_{chiave}_{n}")
        nuovo_giorno = sposta.strftime("%Y-%m-%d")
        if nuovo_giorno != chiave and nuovo_giorno in allenamenti:
            st.warning(f"Il {_gg(nuovo_giorno)} c'è già un allenamento: salvando verrà sostituito.")
    else:
        st.caption("Sono tutti presenti: cambia solo chi è mancato, infortunato o ha fatto differenziato.")
    righe = [{"Ragazzo": nome_completo(r),
              "Presenza": ETICHETTE[(gia or {}).get(r["id"], "presente" if not gia else "assente")]}
             for r in ragazzi]
    tabella = st.data_editor(
        pd.DataFrame(righe), hide_index=True, use_container_width=True, key=f"pres_tab_{gruppo}_{chiave}_{n}",
        disabled=["Ragazzo"], height=min(35 * len(righe) + 40, 640),
        column_config={"Presenza": st.column_config.SelectboxColumn(options=list(ETICHETTE.values()), required=True)})
    stati = [DA_ETICHETTA.get(v, "presente") for v in tabella["Presenza"]]
    segnati = {r["id"]: s for r, s in zip(ragazzi, stati)}
    st.caption(_riassunto(segnati))
    c1, c2 = st.columns(2)
    if c1.button("💾 Salva modifiche" if gia else "💾 Salva presenze", type="primary", use_container_width=True,
                 key="pres_salva"):
        if gia and nuovo_giorno != chiave:
            sposta_allenamento(stagione, gruppo, chiave, nuovo_giorno, segnati)
            st.session_state["pres_apri"] = data_da_iso(nuovo_giorno)
        else:
            salva_allenamento(stagione, gruppo, chiave, segnati)
        st.session_state["pres_n"] = n + 1
        in_campo = sum(1 for s in stati if s in IN_CAMPO)
        _messaggio("success", f"Presenze del {_gg(nuovo_giorno)} salvate: {in_campo} in campo su {len(stati)}.")
        st.rerun()
    if gia and c2.button("🗑️ Togli questo allenamento", use_container_width=True, key="pres_elimina"):
        elimina_allenamento(stagione, gruppo, chiave)
        st.session_state["pres_n"] = n + 1
        _messaggio("success", f"Allenamento del {_gg(chiave)} tolto.")
        st.rerun()

    if allenamenti:
        st.markdown(f"**🗓️ Allenamenti salvati ({len(allenamenti)})** · tocca per modificarlo")
        for g in sorted(allenamenti, reverse=True)[:40]:
            if st.button(f"✏️ {_gg(g)} · {_riassunto(allenamenti[g])}", key=f"pres_apri_{g}",
                         use_container_width=True, disabled=g == chiave):
                st.session_state["pres_apri"] = data_da_iso(g)
                st.rerun()


def _statistiche(stagione, gruppo, ragazzi, allenamenti):
    if not allenamenti:
        st.info("Ancora nessun allenamento segnato per questa squadra.")
        return
    c1, c2 = st.columns(2)
    dal = c1.date_input("Dal", value=_inizio_stagione(stagione), format="DD/MM/YYYY", key="pres_dal")
    al = c2.date_input("Al", value=date.today(), format="DD/MM/YYYY", key="pres_al")
    dal_iso, al_iso = dal.strftime("%Y-%m-%d"), al.strftime("%Y-%m-%d")
    nel_periodo = sorted(g for g in allenamenti if dal_iso <= g <= al_iso)
    if not nel_periodo:
        st.info("Nessun allenamento in questo periodo.")
        return
    conti = statistiche(allenamenti, dal_iso, al_iso)
    nomi = {r["id"]: nome_completo(r) for r in elenco_ragazzi()}
    in_rosa = {r["id"] for r in ragazzi}
    nome_di = {i: nomi.get(i, "(scheda eliminata)") + ("" if i in in_rosa else " · non più in squadra")
               for i in conti}
    righe = [{"Ragazzo": nome_di[i], "Presenze %": v["percentuale"],
              **{COLONNE_STATI[s]: v[s] for s in STATI}, "Allenamenti": v["segnati"]} for i, v in conti.items()]
    righe.sort(key=lambda r: (-r["Presenze %"], r["Ragazzo"]))
    in_campo = sum(v[s] for v in conti.values() for s in IN_CAMPO)
    segnati = sum(v["segnati"] for v in conti.values())
    m1, m2, m3 = st.columns(3)
    m1.metric("Allenamenti", len(nel_periodo))
    m2.metric("Presenza media", f"{round(100 * in_campo / segnati) if segnati else 0}%")
    m3.metric("Infortuni segnati", sum(v["infortunato"] for v in conti.values()))
    st.dataframe(pd.DataFrame(righe), hide_index=True, use_container_width=True,
                 height=min(35 * len(righe) + 40, 640),
                 column_config={"Presenze %": st.column_config.ProgressColumn(format="%d%%", min_value=0,
                                                                               max_value=100)})
    st.caption("La percentuale conta presenti e differenziati sugli allenamenti in cui il ragazzo era segnato.")

    periodo = f"dal {dal:%d/%m/%Y} al {al:%d/%m/%Y}"
    griglia = {nome_di[i]: [SIGLE_PRESENZE.get(allenamenti[g].get(i), "") for g in nel_periodo]
               for i in sorted(conti, key=lambda i: nome_di[i])}
    firma = (gruppo, dal_iso, al_iso, len(nel_periodo), segnati, in_campo)
    if st.button("🖨️ Prepara il PDF delle presenze", key="pres_pdf"):
        st.session_state["pres_pdf_pronto"] = (firma, genera_pdf_presenze(
            gruppo, stagione, periodo, righe, [_gg(g) for g in nel_periodo], griglia))
    pronto = st.session_state.get("pres_pdf_pronto")
    if pronto and pronto[0] == firma:
        st.download_button("⬇️ Scarica il PDF", pronto[1], mime="application/pdf", key="pres_pdf_scarica",
                           file_name=f"presenze_{gruppo.replace(' ', '_')}_{dal_iso}_{al_iso}.pdf")
