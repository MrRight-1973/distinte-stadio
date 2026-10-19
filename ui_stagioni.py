"""⚙️ Opzioni → 🏆 Campionati: anno sportivo in corso, gruppi squadra e loro competizioni."""
import pandas as pd
import streamlit as st

from stagioni import impostazioni_stagioni, salva_stagioni, stagione_di_oggi

GRUPPO, COMPETIZIONE = "Gruppo squadra", "Competizione"


def _successiva(stagione):
    inizio = int(stagione[:4]) + 1
    return f"{inizio}/{(inizio + 1) % 100:02d}"


def render_opzioni_campionati():
    st.subheader("🏆 Anno sportivo, squadre e competizioni")
    st.caption("Tre passi: l'anno sportivo, poi i gruppi squadra (una rosa ciascuno), poi le competizioni di ogni "
               "gruppo (campionato, coppa...). Nella Distinta si sceglie la competizione; archivio e statistiche "
               "si filtrano per gruppo o per singola competizione.")
    for tipo, testo in st.session_state.pop("stagioni_messaggi", []):
        getattr(st, tipo)(testo)
    imp = impostazioni_stagioni()
    oggi = stagione_di_oggi()
    anni = sorted(set(imp["stagioni"]) | {imp["corrente"], oggi, _successiva(oggi)}, reverse=True)
    corrente = st.selectbox("1️⃣ 📅 Anno sportivo in corso", anni, index=anni.index(imp["corrente"]), key="opz_stagione",
                            help="Vale per le nuove distinte; le partite già giocate restano nel loro anno")
    if corrente != imp["corrente"]:
        salva_stagioni(corrente, imp["stagioni"])
        st.session_state["stagioni_messaggi"] = [("success", f"Anno sportivo in corso: {corrente}.")]
        st.rerun()

    gruppi = imp["stagioni"].get(corrente, [])
    precedenti = [a for a in sorted(imp["stagioni"], reverse=True) if a < corrente and imp["stagioni"][a]]
    if not gruppi and precedenti and st.button(f"📋 Copia squadre e competizioni del {precedenti[0]}", use_container_width=True):
        salva_stagioni(corrente, {**imp["stagioni"], corrente: imp["stagioni"][precedenti[0]]})
        st.session_state["stagioni_n"] = st.session_state.get("stagioni_n", 0) + 1
        st.rerun()

    st.markdown(f"**2️⃣ Gruppi squadra e 3️⃣ competizioni {corrente}**: una riga per competizione, col suo gruppo "
                "(es. *Prima Squadra* · *Prima Categoria girone E*, e *Prima Squadra* · *Coppa Veneto*). "
                "Con ➕ in fondo alla tabella si aggiunge una riga.")
    righe = [{GRUPPO: g["gruppo"], COMPETIZIONE: c} for g in gruppi for c in g["competizioni"]] or [{GRUPPO: "", COMPETIZIONE: ""}]
    tabella = st.data_editor(pd.DataFrame(righe, columns=[GRUPPO, COMPETIZIONE]), num_rows="dynamic", hide_index=True,
                             use_container_width=True, key=f"opz_campionati_{corrente}_{st.session_state.get('stagioni_n', 0)}",
                             column_config={GRUPPO: st.column_config.TextColumn(help="La squadra: una sola rosa per tutte le sue competizioni"),
                                            COMPETIZIONE: st.column_config.TextColumn(help="Campionato, coppa, torneo...")})
    nuovi = _da_tabella(tabella)
    if nuovi != gruppi:
        if st.button("💾 Salva squadre e competizioni", type="primary", use_container_width=True):
            salva_stagioni(corrente, {**imp["stagioni"], corrente: nuovi})
            salvati = impostazioni_stagioni()["stagioni"].get(corrente, [])
            st.session_state["stagioni_n"] = st.session_state.get("stagioni_n", 0) + 1
            st.session_state["stagioni_messaggi"] = [("success", f"{corrente}: {len(salvati)} gruppi squadra, "
                                                      f"{sum(len(g['competizioni']) for g in salvati)} competizioni.")]
            st.rerun()
        st.caption("Modifiche non ancora salvate. Senza gruppo, la competizione fa gruppo da sola.")


def _da_tabella(tabella):
    """Righe (gruppo, competizione) → [{"gruppo", "competizioni"}] nell'ordine della tabella."""
    gruppi = {}
    for gruppo, competizione in zip(tabella[GRUPPO].tolist(), tabella[COMPETIZIONE].tolist()):
        competizione = str(competizione).strip() if competizione is not None and not pd.isna(competizione) else ""
        gruppo = str(gruppo).strip() if gruppo is not None and not pd.isna(gruppo) else ""
        if competizione:
            gruppi.setdefault(gruppo or competizione, []).append(competizione)
    return [{"gruppo": g, "competizioni": c} for g, c in gruppi.items()]
