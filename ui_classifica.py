"""📊 Statistiche → 🏆 Classifica: la classifica del girone di ogni squadra della società, letta in automatico
dalla pagina della LND (il link si imposta in ⚙️ Opzioni → 🌐 Dati LND)."""
import pandas as pd
import streamlit as st

from classifica import classifiche, nome_fonte, nostra_riga
from stagioni import gruppi_correnti

COLONNE = {"pos": "#", "squadra": "Squadra", "pt": "Pt", "g": "G", "v": "V", "n": "N", "p": "P", "gf": "GF",
           "gs": "GS", "dr": "DR"}


def _tabella(righe, nome_societa):
    nostra = nostra_riga(righe, nome_societa)
    chiavi = [k for k in COLONNE if any(r.get(k) is not None for r in righe)]  # la LND non dà GF e GS
    df = pd.DataFrame([{COLONNE[k]: r.get(k) for k in chiavi} for r in righe])
    stile = df.style.apply(lambda riga: ["font-weight:700;background-color:rgba(30,90,200,.12)"
                                         if riga["#"] == nostra else "" for _ in riga], axis=1)
    st.dataframe(stile, hide_index=True, width="stretch", height=min(35 * len(righe) + 40, 700))


def render_classifica(nome_societa=""):
    stagione, gruppi = gruppi_correnti()
    nomi = [g["gruppo"] for g in gruppi]
    if not nomi:
        st.info("Prima crea le squadre in ⚙️ Opzioni → 🏆 Campionati.")
        return
    gruppo = st.selectbox(f"👥 Squadra ({stagione})", nomi, key="cl_gruppo") if len(nomi) > 1 else nomi[0]
    salvata = classifiche().get(gruppo)
    if salvata and salvata.get("stagione") == stagione and salvata.get("righe"):
        giorno, _, ora = salvata["aggiornata"].partition(" ")
        st.caption(f"Aggiornata il {giorno[8:10]}/{giorno[5:7]}/{giorno[:4]} alle {ora}"
                   + (f" · [fonte]({salvata['fonte']})" if salvata.get("fonte") else "")
                   + (f" · dati {nome_fonte(salvata.get('fonte'))}" if nome_fonte(salvata.get("fonte")) else "")
                   + " · fa fede il Comunicato Ufficiale.")
        _tabella(salvata["righe"], nome_societa)
    elif salvata and nome_fonte(salvata.get("fonte")):
        st.info(f"Link salvato per {gruppo}: la classifica arriva con il prossimo aggiornamento.")
    else:
        st.info(f"Nessuna classifica per {gruppo}: imposta il link della LND in ⚙️ Opzioni → 🌐 Dati LND.")
