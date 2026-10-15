"""⚙️ Opzioni → 🏆 Campionati: anno sportivo in corso e campionati/categorie delle squadre della società."""
import pandas as pd
import streamlit as st

from stagioni import impostazioni_stagioni, salva_stagioni, stagione_di_oggi

COLONNA = "Campionato / categoria"


def _successiva(stagione):
    inizio = int(stagione[:4]) + 1
    return f"{inizio}/{(inizio + 1) % 100:02d}"


def render_opzioni_campionati():
    st.subheader("🏆 Anno sportivo e campionati")
    st.caption("I campionati dell'anno in corso si scelgono da un elenco nella Distinta (non si leggono più dalle "
               "foto): così ogni squadra della società ha il suo archivio e le sue statistiche.")
    for tipo, testo in st.session_state.pop("stagioni_messaggi", []):
        getattr(st, tipo)(testo)
    imp = impostazioni_stagioni()
    oggi = stagione_di_oggi()
    anni = sorted(set(imp["stagioni"]) | {imp["corrente"], oggi, _successiva(oggi)}, reverse=True)
    corrente = st.selectbox("📅 Anno sportivo in corso", anni, index=anni.index(imp["corrente"]), key="opz_stagione",
                            help="Vale per le nuove distinte; le partite già giocate restano nel loro anno")
    if corrente != imp["corrente"]:
        salva_stagioni(corrente, imp["stagioni"])
        st.session_state["stagioni_messaggi"] = [("success", f"Anno sportivo in corso: {corrente}.")]
        st.rerun()

    elenco = imp["stagioni"].get(corrente, [])
    precedenti = [a for a in sorted(imp["stagioni"], reverse=True) if a < corrente and imp["stagioni"][a]]
    if not elenco and precedenti and st.button(f"📋 Copia i campionati del {precedenti[0]}", use_container_width=True):
        salva_stagioni(corrente, {**imp["stagioni"], corrente: imp["stagioni"][precedenti[0]]})
        st.session_state["stagioni_n"] = st.session_state.get("stagioni_n", 0) + 1
        st.rerun()

    st.markdown(f"**Campionati {corrente}**: uno per riga (es. *Prima Categoria girone E*, *Under 17 Regionale "
                "girone B*). Con ➕ in fondo alla tabella se ne aggiunge uno.")
    tabella = st.data_editor(pd.DataFrame({COLONNA: elenco or [""]}), num_rows="dynamic", hide_index=True,
                             use_container_width=True, key=f"opz_campionati_{corrente}_{st.session_state.get('stagioni_n', 0)}",
                             column_config={COLONNA: st.column_config.TextColumn(required=False)})
    nuovi = [str(c).strip() for c in tabella[COLONNA].tolist() if c is not None and str(c).strip()]
    if nuovi != elenco:
        if st.button("💾 Salva i campionati", type="primary", use_container_width=True):
            salva_stagioni(corrente, {**imp["stagioni"], corrente: nuovi})
            st.session_state["stagioni_n"] = st.session_state.get("stagioni_n", 0) + 1
            st.session_state["stagioni_messaggi"] = [("success", f"Salvati {len(nuovi)} campionati per il {corrente}.")]
            st.rerun()
        st.caption("Modifiche non ancora salvate.")
