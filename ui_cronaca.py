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
    CAMPI_GIOCATORE,
    ICONE_TIPO,
    SCELTE_DETTAGLIO,
    LUNGHEZZE,
    TIPI_NOTA,
    aggiungi_foto_referto,
    aggiungi_nota,
    TIPI_EVENTO,
    archivia_e_azzera,
    avvia_tempo,
    eventi_correnti,
    gol_da_eventi,
    pulisci_eventi,
    carica_cronaca,
    chiudi_tempo,
    descrizione_nota,
    genera_resoconto,
    giocatori_da_distinta,
    imposta_distinta,
    leggi_audio,
    leggi_foto_referto,
    minuto_di_gioco,
    note_in_ordine,
    orologio,
    punteggio,
    ricalcola_eventi,
    rosa,
    salva_audio,
    salva_cronaca,
    stato_gara,
    testo_semplice,
    togli_foto_referto,
    trascrivi,
)
from cronaca_pdf import genera_pdf_resoconto
from pdf_immagini import immagini_jpeg

SQUADRE = {"": "—", "casa": "Casa", "ospite": "Ospite"}
# I tipi nell'ordine in cui servono più spesso a bordo campo
TIPI_EVENTO_GUIDA = ["Gol", "Occasione", "Ammonizione", "Sostituzione", "Rigore", "Espulsione", "Infortunio", "Nota"]


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


def _galleria_foto(cronaca, elenco, etichetta_caricatore):
    """Foto salvate nella cronaca (referto o distinte): caricarne altre, vederle, toglierle."""
    n = st.session_state.setdefault(f"cronaca_{elenco}_n", 0)
    foto = st.file_uploader(etichetta_caricatore, type=["jpg", "jpeg", "png", "pdf"],
                            accept_multiple_files=True, key=f"cronaca_{elenco}_{n}")
    if foto:
        for f in foto:
            try:
                for pagina in immagini_jpeg(f.getvalue()):  # un PDF diventa una foto per pagina
                    aggiungi_foto_referto(cronaca, pagina, elenco)
            except Exception as e:
                st.error(f"{f.name}: file non leggibile ({e})")
        st.session_state[f"cronaca_{elenco}_n"] = n + 1  # svuota il caricatore
        st.rerun()
    nomi = cronaca.get(elenco) or []
    if nomi:
        colonne = st.columns(min(len(nomi), 3))
        for i, nome in enumerate(nomi):
            with colonne[i % len(colonne)]:
                try:
                    st.image(leggi_foto_referto(nome), use_container_width=True)
                except OSError:
                    st.caption("Foto non più disponibile")
                if st.button("🗑️ Togli", key=f"togli_{elenco}_{nome}", use_container_width=True):
                    togli_foto_referto(cronaca, nome, elenco)
                    st.rerun()


def _referto(cronaca):
    st.subheader("📄 Referto dell'arbitro")
    _galleria_foto(cronaca, "referto", "Carica o scatta la foto del referto (anche PDF)")
    st.subheader("📸 Foto della partita")
    st.caption("Vanno nel PDF del resoconto, dopo la cronaca.")
    _galleria_foto(cronaca, "foto_partita", "Carica o scatta le foto della partita")
    st.subheader("📋 Foto delle distinte")
    st.caption("Si prendono da sole quando pubblichi la distinta; qui puoi aggiungerne o toglierne.")
    _galleria_foto(cronaca, "foto_distinte", "Aggiungi la foto di una distinta (anche PDF)")
    if cronaca.get("foto_distinte"):
        includi = st.checkbox("Metti le foto delle distinte nel PDF del resoconto",
                              value=cronaca.get("pdf_foto_distinte", True),
                              help="Le distinte riportano date di nascita e numeri dei documenti: "
                                   "togli la spunta se il PDF va a chi non deve vederli.")
        if includi != cronaca.get("pdf_foto_distinte", True):
            cronaca["pdf_foto_distinte"] = includi
            salva_cronaca(cronaca)


