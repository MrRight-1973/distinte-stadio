"""Rose delle squadre: ⚙️ Opzioni → 👕 Rose, e nella Distinta la lista preparata spuntando i convocati."""
import pandas as pd
import streamlit as st

from anagrafica import rosa_da_anagrafica
from rose import griglia_convocati, pulisci_rosa, rosa_squadra, salva_rosa, ultima_lista
from squadra_manager import NUM_RIGHE
from stagioni import gruppi_correnti

COLONNE_ROSA = {"giocatore": "Giocatore", "anno": "Anno", "numero": "N° abituale"}


def _tabella_rosa(rosa):
    df = pd.DataFrame(rosa or [{"giocatore": "", "anno": "", "numero": None}], columns=list(COLONNE_ROSA))
    df["numero"] = pd.array(df["numero"], dtype="Int64")
    return df.rename(columns=COLONNE_ROSA)


def _da_tabella(df):
    df = df.rename(columns={v: k for k, v in COLONNE_ROSA.items()})
    return [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in df.to_dict("records")]


def render_opzioni_rose(nome_societa, partite):
    """partite: funzione che restituisce le partite (archivio e aperta), per riempire la rosa dall'ultima."""
    st.subheader("👕 Rose delle squadre")
    for tipo, testo in st.session_state.pop("rose_messaggi", []):
        getattr(st, tipo)(testo)
    stagione, gruppi = gruppi_correnti()
    if not gruppi:
        st.info("Prima imposta squadre e competizioni dell'anno in ⚙️ Opzioni → 🏆 Campionati: ogni gruppo squadra ha la sua rosa.")
        return
    st.caption("I giocatori di ogni squadra, una volta per tutte: nella Distinta si spuntano i convocati e, "
               "quando la lista si legge dalla foto, i nomi vengono scritti come qui.")
    competizioni = {g["gruppo"]: g["competizioni"] for g in gruppi}
    gruppo = st.selectbox(f"Gruppo squadra ({stagione})", list(competizioni), key="rose_gruppo",
                              help="La stessa rosa vale per tutte le competizioni del gruppo")
    st.caption("Competizioni: " + " · ".join(competizioni[gruppo]))
    rosa = rosa_squadra(stagione, gruppo)
    if rosa_da_anagrafica(stagione, gruppo):
        st.info(f"La rosa di {gruppo} viene dall'anagrafica ({len(rosa)} ragazzi): si cambia nella sezione "
                "👦 Anagrafica, assegnando i ragazzi alla squadra.")
        st.dataframe(_tabella_rosa(rosa), hide_index=True, use_container_width=True)
        return
    n = st.session_state.get("rose_n", 0)

    with st.popover("📥 Riempi dall'ultima partita di questa squadra", use_container_width=True):
        ultima = ultima_lista(partite(), competizioni[gruppo], nome_societa)
        if not ultima:
            st.caption("Nessuna partita di questo gruppo con la distinta collegata.")
        else:
            st.caption(f"Aggiunge alla rosa i {len(ultima)} giocatori dell'ultima distinta (chi c'è già resta).")
            if st.button("📥 Aggiungi", use_container_width=True, key="rose_aggiungi"):
                nuova = salva_rosa(stagione, gruppo, rosa + ultima)
                st.session_state["rose_n"] = n + 1
                st.session_state["rose_messaggi"] = [("success", f"Rosa di {gruppo}: {len(nuova)} giocatori.")]
                st.rerun()

    tabella = st.data_editor(
        _tabella_rosa(rosa), num_rows="dynamic", hide_index=True, use_container_width=True,
        key=f"rose_tabella_{stagione}_{gruppo}_{n}",
        column_config={"Giocatore": st.column_config.TextColumn(max_chars=40, width="large"),
                       "Anno": st.column_config.TextColumn(max_chars=4),
                       "N° abituale": st.column_config.NumberColumn(min_value=1, max_value=99, step=1)})
    nuova = pulisci_rosa(_da_tabella(tabella))
    if nuova != rosa:
        if st.button("💾 Salva la rosa", type="primary", use_container_width=True):
            salva_rosa(stagione, gruppo, nuova)
            st.session_state["rose_n"] = n + 1
            st.session_state["rose_messaggi"] = [("success", f"Rosa di {gruppo} salvata: {len(nuova)} giocatori.")]
            st.rerun()
        st.caption("Modifiche non ancora salvate.")
    else:
        st.caption(f"{len(rosa)} giocatori. Con ➕ in fondo alla tabella se ne aggiunge uno; per toglierlo selezionalo e 🗑️.")


