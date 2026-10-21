"""La squadra scelta in 📊 Statistiche resta la stessa passando da una scheda all'altra (Giocatori, Classifica,
Risultati, Avversari): ogni scheda ha la sua tendina, ma tutte partono dall'ultima squadra scelta."""
import streamlit as st

COMUNE = "squadra_statistiche"


def _ricorda(chiave):
    if st.session_state.get(chiave) not in (None, "Tutte"):
        st.session_state[COMUNE] = st.session_state[chiave]


def scegli(etichetta, nomi, chiave, prima=None, contenitore=st):
    """Una tendina della squadra che parte dall'ultima squadra scelta in un'altra scheda."""
    comune = st.session_state.get(COMUNE)
    if comune in nomi:
        st.session_state[chiave] = comune
    elif st.session_state.get(chiave) not in nomi:
        st.session_state[chiave] = prima if prima in nomi else nomi[0]
    return contenitore.selectbox(etichetta, nomi, key=chiave, on_change=_ricorda, args=(chiave,))