def _scelta_giocatori(cronaca, tipo, squadra, n_form, iniziali=None):
    """Scelte a tocco (come è nato il gol, motivo del cartellino...) e menu dei giocatori dell'evento.
    iniziali: i dettagli già salvati, per correggere una nota.
    Restituisce i dettagli da salvare nella nota, es. {"giocatore": "ROSSI ANDREA", "giocatore_n": 9, "come": "Punizione"}."""
    iniziali = iniziali or {}
    dettagli = {}
    scelta = SCELTE_DETTAGLIO.get(tipo)
    if scelta:
        campo, domanda, opzioni = scelta
        valore = st.pills(domanda, opzioni, key=f"cronaca_{campo}_{n_form}",
                          default=iniziali.get(campo) if iniziali.get(campo) in opzioni else None)
        if valore:
            dettagli[campo] = valore
    campi = CAMPI_GIOCATORE.get(tipo)
    if not campi:
        return dettagli
    if squadra not in ("casa", "ospite"):
        st.caption("Scegli la squadra per vedere i giocatori.")
        return dettagli
    # Nell'autogol il giocatore è della squadra avversaria
    autogol = tipo == "Gol" and dettagli.get("come") == "Autogol"
    lato = {"casa": "ospite", "ospite": "casa"}[squadra] if autogol else squadra
    giocatori = rosa(cronaca, lato)
    if not giocatori:
        st.caption("Nessuna distinta collegata: pubblicala nella sezione Distinta (o usa «Ricarica la distinta pubblicata») per scegliere i giocatori dai menu.")
        return dettagli
    if autogol:
        campi = [("giocatore", "Autore dell'autogol")]
    opzioni = [None] + giocatori
    colonne = st.columns(len(campi))
    for (campo, etichetta), col in zip(campi, colonne):
        gia = next((i for i, g in enumerate(opzioni) if g and g[1] == iniziali.get(campo)), 0)
        scelto = col.selectbox(etichetta, opzioni, index=gia, key=f"cronaca_{campo}_{lato}_{n_form}", filter_mode=None,
                               format_func=lambda g: "—" if g is None else f"{g[0]} {g[1]}")
        if scelto:
            dettagli[campo], dettagli[f"{campo}_n"] = scelto[1], scelto[0]
    return dettagli


def _form_nota(cronaca, api_key, giocatori):
    """Presa note guidata: si tocca cosa è successo, di quale squadra, chi e come; il commento è facoltativo."""
    n_form = st.session_state.setdefault("cronaca_form_n", 0)
    nomi = {"casa": cronaca["partita"].get("casa") or "Casa", "ospite": cronaca["partita"].get("ospite") or "Ospite"}
    tipo = st.pills("1 · Cosa è successo?", TIPI_EVENTO_GUIDA, key=f"cronaca_tipo_{n_form}",
                    format_func=lambda t: f"{ICONE_TIPO.get(t, '')} {t}")
    if not tipo:
        st.caption("Tocca il tipo di evento: il minuto viene preso in quel momento.")
        return _messaggio_nota()

    # Il minuto è quello in cui si tocca il tipo, non quello in cui si finisce di compilare
    chiave_minuto = f"cronaca_minuto_{n_form}"
    if chiave_minuto not in st.session_state:
        st.session_state[chiave_minuto] = minuto_di_gioco(cronaca)
    minuto = st.session_state[chiave_minuto]

    squadra = st.pills("2 · Squadra", ["casa", "ospite"], key=f"cronaca_squadra_{n_form}",
                       format_func=lambda k: nomi[k]) or ""
    dettagli = _scelta_giocatori(cronaca, tipo, squadra, n_form)

    def registrata(nota):
        st.session_state["cronaca_messaggio"] = (
            "success", f"{nota['minuto']} {tipo} {nomi.get(squadra, '')} {descrizione_nota(nota)} {nota['testo']}".strip())
        st.session_state["cronaca_form_n"] = n_form + 1  # si riparte da capo
        st.rerun()

    st.caption(f"⏱️ {minuto} · commento facoltativo, a voce o scritto")
    # Commento vocale: registrandolo, l'evento si salva subito con le scelte fatte sopra
    n_audio = st.session_state.setdefault("cronaca_audio_n", 0)
    audio = st.audio_input("🎙️ Commento vocale", key=f"cronaca_audio_{n_audio}")
    if audio is not None:
        dati = audio.getvalue()
        impronta = hashlib.sha1(dati).hexdigest()
        if st.session_state.get("cronaca_ultimo_audio") != impronta:
            st.session_state["cronaca_ultimo_audio"] = impronta
            st.session_state["cronaca_audio_n"] = n_audio + 1
            nome_file = salva_audio(dati)
            try:
                with st.spinner("Trascrizione in corso..."):
                    testo = trascrivi(api_key, dati, cronaca, giocatori)
                nota = aggiungi_nota(cronaca, testo or ("" if dettagli else "(nota vocale vuota)"), tipo, squadra,
                                     "voce", None, minuto, dettagli)
            except Exception as e:
                # L'audio resta salvato: si può ritrascrivere più tardi
                nota = aggiungi_nota(cronaca, "(da trascrivere)", tipo, squadra, "voce", nome_file, minuto, dettagli)
                st.session_state["cronaca_avviso"] = f"Commento non trascritto, si può riprovare più tardi: {e}"
            registrata(nota)

    with st.form(f"cronaca_nota_testo_{n_form}"):
        testo = st.text_input("✏️ Commento scritto", placeholder="es. tiro a giro sul secondo palo")
        if st.form_submit_button("✅ Registra", type="primary", use_container_width=True):
            if testo.strip() or dettagli or tipo != "Nota":
                registrata(aggiungi_nota(cronaca, testo, tipo, squadra, "testo", None, minuto, dettagli))
            else:
                st.warning("Per una nota scrivi o detta un commento.")
    if st.button("✖️ Annulla", use_container_width=True, key=f"cronaca_annulla_{n_form}"):
        st.session_state["cronaca_form_n"] = n_form + 1
        st.rerun()
    _messaggio_nota()