def render_prepara_da_rosa():
    """Nella Distinta: la nostra lista dalla rosa, spuntando convocati e titolari.
    Restituisce (lato, griglia, campionato) quando si preme «Metti nella distinta», altrimenti None."""
    stagione, gruppi = gruppi_correnti()
    con_rosa = {g["gruppo"]: g["competizioni"] for g in gruppi if rosa_squadra(stagione, g["gruppo"])}
    if not con_rosa:
        return None
    with st.expander("👕 Prepara la nostra lista dalla rosa (senza scansione)"):
        c1, c2, c3 = st.columns([2, 3, 2])
        gruppo = c1.selectbox("Squadra", list(con_rosa), key="conv_gruppo")
        campionato = c2.selectbox("Competizione", con_rosa[gruppo], key=f"conv_campionato_{gruppo}")
        lato = c3.radio("Giochiamo", ["casa", "ospite"], horizontal=True, key="conv_lato",
                        format_func={"casa": "🏠 In casa", "ospite": "🚌 In trasferta"}.get)
        rosa = rosa_squadra(stagione, gruppo)
        df = pd.DataFrame([{"Conv.": False, "Tit.": False, "N°": g.get("numero"), "Giocatore": g["giocatore"],
                            "Anno": g.get("anno") or ""} for g in rosa])
        df["N°"] = pd.array(df["N°"], dtype="Int64")
        scelta = st.data_editor(df, hide_index=True, use_container_width=True, key=f"conv_tabella_{gruppo}",
                                disabled=["Giocatore", "Anno"],
                                column_config={"Conv.": st.column_config.CheckboxColumn(help="Convocato"),
                                               "Tit.": st.column_config.CheckboxColumn(help="Titolare (gli 11 in alto)"),
                                               "N°": st.column_config.NumberColumn(min_value=1, max_value=99, step=1)})
        convocati = scelta[scelta["Conv."] | scelta["Tit."]]
        titolari = convocati[convocati["Tit."]]
        st.caption(f"Convocati {len(convocati)} su {NUM_RIGHE} · titolari {len(titolari)} su 11. "
                   "Il numero si può cambiare qui per questa partita.")
        numeri = [int(x) for x in convocati["N°"].dropna()]
        problemi = []
        if len(convocati) > NUM_RIGHE:
            problemi.append(f"Al massimo {NUM_RIGHE} convocati.")
        if len(numeri) != len(set(numeri)):
            problemi.append("Due giocatori hanno lo stesso numero.")
        for p in problemi:
            st.error(p)
        if len(titolari) not in (0, 11) and not problemi:
            st.warning(f"Titolari spuntati: {len(titolari)} (di solito 11). Puoi comunque proseguire.")
        if st.button("✅ Metti nella distinta", type="primary", use_container_width=True,
                     disabled=bool(problemi) or convocati.empty):
            def giocatori(righe):
                return [{"giocatore": r["Giocatore"], "anno": r["Anno"],
                         "numero": None if pd.isna(r["N°"]) else int(r["N°"])} for _, r in righe.iterrows()]
            if titolari.empty:  # nessun titolare spuntato: l'ordine è quello dei numeri
                griglia = griglia_convocati(giocatori(convocati), [])
            else:
                griglia = griglia_convocati(giocatori(titolari), giocatori(convocati[~convocati["Tit."]]))
            return lato, griglia, campionato
    return None
