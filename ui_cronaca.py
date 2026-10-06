"""Sezione "Cronaca partita" del pannello segreteria.

Al fischio d'inizio si avvia il cronometro; durante la gara si dettano note vocali
(trascritte subito) o si scrivono note, ciascuna col suo minuto. A fine gara un
pulsante scrive il resoconto in stile giornalistico e lo mette in PDF.
"""
import hashlib
import json

import pandas as pd
import streamlit as st

from cronaca_manager import (
    LUNGHEZZE,
    TIPI_NOTA,
    aggiungi_foto_referto,
    aggiungi_nota,
    archivia_e_azzera,
    avvia_tempo,
    carica_cronaca,
    chiudi_tempo,
    genera_resoconto,
    giocatori_da_distinta,
    imposta_distinta,
    leggi_audio,
    leggi_foto_referto,
    minuto_di_gioco,
    orologio,
    punteggio,
    salva_audio,
    salva_cronaca,
    stato_gara,
    testo_semplice,
    togli_foto_referto,
    trascrivi,
)
from cronaca_pdf import genera_pdf_resoconto

SQUADRE = {"": "—", "casa": "Casa", "ospite": "Ospite"}


@st.fragment(run_every=1)
def _tabellone():
    """Cronometro e punteggio: si aggiornano da soli ogni secondo."""
    cronaca = carica_cronaca()
    p = cronaca["partita"]
    gol_casa, gol_ospite = punteggio(cronaca)
    st.markdown(f"### {p.get('casa') or 'Casa'} {gol_casa} – {gol_ospite} {p.get('ospite') or 'Ospite'}")
    st.markdown(f"## ⏱️ {minuto_di_gioco(cronaca)} &nbsp; <small style='color:gray'>{orologio(cronaca)}</small>",
                unsafe_allow_html=True)


AZIONI_TEMPO = {
    # stato della gara: (pulsante, domanda di conferma, tempo, avvia?)
    "prepartita": ("▶️ Fischio d'inizio 1° tempo", "Avviare il cronometro del 1° tempo?", "primo", True),
    "primo": ("⏸️ Fine 1° tempo", "Fermare il cronometro: è finito il 1° tempo?", "primo", False),
    "intervallo": ("▶️ Inizio 2° tempo", "Avviare il cronometro del 2° tempo?", "secondo", True),
    "secondo": ("⏹️ Fine partita", "Fermare il cronometro: è finita la partita?", "secondo", False),
}


@st.dialog("Conferma")
def _conferma_tempo(stato):
    _, domanda, tempo, avvia = AZIONI_TEMPO[stato]
    st.write(domanda)
    si, no = st.columns(2)
    if si.button("Sì, conferma", type="primary", use_container_width=True):
        cronaca = carica_cronaca()
        if stato_gara(cronaca) == stato:  # evita il doppio avvio se si preme due volte
            (avvia_tempo if avvia else chiudi_tempo)(cronaca, tempo)
        st.rerun()
    if no.button("Annulla", use_container_width=True):
        st.rerun()


def _pulsanti_tempo(cronaca):
    stato = stato_gara(cronaca)
    if stato in AZIONI_TEMPO:
        if st.button(AZIONI_TEMPO[stato][0], type="primary", use_container_width=True, key=f"tempo_{stato}"):
            _conferma_tempo(stato)
    else:
        st.success("Partita finita: puoi generare il resoconto qui sotto.")


def _referto(cronaca):
    st.subheader("📄 Referto dell'arbitro")
    n = st.session_state.setdefault("cronaca_referto_n", 0)
    foto = st.file_uploader("Carica o scatta la foto del referto", type=["jpg", "jpeg", "png"],
                            accept_multiple_files=True, key=f"cronaca_referto_{n}")
    if foto:
        for f in foto:
            try:
                aggiungi_foto_referto(cronaca, f.getvalue())
            except Exception as e:
                st.error(f"{f.name}: immagine non leggibile ({e})")
        st.session_state["cronaca_referto_n"] = n + 1  # svuota il caricatore
        st.rerun()
    nomi = cronaca.get("referto") or []
    if nomi:
        colonne = st.columns(min(len(nomi), 3))
        for i, nome in enumerate(nomi):
            with colonne[i % len(colonne)]:
                try:
                    st.image(leggi_foto_referto(nome), use_container_width=True)
                except OSError:
                    st.caption("Foto non più disponibile")
                if st.button("🗑️ Togli", key=f"togli_referto_{nome}", use_container_width=True):
                    togli_foto_referto(cronaca, nome)
                    st.rerun()