def _messaggio_nota():
    messaggio = st.session_state.pop("cronaca_messaggio", None)
    if messaggio:
        getattr(st, messaggio[0])(messaggio[1])
    avviso = st.session_state.pop("cronaca_avviso", None)
    if avviso:
        st.warning(avviso)


def _etichetta_nota(n, nomi):
    squadra = f" {nomi[n['squadra']]}" if n.get("squadra") in nomi else ""
    dettaglio = descrizione_nota(n) or (n.get("testo") or "")[:40]
    return f"{n.get('minuto', '')} · {n.get('tipo', 'Nota')}{squadra} · {dettaglio}".strip(" ·")


def _elenco_note(cronaca, api_key, giocatori):
    note = cronaca["note"]
    if not note:
        st.caption("Ancora nessuna nota.")
    else:
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

        # Elenco in ordine di minuto, come andrà nel resoconto
        nomi = {"casa": cronaca["partita"].get("casa") or "Casa", "ospite": cronaca["partita"].get("ospite") or "Ospite"}
        st.dataframe(
            pd.DataFrame([{"Min.": n.get("minuto", ""), "Tipo": n.get("tipo", ""),
                           "Squadra": nomi.get(n.get("squadra"), ""), "Giocatori": descrizione_nota(n),
                           "Commento": n.get("testo", "")} for n in note_in_ordine(cronaca)]),
            hide_index=True, use_container_width=True,
        )
    _modifica_nota(cronaca)


def _modifica_nota(cronaca):
    """Correggere, aggiungere a mano o togliere una nota, con gli stessi menu della presa note."""
    nomi = {"casa": cronaca["partita"].get("casa") or "Casa", "ospite": cronaca["partita"].get("ospite") or "Ospite"}
    per_id = {n["id"]: n for n in cronaca["note"]}
    n_mod = st.session_state.setdefault("cronaca_mod_n", 0)
    # Un interruttore invece di un riquadro richiudibile: il suo stato è salvato sul server, quindi il
    # pannello resta aperto finché non lo si spegne (anche se il telefono perde un attimo la connessione)
    if not st.toggle("✏️ Correggi, aggiungi o togli una nota", key="cronaca_mod_aperto"):
        return
    with st.container(border=True):
        scelta = st.selectbox(
            "Nota", [None] + [n["id"] for n in note_in_ordine(cronaca)], key=f"cronaca_mod_scelta_{n_mod}",
            format_func=lambda i: "➕ Nuova nota (a mano)" if i is None else _etichetta_nota(per_id[i], nomi),
            filter_mode=None,
        )
        nota = per_id.get(scelta) or {}
        k = f"{scelta or 'nuova'}_{n_mod}"
        c_min, c_tipo, c_squadra = st.columns([1, 2, 2])
        minuto = c_min.text_input("Minuto", nota.get("minuto", ""), key=f"cronaca_mod_minuto_{k}",
                                  placeholder=minuto_di_gioco(cronaca))
        tipo_attuale = nota.get("tipo") if nota.get("tipo") in TIPI_NOTA else "Nota"
        tipo = c_tipo.selectbox("Tipo", TIPI_NOTA, index=TIPI_NOTA.index(tipo_attuale), key=f"cronaca_mod_tipo_{k}",
                                filter_mode=None)
        squadra_attuale = nota.get("squadra") if nota.get("squadra") in SQUADRE else ""
        squadra = c_squadra.selectbox("Squadra", list(SQUADRE), index=list(SQUADRE).index(squadra_attuale),
                                      format_func=lambda s: SQUADRE[s], key=f"cronaca_mod_squadra_{k}", filter_mode=None)
        dettagli = _scelta_giocatori(cronaca, tipo, squadra, f"mod_{k}", iniziali=nota.get("dettagli"))
        testo = st.text_area("Commento", nota.get("testo", ""), key=f"cronaca_mod_testo_{k}", height=80)

        c_salva, c_togli = st.columns(2)
        if c_salva.button("💾 Salva" if nota else "➕ Aggiungi", type="primary", use_container_width=True,
                          key=f"cronaca_mod_salva_{k}"):
            if not (testo.strip() or dettagli):
                st.warning("Scrivi un commento o scegli un giocatore.")
            else:
                if nota:
                    nota.update({"minuto": minuto.strip() or nota.get("minuto", ""), "tipo": tipo, "squadra": squadra,
                                 "testo": testo.strip(), "dettagli": {c: v for c, v in dettagli.items() if v}})
                    salva_cronaca(cronaca)
                else:
                    aggiungi_nota(cronaca, testo, tipo, squadra, "testo", None, minuto.strip() or None, dettagli)
                st.session_state["cronaca_mod_n"] = n_mod + 1
                st.rerun()
        if nota:
            with c_togli.popover("🗑️ Togli", use_container_width=True):
                st.write("Togliere questa nota?")
                if st.button("Sì, togli", type="primary", key=f"cronaca_mod_togli_{k}"):
                    cronaca["note"] = [n for n in cronaca["note"] if n["id"] != nota["id"]]
                    salva_cronaca(cronaca)
                    st.session_state["cronaca_mod_n"] = n_mod + 1
                    st.rerun()


