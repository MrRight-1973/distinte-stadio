"""📊 Statistiche → 👀 Pagina live: quante volte è stata aperta la pagina spettatori e da quanti telefoni."""
import pandas as pd
import streamlit as st

from ui_archivio import data_ordinabile
from visite import VisiteErrore, riepilogo

ISTRUZIONI = (
    "Per attivare il contatore servono due passi, una volta sola:\n\n"
    "1. In Supabase apri **SQL Editor → New query**, incolla il contenuto del file `supabase/visite.sql` "
    "del repository e premi **Run**.\n"
    "2. In Supabase apri **Project Settings → API Keys** e copia la chiave **publishable** (o *anon*): "
    "è quella fatta apposta per le pagine web, non la secret. Aggiungila nei secrets dell'app come "
    "`SUPABASE_PUBBLICA = \"...\"`.\n\n"
    "Il conteggio parte dalla prossima pubblicazione della distinta (o dalla prossima archiviazione).")


def _data(iso):
    p = str(iso or "").split("-")
    return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 else ""


def render_visite(chiave_pubblica):
    st.caption("Ogni apertura della pagina spettatori conta una visita. I dispositivi diversi si contano con un "
               "numero a caso che il telefono si tiene: nessun nome, nessun indirizzo IP.")
    try:
        righe = riepilogo()
    except VisiteErrore as e:
        if str(e) == "manca":
            st.info(ISTRUZIONI)
        else:
            st.warning(f"Visite non disponibili: {e}")
        return
    if not chiave_pubblica:
        st.warning("Manca `SUPABASE_PUBBLICA` nei secrets: la pagina non conta le nuove visite.\n\n" + ISTRUZIONI)
    if not righe:
        st.info("Ancora nessuna visita registrata: si contano dalla prossima pubblicazione della distinta.")
        return
    m = st.columns(2)
    m[0].metric("Aperture in tutto", sum(r["aperture"] for r in righe))
    m[1].metric("Partite seguite", sum(1 for r in righe if not r["partita"].startswith("In attesa")))
    tabella = pd.DataFrame([{"Partita": r["partita"], "Dal": _data(r["primo_giorno"]), "Al": _data(r["ultimo_giorno"]),
                             "Aperture": r["aperture"], "Dispositivi": r["dispositivi"]} for r in righe])
    st.dataframe(tabella, hide_index=True, width="stretch")
    partite = [r for r in righe if not r["partita"].startswith("In attesa")]
    if partite:
        partite.sort(key=lambda r: data_ordinabile(r["partita"]))
        st.bar_chart(pd.DataFrame({"Dispositivi": [r["dispositivi"] for r in partite]},
                                  index=[r["partita"][:40] for r in partite]))
