"""📊 Statistiche → 🏆 Classifica: la classifica del girone di ogni squadra della società, presa da Tuttocampo
(dal link) o dalla pagina della LND (copiando e incollando il testo)."""
import pandas as pd
import streamlit as st

from classifica import ClassificaErrore, classifiche, leggi, link_attuale, nome_fonte, nostra_riga, salva, scarica
from stagioni import gruppi_correnti

COLONNE = {"pos": "#", "squadra": "Squadra", "pt": "Pt", "g": "G", "v": "V", "n": "N", "p": "P", "gf": "GF",
           "gs": "GS", "dr": "DR"}


def _tabella(righe, nome_societa):
    nostra = nostra_riga(righe, nome_societa)
    chiavi = [k for k in COLONNE if any(r.get(k) is not None for r in righe)]  # la LND non dà GF e GS
    df = pd.DataFrame([{COLONNE[k]: r.get(k) for k in chiavi} for r in righe])
    stile = df.style.apply(lambda riga: ["font-weight:700;background-color:rgba(30,90,200,.12)"
                                         if riga["#"] == nostra else "" for _ in riga], axis=1)
    st.dataframe(stile, hide_index=True, use_container_width=True, height=min(35 * len(righe) + 40, 700))


def _aggiorna(gruppo, stagione, salvata):
    def fatto(righe, fonte):
        salva(gruppo, stagione, righe, link_attuale(fonte))
        st.session_state["cl_messaggio"] = f"Classifica di {gruppo} aggiornata: {len(righe)} squadre."
        st.session_state.pop(f"cl_testo_{gruppo}", None)
        st.rerun()

    link = st.text_input("Link della classifica (Tuttocampo o LND)", value=(salvata or {}).get("fonte", ""),
                         key=f"cl_link_{gruppo}", placeholder="https://www.tuttocampo.it/.../Classifica",
                         help="Con il link salvato la classifica si aggiorna da sola due volte al giorno. "
                              "La giornata eventualmente scritta nel link viene tolta, così si legge sempre l'ultima.")
    lnd = nome_fonte(link) == "LND"
    if nome_fonte(link) and link_attuale(link) != (salvata or {}).get("fonte"):
        if st.button("💾 Salva il link: la classifica si aggiorna da sola", key=f"cl_salva_link_{gruppo}",
                     type="primary"):
            salva(gruppo, stagione, (salvata or {}).get("righe") or [], link_attuale(link))
            st.session_state["cl_messaggio"] = ("Link salvato: la classifica arriva con il prossimo aggiornamento "
                                                "automatico (ogni mattina e ogni sera).")
            st.rerun()
    if not lnd and st.button("🔄 Leggi da Tuttocampo", key=f"cl_leggi_{gruppo}", type="primary",
                             disabled=not link.strip()):
        with st.spinner("Leggo la pagina..."):
            try:
                fatto(leggi(scarica(link)), link.strip())
            except ClassificaErrore as e:
                st.session_state[f"cl_errore_{gruppo}"] = str(e)
    if st.session_state.get(f"cl_errore_{gruppo}"):
        st.warning(st.session_state[f"cl_errore_{gruppo}"])
    with st.expander("📋 Per averla subito: copia e incolla la pagina" if lnd
                     else "📋 Se la lettura automatica non va: copia e incolla",
                     expanded=bool(st.session_state.get(f"cl_errore_{gruppo}"))):
        st.caption(f"Apri la classifica su {'gare.lnd.it' if lnd else 'Tuttocampo'}, seleziona tutta la pagina "
                   "(Ctrl+A, sul telefono \"Seleziona tutto\"), copia e incolla qui sotto.")
        testo = st.text_area("Testo della pagina", key=f"cl_testo_{gruppo}", height=150)
        if st.button("Leggi il testo incollato", key=f"cl_leggi_testo_{gruppo}", disabled=not testo.strip()):
            try:
                st.session_state.pop(f"cl_errore_{gruppo}", None)
                fatto(leggi(testo), link.strip() or (salvata or {}).get("fonte", ""))
            except ClassificaErrore as e:
                st.error(str(e))


def render_classifica(nome_societa=""):
    stagione, gruppi = gruppi_correnti()
    nomi = [g["gruppo"] for g in gruppi]
    if not nomi:
        st.info("Prima crea le squadre in ⚙️ Opzioni → 🏆 Campionati.")
        return
    if st.session_state.get("cl_messaggio"):
        st.success(st.session_state.pop("cl_messaggio"))
    gruppo = st.selectbox(f"👥 Squadra ({stagione})", nomi, key="cl_gruppo") if len(nomi) > 1 else nomi[0]
    salvata = classifiche().get(gruppo)
    if salvata and salvata.get("stagione") == stagione and salvata.get("righe"):
        giorno, _, ora = salvata["aggiornata"].partition(" ")
        st.caption(f"Aggiornata il {giorno[8:10]}/{giorno[5:7]}/{giorno[:4]} alle {ora}"
                   + (f" · [fonte]({salvata['fonte']})" if salvata.get("fonte") else "")
                   + (f" · dati {nome_fonte(salvata.get('fonte'))}" if nome_fonte(salvata.get("fonte")) else "")
                   + (" · si aggiorna da sola mattina e sera" if nome_fonte(salvata.get("fonte")) else "")
                   + " · fa fede il Comunicato Ufficiale.")
        _tabella(salvata["righe"], nome_societa)
        with st.expander("🔄 Aggiorna la classifica"):
            _aggiorna(gruppo, stagione, salvata)
    elif salvata and nome_fonte(salvata.get("fonte")):
        st.info(f"Link salvato per {gruppo}: la classifica arriva con il prossimo aggiornamento automatico "
                "(ogni mattina e ogni sera). Per averla subito copia e incolla la pagina.")
        _aggiorna(gruppo, stagione, salvata)
    else:
        st.info(f"Nessuna classifica per {gruppo}: incolla il link della LND (gare.lnd.it) o di Tuttocampo e "
                "salvalo.")
        _aggiorna(gruppo, stagione, salvata)
