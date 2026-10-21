"""L'aggiornamento dei dati del girone (classifica, risultati, avversari): il pulsante "Aggiorna adesso" con
l'avviso mentre l'Action gira (in 📊 Statistiche) e i link delle pagine LND (⚙️ Opzioni → 🌐 Dati LND)."""
import time

import streamlit as st

import classifica
import girone
from azione_classifiche import AzioneErrore, avvia, stato
from stagioni import gruppi_correnti


def _dimentica_dati():
    """Fa rileggere da Supabase classifica e giornate appena l'Action ha finito."""
    classifica._letta["dati"] = None
    girone._letto["dati"] = None


def _in_corso(s):
    """Sta girando? Appena avviata, GitHub mostra il nuovo giro dopo qualche secondo: intanto conta come in corso."""
    avviato = st.session_state.get("lnd_avviato", 0)
    appena = time.time() - avviato < 90 and (not s or s.get("creata", 0) < avviato - 5)
    return bool(s and s["in_corso"]) or appena


@st.fragment(run_every=20)
def _avviso(token, repo):
    s = stato(token, repo)
    era_in_corso, in_corso = st.session_state.get("lnd_in_corso", False), _in_corso(s)
    st.session_state["lnd_in_corso"] = in_corso
    if in_corso:
        st.warning(f"⏳ Aggiornamento dei dati LND in corso (partito alle {(s or {}).get('dalle') or 'adesso'}): "
                   "classifica, risultati e avversari si aggiornano da soli appena finisce, di solito in pochi "
                   "minuti.")
    if in_corso and not era_in_corso:
        st.rerun(scope="app")  # partito da solo (mattina e sera) o da un altro utente: via il pulsante
    elif era_in_corso and not in_corso:
        _dimentica_dati()
        st.session_state["lnd_messaggio"] = ("Dati LND aggiornati." if s and s["esito"] == "success"
                                             else "L'aggiornamento è finito con un errore: riprova più tardi.")
        st.rerun(scope="app")


def render_aggiornamento(token, repo=None):
    """Riga sopra le schede di Statistiche: avviso se l'Action gira, altrimenti il pulsante."""
    if st.session_state.get("lnd_messaggio"):
        st.success(st.session_state.pop("lnd_messaggio"))
    if not token:
        st.caption("I dati LND si aggiornano da soli ogni mattina e ogni sera.")
        return
    _avviso(token, repo)
    if st.session_state.get("lnd_in_corso"):
        return
    if st.button("🔄 Aggiorna adesso i dati LND", key="lnd_aggiorna",
                 help="Rilegge dalla LND classifica, risultati e calendario. Ci vogliono alcuni minuti; "
                      "da solo si aggiorna comunque ogni mattina e ogni sera."):
        try:
            avvia(token, repo)
            st.session_state["lnd_avviato"] = time.time()
            st.rerun()
        except AzioneErrore as e:
            st.error(str(e))


def render_opzioni_dati_lnd():
    st.subheader("🌐 Dati LND")
    st.caption("Per ogni squadra incolla il link del girone su gare.lnd.it (va bene anche quello di una "
               "giornata: la giornata viene tolta). Ogni mattina e ogni sera, o con 🔄 Aggiorna adesso in "
               "📊 Statistiche, l'app legge da lì classifica, risultati e calendario di tutte le giornate.")
    if st.session_state.get("lnd_link_messaggio"):
        st.success(st.session_state.pop("lnd_link_messaggio"))
    stagione, gruppi = gruppi_correnti()
    if not gruppi:
        st.info("Prima crea le squadre in ⚙️ Opzioni → 🏆 Campionati.")
        return
    salvate = classifica.classifiche()
    for g in gruppi:
        gruppo = g["gruppo"]
        salvata = salvate.get(gruppo) or {}
        attuale = salvata.get("fonte", "")
        st.markdown(f"**👥 {gruppo}**")
        link = st.text_input("Link LND", value=attuale, key=f"lnd_link_{gruppo}", label_visibility="collapsed",
                             placeholder="https://gare.lnd.it/competizione/veneto?campionato=...&girone=...")
        nuovo = classifica.link_attuale(link) if link.strip() else ""
        if link.strip() and not classifica.nome_fonte(link):
            st.warning("Serve un link di gare.lnd.it (o di tuttocampo.it).")
        elif nuovo != attuale and st.button("💾 Salva", key=f"lnd_salva_{gruppo}", type="primary"):
            righe = (salvata.get("righe") or []) if salvata.get("stagione") == stagione else []
            classifica.salva(gruppo, stagione, righe, nuovo)
            st.session_state["lnd_link_messaggio"] = (
                f"Link di {gruppo} salvato: i dati arrivano col prossimo aggiornamento." if nuovo
                else f"Link di {gruppo} tolto: i dati non si aggiornano più.")
            st.rerun()
        elif attuale and salvata.get("aggiornata"):
            giorno, _, ora = salvata["aggiornata"].partition(" ")
            st.caption(f"Ultimo aggiornamento: {giorno[8:10]}/{giorno[5:7]} alle {ora} · "
                       f"{len(salvata.get('righe') or [])} squadre in classifica")
