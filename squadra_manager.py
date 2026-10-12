import pandas as pd
import streamlit as st

NUM_RIGHE = 20
PREFISSI_WIDGET = ("ed_", "n_", "a_")


def griglia_vuota():
    return pd.DataFrame(
        [{"N°": i, "GIOCATORE": "", "ANNO": ""} for i in range(1, NUM_RIGHE + 1)]
    ).set_index("N°")


def pulisci_widget_squadra(chiave_griglia):
    """Elimina lo stato dei widget (editor, nome, allenatore) di una squadra.

    Necessario per evitare che modifiche vecchie vengano riapplicate ai dati
    nuovi e che nome/allenatore restino quelli della scansione precedente.
    """
    for prefisso in PREFISSI_WIDGET:
        st.session_state.pop(f"{prefisso}{chiave_griglia}", None)


def reset_stato_squadra(chiave_griglia):
    st.session_state[chiave_griglia] = griglia_vuota()
    pulisci_widget_squadra(chiave_griglia)


def _testo(valore):
    """Converte None/NaN (celle svuotate nel data_editor) in stringa vuota."""
    if valore is None or pd.isna(valore):
        return ""
    return str(valore).strip()


def giocatori_da_griglia(chiave_griglia):
    """Restituisce la lista di giocatori pronta per JSON/PDF, senza None."""
    df = st.session_state[chiave_griglia].reset_index()
    return [
        {
            "N°": int(r["N°"]),
            "GIOCATORE": _testo(r["GIOCATORE"]),
            "ANNO": _testo(r["ANNO"]),
        }
        for _, r in df.iterrows()
    ]


def applica_shift(chiave_griglia, direzione):
    """Callback: sposta le righe verso il basso o l'alto dalla riga scelta."""
    riga = st.session_state[f"sel_{chiave_griglia}"]
    df = st.session_state[chiave_griglia].copy().reset_index()
    idx = riga - 1
    riga_vuota = pd.DataFrame([{"N°": 0, "GIOCATORE": "", "ANNO": ""}])

    if direzione == "giù":
        if _testo(df.iloc[NUM_RIGHE - 1]["GIOCATORE"]):
            st.session_state[f"avviso_{chiave_griglia}"] = (
                "Attenzione: la riga 20 era compilata ed è stata eliminata dallo spostamento."
            )
        df_nuovo = pd.concat([df.iloc[:idx], riga_vuota, df.iloc[idx:NUM_RIGHE - 1]])
    else:
        df_nuovo = pd.concat([df.iloc[:idx], df.iloc[idx + 1:], riga_vuota])

    df_nuovo = df_nuovo.reset_index(drop=True)
    df_nuovo["N°"] = range(1, NUM_RIGHE + 1)
    st.session_state[chiave_griglia] = df_nuovo.set_index("N°")
    # Le modifiche pendenti dell'editor non vanno riapplicate ai dati spostati
    st.session_state.pop(f"ed_{chiave_griglia}", None)


def _importa_csv(chiave_griglia):
    """Ricarica la lista da un CSV scaricato in precedenza (icona ⬇️ sopra la tabella)."""
    from import_csv import CsvErrore, griglia_da_csv

    n = st.session_state.setdefault(f"csv_n_{chiave_griglia}", 0)
    with st.popover("📥 Carica lista da CSV", use_container_width=True):
        st.caption("Il CSV scaricato dall'icona ⬇️ della tabella (colonne N°, GIOCATORE, ANNO). "
                   "Sostituisce la lista di questa squadra.")
        f = st.file_uploader("CSV della lista", type=["csv"], key=f"csv_{chiave_griglia}_{n}",
                             label_visibility="collapsed")
    if f is None:
        return
    try:
        st.session_state[chiave_griglia] = griglia_da_csv(f.getvalue())
    except CsvErrore as e:
        st.error(str(e))
        return
    st.session_state.pop(f"ed_{chiave_griglia}", None)  # le modifiche dell'editor non vanno riapplicate
    st.session_state[f"csv_n_{chiave_griglia}"] = n + 1  # uploader nuovo e vuoto: il file non si riapplica
    st.rerun()


def render_colonna_squadra(label_titolo, chiave_griglia, default_all, default_nome=""):
    """Rende la colonna squadra; nome società e allenatore sono precompilati dalla scansione
    ma restano modificabili dall'utente."""
    st.subheader(label_titolo)

    nome = st.text_input(f"Nome Società {label_titolo}", value=default_nome, key=f"n_{chiave_griglia}")
    alln = st.text_input(f"Allenatore {label_titolo}", value=default_all, key=f"a_{chiave_griglia}")

    st.session_state[chiave_griglia] = st.data_editor(
        st.session_state[chiave_griglia],
        key=f"ed_{chiave_griglia}",
        use_container_width=True,
        column_config={
            "GIOCATORE": st.column_config.TextColumn("GIOCATORE", max_chars=40),
            "ANNO": st.column_config.TextColumn("ANNO", max_chars=4),
        },
    )

    _importa_csv(chiave_griglia)

    avviso = st.session_state.pop(f"avviso_{chiave_griglia}", None)
    if avviso:
        st.warning(avviso)

    c1, c2 = st.columns(2)
    with c1:
        st.selectbox("🎯 Riga", options=list(range(1, NUM_RIGHE + 1)), index=12, key=f"sel_{chiave_griglia}")
    with c2:
        st.markdown("<div style='padding-top: 24px;'></div>", unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        with b1:
            st.button("⬇️", key=f"down_{chiave_griglia}", use_container_width=True,
                      on_click=applica_shift, args=(chiave_griglia, "giù"))
        with b2:
            st.button("⬆️", key=f"up_{chiave_griglia}", use_container_width=True,
                      on_click=applica_shift, args=(chiave_griglia, "su"))

    return {"squadra": nome, "allenatore": alln}