ICONE_EVENTO = {"gol": "⚽ gol", "ammonizione": "🟨 ammonizione", "espulsione": "🟥 espulsione",
                "sostituzione": "🔄 sostituzione"}


def _eventi(cronaca):
    """Il tabellino (gol, cartellini, sostituzioni) come andrà nel PDF, correggibile a mano."""
    st.markdown("**⚽ Tabellino: gol, cartellini e sostituzioni** (correggi qui nomi e minuti prima di scaricare il PDF)")
    eventi = eventi_correnti(cronaca)
    df = pd.DataFrame(eventi, columns=["tipo", "squadra", "minuto", "giocatore", "nota"])
    chiave = f"cronaca_eventi_{st.session_state.setdefault('cronaca_eventi_n', 0)}"
    modificato = st.data_editor(
        df, key=chiave, hide_index=True, num_rows="dynamic", use_container_width=True,
        column_config={
            "tipo": st.column_config.SelectboxColumn("Tipo", options=TIPI_EVENTO, format_func=ICONE_EVENTO.get,
                                                     required=True),
            "squadra": st.column_config.SelectboxColumn("Squadra", options=["casa", "ospite"], required=True),
            "minuto": st.column_config.TextColumn("Min."),
            "giocatore": st.column_config.TextColumn("Giocatore"),
            "nota": st.column_config.TextColumn("Nota (rig., aut.)"),
        },
    )
    if not modificato.reset_index(drop=True).equals(df):
        cronaca["resoconto"]["eventi"] = pulisci_eventi(modificato.fillna("").to_dict("records"))
        salva_cronaca(cronaca)
        st.session_state["cronaca_eventi_n"] += 1
        st.rerun()
    gol = gol_da_eventi(eventi)
    gol_note = punteggio(cronaca)
    if (gol["casa"], gol["ospite"]) != gol_note:
        st.warning(f"Il risultato dei marcatori ({gol['casa']}-{gol['ospite']}) è diverso da quello delle note "
                   f"({gol_note[0]}-{gol_note[1]}): controlla.")
    senza_squadra = [n for n in cronaca["note"] if n.get("tipo") in ("Gol", "Rigore", "Ammonizione", "Espulsione", "Sostituzione")
                     and n.get("squadra") not in ("casa", "ospite")]
    if senza_squadra:
        st.warning("Queste note non sono nell'elenco perché manca la squadra: "
                   + ", ".join(f"{n.get('minuto', '')} {n.get('tipo')}" for n in senza_squadra)
                   + ". Scegli la squadra in «✏️ Correggi, aggiungi o togli una nota» e premi «Ricalcola dalle note».")
    if st.button("🔄 Ricalcola dalle note", help="Rifà l'elenco dalle note attuali; le correzioni fatte qui sopra si perdono"):
        ricalcola_eventi(cronaca)
        st.session_state["cronaca_eventi_n"] += 1
        st.rerun()


def _resoconto(cronaca, api_key, giocatori, loghi_sponsor, leggi_distinta):
    st.subheader("📰 Resoconto per i giornalisti")
    lunghezza = st.selectbox("Lunghezza dell'articolo", list(LUNGHEZZE), index=1, filter_mode=None)
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

    _eventi(cronaca)
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