def _form_nota(cronaca, api_key, giocatori):
    c_tipo, c_squadra = st.columns(2)
    tipo = c_tipo.selectbox("Tipo", TIPI_NOTA, key="cronaca_tipo")
    squadra = c_squadra.selectbox("Squadra", list(SQUADRE), format_func=lambda k: SQUADRE[k], key="cronaca_squadra")

    # Nota vocale: la chiave cambia dopo ogni registrazione, così il registratore si svuota
    n_audio = st.session_state.setdefault("cronaca_audio_n", 0)
    audio = st.audio_input("🎙️ Nota vocale", key=f"cronaca_audio_{n_audio}")
    if audio is not None:
        dati = audio.getvalue()
        impronta = hashlib.sha1(dati).hexdigest()
        if st.session_state.get("cronaca_ultimo_audio") != impronta:
            st.session_state["cronaca_ultimo_audio"] = impronta
            minuto = minuto_di_gioco(cronaca)  # il minuto di quando si è finito di parlare
            nome_file = salva_audio(dati)
            try:
                with st.spinner("Trascrizione in corso..."):
                    testo = trascrivi(api_key, dati, cronaca, giocatori)
                aggiungi_nota(cronaca, testo or "(nota vocale vuota)", tipo, squadra, "voce", None, minuto)
                st.session_state["cronaca_messaggio"] = ("success", f"{minuto} {testo}")
            except Exception as e:
                # L'audio resta salvato: si può ritrascrivere più tardi
                aggiungi_nota(cronaca, "(da trascrivere)", tipo, squadra, "voce", nome_file, minuto)
                st.session_state["cronaca_messaggio"] = ("warning", f"Nota salvata ma non trascritta: {e}")
            st.session_state["cronaca_audio_n"] = n_audio + 1
            st.rerun()

    # Nota scritta
    with st.form("cronaca_nota_testo", clear_on_submit=True):
        testo = st.text_input("✏️ Nota scritta", placeholder="es. Rossi di testa su cross di Bianchi, 1-0")
        if st.form_submit_button("Aggiungi nota", use_container_width=True) and testo.strip():
            aggiungi_nota(cronaca, testo, tipo, squadra, "testo")
            st.rerun()

    messaggio = st.session_state.pop("cronaca_messaggio", None)
    if messaggio:
        getattr(st, messaggio[0])(messaggio[1])


def _elenco_note(cronaca, api_key, giocatori):
    note = cronaca["note"]
    if not note:
        st.caption("Ancora nessuna nota.")
        return

    da_trascrivere = [n for n in note if n.get("audio")]
    if da_trascrivere and st.button(f"🔁 Trascrivi {len(da_trascrivere)} note vocali in sospeso"):
        with st.spinner("Trascrizione in corso..."):
            for n in da_trascrivere:
                try:
                    n["testo"] = trascrivi(api_key, leggi_audio(n["audio"]), cronaca, giocatori) or n["testo"]
                    n["audio"] = None
                except Exception as e:
                    st.warning(f"{n['minuto']}: {e}")
        salva_cronaca(cronaca)
        st.rerun()

    # Le note si possono correggere o cancellare (selezionare la riga e premere Canc)
    df = pd.DataFrame(
        [{"id": n["id"], "Minuto": n["minuto"], "Tipo": n["tipo"], "Squadra": n.get("squadra", ""), "Testo": n["testo"]}
         for n in note]
    )
    chiave_editor = f"cronaca_editor_{st.session_state.setdefault('cronaca_editor_n', 0)}"
    modificato = st.data_editor(
        df,
        key=chiave_editor,
        hide_index=True,
        num_rows="dynamic",
        use_container_width=True,
        column_order=["Minuto", "Tipo", "Squadra", "Testo"],
        column_config={
            "Minuto": st.column_config.TextColumn(width="small"),
            "Tipo": st.column_config.SelectboxColumn(options=TIPI_NOTA, width="small"),
            "Squadra": st.column_config.SelectboxColumn(options=list(SQUADRE), width="small"),
            "Testo": st.column_config.TextColumn(width="large"),
        },
    )
    if not modificato.reset_index(drop=True).equals(df):
        per_id = {n["id"]: n for n in note}
        nuove = []
        for _, riga in modificato.iterrows():
            originale = per_id.get(riga.get("id")) if isinstance(riga.get("id"), str) else None
            base = originale or {"id": None, "ts": max((n["ts"] for n in note), default=0) + 1, "origine": "testo", "audio": None}
            nuove.append({**base,
                          "minuto": str(riga["Minuto"] or ""), "tipo": riga["Tipo"] or "Nota",
                          "squadra": riga["Squadra"] or "", "testo": str(riga["Testo"] or "")})
        cronaca["note"] = [n for n in nuove if n["testo"] or n["minuto"]]
        for n in cronaca["note"]:
            n["id"] = n["id"] or hashlib.sha1(str(n["ts"]).encode()).hexdigest()[:10]
        salva_cronaca(cronaca)
        # Le modifiche sono salvate: l'editor riparte dai dati nuovi (niente doppie applicazioni)
        st.session_state["cronaca_editor_n"] += 1
        st.rerun()


