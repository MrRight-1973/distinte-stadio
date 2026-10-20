"""🏃 Allenamenti: l'allenatore segna chi c'era e vede le statistiche delle presenze.

Un allenatore vede solo i gruppi squadra assegnati in ⚙️ Opzioni → 👥 Utenti; segreteria e
amministratori li vedono tutti. I ragazzi sono quelli dell'👦 Anagrafica nel gruppo dell'anno.
"""
from datetime import date

import pandas as pd
import streamlit as st

from anagrafica import data_da_iso, elenco_ragazzi, nome_completo, ragazzi_del_gruppo
from presenze import STATI, elimina_allenamento, presenze_gruppo, salva_allenamento, statistiche
from stagioni import gruppi_correnti
from utenti import gruppi_utente

ETICHETTE = {"presente": "✅ Presente", "assente": "❌ Assente", "giustificato": "🟡 Giustificato"}
DA_ETICHETTA = {v: k for k, v in ETICHETTE.items()}


def _messaggio(tipo, testo):
    st.session_state["pres_messaggi"] = [(tipo, testo)]


def _inizio_stagione(stagione):
    """1° luglio del primo anno dell'anno sportivo (es. "2026/2027" -> 2026-07-01)."""
    try:
        return date(int(str(stagione)[:4]), 7, 1)
    except ValueError:
        return date(date.today().year, 1, 1)


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
        _statistiche(stagione, ragazzi, allenamenti)


def _segna(stagione, gruppo, ragazzi, allenamenti):
    if not ragazzi:
        st.info(f"Nessun ragazzo in 👦 Anagrafica nella squadra {gruppo} per il {stagione}.")
        return
    oggi = date.today()
    giorno = st.date_input("📅 Allenamento del", value=oggi, max_value=oggi, format="DD/MM/YYYY", key="pres_giorno")
    chiave = giorno.strftime("%Y-%m-%d")
    gia = allenamenti.get(chiave)
    if gia:
        st.caption("Allenamento già segnato: puoi correggerlo e salvare di nuovo.")
    else:
        st.caption("Sono tutti presenti: cambia solo chi è mancato.")
    righe = [{"Ragazzo": nome_completo(r),
              "Presenza": ETICHETTE[(gia or {}).get(r["id"], "presente" if not gia else "assente")]}
             for r in ragazzi]
    n = st.session_state.get("pres_n", 0)
    tabella = st.data_editor(
        pd.DataFrame(righe), hide_index=True, use_container_width=True, key=f"pres_tab_{gruppo}_{chiave}_{n}",
        disabled=["Ragazzo"], height=min(35 * len(righe) + 40, 640),
        column_config={"Presenza": st.column_config.SelectboxColumn(options=list(ETICHETTE.values()), required=True)})
    stati = [DA_ETICHETTA.get(v, "presente") for v in tabella["Presenza"]]
    st.caption(f"✅ {stati.count('presente')} · ❌ {stati.count('assente')} · 🟡 {stati.count('giustificato')}")
    c1, c2 = st.columns(2)
    if c1.button("💾 Salva presenze", type="primary", use_container_width=True, key="pres_salva"):
        salva_allenamento(stagione, gruppo, chiave, {r["id"]: s for r, s in zip(ragazzi, stati)})
        st.session_state["pres_n"] = n + 1
        _messaggio("success", f"Presenze del {giorno.strftime('%d/%m/%Y')} salvate: {stati.count('presente')} "
                              f"presenti su {len(stati)}.")
        st.rerun()
    if gia and c2.button("🗑️ Togli questo allenamento", use_container_width=True, key="pres_elimina"):
        elimina_allenamento(stagione, gruppo, chiave)
        st.session_state["pres_n"] = n + 1
        _messaggio("success", f"Allenamento del {giorno.strftime('%d/%m/%Y')} tolto.")
        st.rerun()

    if allenamenti:
        with st.expander(f"🗓️ Allenamenti segnati ({len(allenamenti)})"):
            for g in sorted(allenamenti, reverse=True)[:30]:
                segnati = allenamenti[g]
                presenti = sum(1 for s in segnati.values() if s == "presente")
                st.markdown(f"**{data_da_iso(g).strftime('%d/%m/%Y')}** · {presenti}/{len(segnati)} presenti")


def _statistiche(stagione, ragazzi, allenamenti):
    if not allenamenti:
        st.info("Ancora nessun allenamento segnato per questa squadra.")
        return
    c1, c2 = st.columns(2)
    dal = c1.date_input("Dal", value=_inizio_stagione(stagione), format="DD/MM/YYYY", key="pres_dal")
    al = c2.date_input("Al", value=date.today(), format="DD/MM/YYYY", key="pres_al")
    dal_iso, al_iso = dal.strftime("%Y-%m-%d"), al.strftime("%Y-%m-%d")
    nel_periodo = [g for g in allenamenti if dal_iso <= g <= al_iso]
    conti = statistiche(allenamenti, dal_iso, al_iso)
    if not nel_periodo:
        st.info("Nessun allenamento in questo periodo.")
        return
    nomi = {r["id"]: nome_completo(r) for r in elenco_ragazzi()}
    in_rosa = {r["id"] for r in ragazzi}
    righe = [{"Ragazzo": nomi.get(i, "(scheda eliminata)") + ("" if i in in_rosa else " ·  non più in squadra"),
              "Presenze %": v["percentuale"], "Presente": v["presente"], "Assente": v["assente"],
              "Giustificato": v["giustificato"], "Allenamenti": v["segnati"]} for i, v in conti.items()]
    righe.sort(key=lambda r: (-r["Presenze %"], r["Ragazzo"]))
    totale = sum(v["presente"] for v in conti.values())
    segnati = sum(v["segnati"] for v in conti.values())
    m1, m2 = st.columns(2)
    m1.metric("Allenamenti", len(nel_periodo))
    m2.metric("Presenza media", f"{round(100 * totale / segnati) if segnati else 0}%")
    st.dataframe(pd.DataFrame(righe), hide_index=True, use_container_width=True,
                 height=min(35 * len(righe) + 40, 640),
                 column_config={"Presenze %": st.column_config.ProgressColumn(format="%d%%", min_value=0,
                                                                               max_value=100)})
    st.caption("La percentuale è sugli allenamenti in cui il ragazzo era in squadra e quindi segnato.")
