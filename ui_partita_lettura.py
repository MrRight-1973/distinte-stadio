"""Una partita dell'archivio in sola lettura: liste, risultato, tabellino, note, articolo e foto.
Utile ai mister: si guarda (e se ne scarica il PDF) senza riaprirla nella Cronaca e senza poterla cambiare."""
import pandas as pd
import streamlit as st

from cronaca_manager import (
    cronaca_vuota,
    descrizione_nota,
    eventi_correnti,
    gol_da_eventi,
    leggi_foto_referto,
    note_in_ordine,
)
from cronaca_pdf import genera_pdf_resoconto
from giornata import campionato_e_giornata
from nomi_file import nome_file_gara

ICONE = {"gol": "⚽ Gol", "ammonizione": "🟨 Ammonizione", "espulsione": "🟥 Espulsione",
         "sostituzione": "🔄 Sostituzione"}
FOTO = (("referto", "📄 Referto"), ("foto_distinte", "📋 Distinte"), ("foto_partita", "📷 Partita"))


def _lista(squadra):
    giocatori = squadra.get("giocatori") or []
    if squadra.get("allenatore"):
        st.caption(f"Allenatore: {squadra['allenatore']}")
    if not giocatori:
        st.caption("Lista non disponibile.")
        return
    st.dataframe(pd.DataFrame([{"N°": str(g.get("N°") or i + 1), "Giocatore": g.get("GIOCATORE") or "",
                                "Anno": str(g.get("ANNO") or "")} for i, g in enumerate(giocatori)]),
                 hide_index=True, use_container_width=True)


def render_partita_sola_lettura(id_partita, dati, loghi_sponsor=lambda: None):
    cronaca = {**cronaca_vuota(), **(dati or {})}
    p = cronaca["partita"]
    distinta = cronaca.get("distinta") or {}
    nomi = {"casa": p.get("casa") or "Casa", "ospite": p.get("ospite") or "Ospite"}
    eventi = eventi_correnti(cronaca)
    gol = gol_da_eventi(eventi)

    with st.container(border=True):
        st.markdown(f"#### 👁️ {nomi['casa']} {gol['casa']}-{gol['ospite']} {nomi['ospite']}")
        st.caption(" · ".join(x for x in (campionato_e_giornata(p.get("campionato"), p.get("giornata")),
                                          p.get("data"), f"Arbitro {p['arbitro']}" if p.get("arbitro") else "")
                              if x) + " · sola lettura")
        liste, tabellino, note, articolo, foto = st.tabs(["📋 Liste", "⚽ Tabellino", "🗒️ Note", "📰 Articolo",
                                                          "📷 Foto"])
        with liste:
            c1, c2 = st.columns(2)
            for colonna, lato in ((c1, "casa"), (c2, "ospite")):
                with colonna:
                    squadra = distinta.get(lato) or {}
                    st.markdown(f"**{squadra.get('squadra') or nomi[lato]}**")
                    _lista(squadra)
        with tabellino:
            if eventi:
                st.dataframe(pd.DataFrame([{"Min.": e.get("minuto", ""), "Evento": ICONE.get(e.get("tipo"), ""),
                                            "Squadra": nomi.get(e.get("squadra"), ""),
                                            "Giocatore": e.get("giocatore", ""), "Nota": e.get("nota", "")}
                                           for e in eventi]),
                             hide_index=True, use_container_width=True)
            else:
                st.caption("Nessun gol, cartellino o cambio segnato.")
        with note:
            if cronaca["note"]:
                st.dataframe(pd.DataFrame([{"Min.": n.get("minuto", ""), "Tipo": n.get("tipo", ""),
                                            "Squadra": nomi.get(n.get("squadra"), ""),
                                            "Giocatori": descrizione_nota(n), "Commento": n.get("testo", "")}
                                           for n in note_in_ordine(cronaca)]),
                             hide_index=True, use_container_width=True)
            else:
                st.caption("Nessuna nota.")
        with articolo:
            r = cronaca.get("resoconto") or {}
            if r.get("articolo"):
                if r.get("titolo"):
                    st.markdown(f"**{r['titolo']}**")
                st.write(r["articolo"])
            else:
                st.caption("Il resoconto per i giornalisti non è stato scritto.")
        with foto:
            if cronaca.get("alleggerita"):
                st.caption(f"Foto e note vocali tolte il {cronaca['alleggerita'].get('il', '')}: sono nel backup.")
            elenchi = [(e, etichetta) for e, etichetta in FOTO if cronaca.get(e)]
            if not elenchi:
                st.caption("Nessuna foto.")
            elif st.toggle(f"Mostra le foto ({sum(len(cronaca[e]) for e, _ in elenchi)})", key=f"lett_foto_{id_partita}"):
                for elenco, etichetta in elenchi:
                    st.markdown(f"**{etichetta}**")
                    colonne = st.columns(3)
                    for i, nome in enumerate(cronaca[elenco]):
                        with colonne[i % 3]:
                            try:
                                st.image(leggi_foto_referto(nome), use_container_width=True)
                            except OSError:
                                st.caption("Foto non più disponibile")

        pdf = st.session_state.get("lett_pdf")
        if not pdf or pdf["id"] != id_partita:
            if st.button("📄 Prepara il PDF del resoconto", key=f"lett_prepara_{id_partita}", use_container_width=True):
                with st.spinner("Preparo il PDF..."):
                    st.session_state["lett_pdf"] = {"id": id_partita,
                                                    "pdf": genera_pdf_resoconto(cronaca, sponsor_loghi=loghi_sponsor())}
                st.rerun()
        else:
            st.download_button("💾 Scarica il PDF del resoconto", pdf["pdf"], mime="application/pdf",
                               file_name=nome_file_gara("Resoconto", p.get("data"), p.get("casa"), p.get("ospite")),
                               key=f"lett_scarica_{id_partita}", type="primary", use_container_width=True)