def _resoconto(cronaca, api_key, giocatori, loghi_sponsor, leggi_distinta):
    st.subheader("📰 Resoconto per i giornalisti")
    lunghezza = st.selectbox("Lunghezza dell'articolo", list(LUNGHEZZE), index=1)
    if st.button("✍️ Genera resoconto e PDF", type="primary", use_container_width=True, disabled=not cronaca["note"]):
        # Si riprende l'ultima distinta pubblicata: la cronaca potrebbe essere partita prima della Fase 3
        try:
            distinta = leggi_distinta()
            if distinta:
                imposta_distinta(cronaca, distinta)
                giocatori.update(giocatori_da_distinta(distinta))
        except Exception:
            pass  # si tiene quella già collegata
        try:
            with st.spinner("Scrittura del resoconto..."):
                genera_resoconto(api_key, cronaca, giocatori, LUNGHEZZE[lunghezza])
        except Exception as e:
            st.error(f"Resoconto non riuscito: {e}")

    if not cronaca.get("resoconto"):
        return

    st.text_area("Testo da copiare (mail o sito)", testo_semplice(cronaca), height=320)
    # Il PDF si rifà solo se note, resoconto o formazioni sono cambiati
    impronta = hashlib.sha1(json.dumps([cronaca, giocatori], sort_keys=True, default=str).encode()).hexdigest()
    if st.session_state.get("cronaca_pdf_impronta") != impronta:
        st.session_state["cronaca_pdf"] = genera_pdf_resoconto(cronaca, giocatori, loghi_sponsor())
        st.session_state["cronaca_pdf_impronta"] = impronta
    p = cronaca["partita"]
    nome = "_".join(x for x in (p.get("casa"), p.get("ospite")) if x).replace(" ", "_") or "partita"
    st.download_button(
        "💾 Scarica PDF del resoconto",
        data=st.session_state["cronaca_pdf"],
        file_name=f"resoconto_{nome}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )


def render_cronaca(api_key, macro_info=None, loghi_sponsor=lambda: None, leggi_distinta=lambda: None):
    """loghi_sponsor: funzione che restituisce i loghi (bytes) da stampare nel PDF.
    leggi_distinta: funzione che restituisce l'ultima distinta pubblicata (info_gara, casa, ospite)."""
    cronaca = carica_cronaca()
    info = macro_info or {}

    # Le liste dei giocatori arrivano dalla distinta pubblicata (Fase 3)
    if not cronaca.get("distinta") or st.session_state.pop("cronaca_ricarica_distinta", False):
        try:
            distinta = leggi_distinta()
        except Exception as e:
            distinta = None
            st.warning(f"Distinta pubblicata non leggibile: {e}")
        if distinta:
            imposta_distinta(cronaca, distinta)
    giocatori = giocatori_da_distinta(cronaca.get("distinta"))

    st.header("🎙️ Cronaca partita")
    if not api_key:
        st.warning("OPENAI_API_KEY non configurata: si possono scrivere note, ma non trascrivere né generare il resoconto.")

    with st.expander("⚙️ Partita", expanded=stato_gara(cronaca) == "prepartita"):
        p = cronaca["partita"]
        c1, c2 = st.columns(2)
        casa = c1.text_input("Squadra di casa", p.get("casa") or info.get("nome_casa", ""))
        ospite = c2.text_input("Squadra ospite", p.get("ospite") or info.get("nome_ospite", ""))
        c3, c4, c5 = st.columns([2, 1, 1])
        campionato = c3.text_input("Campionato", p.get("campionato") or info.get("campionato", ""))
        data = c4.text_input("Data", p.get("data") or info.get("data", ""))
        durata = c5.number_input("Minuti per tempo", 20, 45, int(cronaca.get("durata_tempo") or 45), step=5)
        nuovi = {"casa": casa, "ospite": ospite, "campionato": campionato, "data": data}
        if nuovi != p or durata != cronaca.get("durata_tempo"):
            cronaca["partita"], cronaca["durata_tempo"] = nuovi, int(durata)
            salva_cronaca(cronaca)
        d = cronaca.get("distinta")
        if d:
            st.caption(f"Liste giocatori dalla distinta pubblicata: {(d.get('casa') or {}).get('squadra', '')} – "
                       f"{(d.get('ospite') or {}).get('squadra', '')}")
        else:
            st.caption("Nessuna distinta pubblicata trovata: il PDF non avrà le liste dei giocatori.")
        if st.button("🔄 Ricarica la distinta pubblicata"):
            st.session_state["cronaca_ricarica_distinta"] = True
            cronaca["distinta"] = None
            salva_cronaca(cronaca)
            st.rerun()
        if st.button("🆕 Nuova partita (archivia questa cronaca)"):
            archivia_e_azzera(cronaca, casa=info.get("nome_casa", ""), ospite=info.get("nome_ospite", ""),
                              campionato=info.get("campionato", ""), data=info.get("data", ""))
            st.rerun()

    _tabellone()
    _pulsanti_tempo(cronaca)
    st.markdown("---")
    _form_nota(cronaca, api_key, giocatori)
    st.markdown("---")
    st.subheader("🗒️ Note")
    _elenco_note(cronaca, api_key, giocatori)
    st.markdown("---")
    _referto(cronaca)
    st.markdown("---")
    _resoconto(cronaca, api_key, giocatori, loghi_sponsor, leggi_distinta)
