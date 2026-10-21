"""📊 Statistiche → 🏆 Classifica: la classifica del girone di ogni squadra della società, letta in automatico
dalla pagina della LND (il link si imposta in ⚙️ Opzioni → 🌐 Dati LND)."""
import altair as alt
import pandas as pd
import streamlit as st

import girone
import loghi
from classifica import classifiche, nome_fonte, nostra_riga
from scelta_squadra import scegli
from stagioni import gruppi_correnti

COLONNE = {"pos": "#", "squadra": "Squadra", "pt": "Pt", "g": "G", "v": "V", "n": "N", "p": "P", "gf": "GF",
           "gs": "GS", "dr": "DR"}


def _tabella(righe, nome_societa):
    nostra = nostra_riga(righe, nome_societa)
    chiavi = [k for k in COLONNE if any(r.get(k) is not None for r in righe)]  # la LND non dà GF e GS
    stemmi = loghi.tutti()
    con_stemmi = any(loghi.di(r["squadra"], stemmi) for r in righe)
    df = pd.DataFrame([{COLONNE["pos"]: r.get("pos"), **({"Stemma": loghi.di(r["squadra"], stemmi) or None}
                                                          if con_stemmi else {}),
                        **{COLONNE[k]: r.get(k) for k in chiavi if k != "pos"}} for r in righe])
    stile = df.style.apply(lambda riga: ["font-weight:700;background-color:rgba(30,90,200,.12)"
                                         if riga["#"] == nostra else "" for _ in riga], axis=1)
    piccole = {COLONNE[k]: st.column_config.NumberColumn(COLONNE[k], width=40) for k in chiavi if k != "squadra"}
    st.dataframe(stile, hide_index=True, width="stretch", height=min(35 * len(righe) + 40, 700),
                 column_config={**piccole, "Stemma": st.column_config.ImageColumn("", width=40),
                                "Squadra": st.column_config.TextColumn("Squadra", width=180)})


def _grafico(gruppo, stagione, righe, nome_societa):
    """L'andamento giornata per giornata (punti o posizione) delle squadre scelte, dai risultati letti."""
    dati = girone.tutti().get(gruppo) or {}
    if dati.get("stagione") != stagione:
        return
    punti = girone.andamento(dati.get("giornate") or {})
    if len({p["giornata"] for p in punti}) < 2:
        return
    st.markdown("**📈 Andamento**")
    squadre = sorted({p["squadra"] for p in punti})
    nostra = next((r["squadra"] for r in righe if r["pos"] == nostra_riga(righe, nome_societa)), None)
    nostra = next((s for s in squadre if nostra and s.lower() == nostra.lower()), None)
    prime = [r["squadra"] for r in righe[:3]]
    proposte = [s for s in squadre if s == nostra or s.lower() in (p.lower() for p in prime)]
    scelte = st.multiselect("Squadre", squadre, default=proposte, key=f"cl_grafico_{gruppo}",
                            label_visibility="collapsed", placeholder="Scegli le squadre da confrontare")
    misura = st.segmented_control("Mostra", ["Punti", "Posizione"], default="Punti", key=f"cl_misura_{gruppo}",
                                  label_visibility="collapsed") or "Punti"
    if not scelte:
        return
    campo = "punti" if misura == "Punti" else "posizione"
    df = pd.DataFrame([p for p in punti if p["squadra"] in scelte])
    asse_y = alt.Y(f"{campo}:Q", title=misura, scale=alt.Scale(reverse=campo == "posizione", zero=campo == "punti"),
                   axis=alt.Axis(tickMinStep=1))
    linee = alt.Chart(df).mark_line(point=True).encode(
        x=alt.X("giornata:O", title="Giornata", axis=alt.Axis(labelAngle=0)), y=asse_y,
        color=alt.Color("squadra:N", title=None, legend=alt.Legend(orient="top", columns=2, labelLimit=220)),
        strokeWidth=alt.condition(alt.datum.squadra == (nostra or ""), alt.value(4), alt.value(2)),
        tooltip=["etichetta", "squadra", "punti", "posizione"])
    st.altair_chart(linee, width="stretch")
    st.caption("Calcolato dai risultati letti dalla LND: può differire dalla classifica ufficiale (penalizzazioni, "
               "partite a tavolino).")


def render_classifica(nome_societa=""):
    stagione, gruppi = gruppi_correnti()
    nomi = [g["gruppo"] for g in gruppi]
    if not nomi:
        st.info("Prima crea le squadre in ⚙️ Opzioni → 🏆 Campionati.")
        return
    gruppo = scegli(f"👥 Squadra ({stagione})", nomi, "cl_gruppo") if len(nomi) > 1 else nomi[0]
    salvata = classifiche().get(gruppo)
    if salvata and salvata.get("stagione") == stagione and salvata.get("righe"):
        giorno, _, ora = salvata["aggiornata"].partition(" ")
        st.caption(f"Aggiornata il {giorno[8:10]}/{giorno[5:7]}/{giorno[:4]} alle {ora}"
                   + (f" · [fonte]({salvata['fonte']})" if salvata.get("fonte") else "")
                   + (f" · dati {nome_fonte(salvata.get('fonte'))}" if nome_fonte(salvata.get("fonte")) else "")
                   + " · fa fede il Comunicato Ufficiale.")
        # su PC il grafico sta accanto alla classifica, sul telefono sotto
        sinistra, destra = st.columns([5, 6], gap="large")
        with sinistra:
            _tabella(salvata["righe"], nome_societa)
        with destra:
            _grafico(gruppo, stagione, salvata["righe"], nome_societa)
    elif salvata and nome_fonte(salvata.get("fonte")):
        st.info(f"Link salvato per {gruppo}: la classifica arriva con il prossimo aggiornamento.")
    else:
        st.info(f"Nessuna classifica per {gruppo}: imposta il link della LND in ⚙️ Opzioni → 🌐 Dati LND.")
