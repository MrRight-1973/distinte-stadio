"""⚖️ Squalifiche dal Comunicato: in 👦 Anagrafica si segnano e si cancellano, in 📝 Crea distinta si vedono
quelle della squadra con le giornate che restano alla partita."""
import time
from datetime import date

import streamlit as st

import squalifiche
from anagrafica import e_calciatore, elenco_ragazzi, nome_completo
from disciplina import partite_della_competizione

FINE = "9999-12-31"


def partite_giocate():
    """Le partite della Cronaca (archivio e aperta), rilette al massimo ogni 5 minuti: servono per i cartellini."""
    salvate = st.session_state.get("cd_partite")
    if not salvate or time.time() - salvate[0] > 300:
        from ui_statistiche import _partite
        salvate = (time.time(), _partite())
        st.session_state["cd_partite"] = salvate
    return salvate[1]


def mostra(elenco, persone, date_giocate, giorno, tipo=None, elimina=False):
    """Una riga per squalifica: giocatore, durata, Comunicato e quante giornate restano (con 🗑️ se elimina).
    date_giocate: funzione squalifica → date delle partite giocate nella sua squadra e competizione."""
    for s in sorted(elenco, key=lambda s: s.get("data_cu", ""), reverse=True):
        durata, esito = squalifiche.descrivi(s, date_giocate(s), giorno, tipo)
        riga = (f"**{nome_completo(persone[s['persona']])}**: {durata}, Comunicato del "
                f"{squalifiche._gg_mm(s['data_cu'])} · {esito}")
        if not elimina:
            st.markdown(f"- {riga}")
            continue
        c1, c2 = st.columns([5, 1])
        c1.markdown(riga)
        if c2.button("🗑️", key=f"anag_sq_del_{s['id']}", help="Elimina questa squalifica"):
            squalifiche.elimina(s["id"])
            st.rerun()


def render_squalifiche(stagione, miei, nome_societa, utente):
    """La scheda ⚖️ Squalifiche di 👦 Anagrafica: l'elenco delle squadre visibili e il modulo per segnarne una."""
    st.caption("Quando il Giudice Sportivo dà più giornate (o una squalifica a tempo), segnala qui: le giornate si "
               "contano sulle partite della squadra e competizione segnate in 🎙️ Cronaca dopo la data del "
               "Comunicato. In 📝 Crea distinta il giocatore compare come squalificato finché non le ha scontate.")
    persone = {r["id"]: r for r in elenco_ragazzi()}
    if st.session_state.get("anag_sq_msg"):
        st.success(st.session_state.pop("anag_sq_msg"))
    gruppo = st.selectbox(f"👥 Squadra ({stagione})", miei, key="anag_sq_gruppo")
    oggi = date.today().isoformat()

    def date_giocate(s):
        nome = "COPPA" if s.get("tipo") == "coppa" else "campionato"
        return [d for d, _ in partite_della_competizione(partite_giocate(), (nome_societa,), stagione,
                                                           s.get("gruppo"), nome, FINE)]

    mie = [s for s in squalifiche.elenco() if s.get("stagione") == stagione and s["persona"] in persone
           and s.get("gruppo") == gruppo]
    if mie:
        st.markdown("**Ad oggi**")
        mostra(mie, persone, date_giocate, oggi, elimina=True)
    else:
        st.info("Nessuna squalifica segnata per questa squadra.")

    st.markdown("**➕ Segna una squalifica**")
    giocatori = sorted((r for r in persone.values() if e_calciatore(r)),
                       key=lambda r: ((r.get("gruppi") or {}).get(stagione, "") != gruppo, nome_completo(r)))
    nomi = {r["id"]: nome_completo(r) for r in giocatori}
    chi = st.selectbox("Giocatore", list(nomi), format_func=nomi.get, index=None,
                       placeholder="Scegli il giocatore", key="anag_sq_chi")
    c1, c2 = st.columns(2)
    data_cu = c1.date_input("Data del Comunicato", value=date.today(), format="DD/MM/YYYY", key="anag_sq_cu")
    modo = c2.segmented_control("Squalifica", ["📅 A giornate", "⏳ A tempo"], default="📅 A giornate",
                                required=True, key="anag_sq_modo")
    c1, c2 = st.columns(2)
    tipo, giornate, fino = "campionato", 0, None
    if modo == "⏳ A tempo":
        fino = c1.date_input("Fino al (compreso)", value=None, format="DD/MM/YYYY", key="anag_sq_fino")
    else:
        giornate = c1.number_input("Giornate", min_value=1, max_value=50, value=1, step=1, key="anag_sq_gg")
        tipo = c2.selectbox("Competizione", ["campionato", "coppa"], format_func=str.capitalize, key="anag_sq_tipo")
    if st.button("⚖️ Segna squalifica", key="anag_sq_salva",
                 disabled=not chi or not data_cu or (modo == "⏳ A tempo" and not fino)):
        squalifiche.aggiungi(chi, stagione, gruppo, tipo, data_cu.isoformat(), giornate,
                             fino.isoformat() if fino else "", utente)
        st.session_state["anag_sq_msg"] = f"⚖️ Squalifica di {nomi[chi]} segnata."
        for chiave in ("anag_sq_chi", "anag_sq_fino"):
            st.session_state.pop(chiave, None)
        st.rerun()
