"""👦 Anagrafica: i ragazzi della società con matricola, documento e certificato medico, e in una vista a
parte dirigenti, allenatori e staff (servono per la distinta da stampare in 📝 Crea distinta).

Segreteria e amministratori vedono tutti; un allenatore solo i ragazzi dei gruppi squadra
che gli sono stati assegnati in ⚙️ Opzioni → 👥 Utenti.
"""
from datetime import date

import pandas as pd
import streamlit as st

from anagrafica import (CALCIATORE, CONSENSI_FOTO, CONSENSO_NO, CONSENSO_SI, GIORNI_AVVISO, RUOLI_CAMPO, TIPI_DOCUMENTO, TIPI_PERSONA, applica_tabulato,
                        confronta_tabulato, data_da_iso, doppione,
                        e_calciatore, elenco_ragazzi, elimina_scheda, importa_rose, importa_schede, nome_completo, salva_scheda, scadenze,
                        stato_scadenza)
from import_csv import CsvErrore, schede_da_csv
from moduli_consenso import genera_moduli
from stagioni import gruppi_correnti
from tabulato import leggi_tabulato
from utenti import gruppi_utente

TUTTI, SENZA = "Tutti", "Senza squadra quest'anno"
RAGAZZI, STAFF = "👦 Calciatori", "👔 Dirigenti e staff"
SEGNI = {"scaduto": "🔴", "in scadenza": "🟠", "ok": "🟢", "": ""}
SEGNI_FOTO = {CONSENSO_SI: "✅ Sì", CONSENSO_NO: "🚫 No", "": "❔"}


def _data(valore):
    giorno = data_da_iso(valore)
    return giorno.strftime("%d/%m/%Y") if giorno else ""


def _con_segno(valore):
    stato = stato_scadenza(valore)
    return f"{SEGNI[stato]} {_data(valore)}".strip() if stato else "—"


def _messaggio(tipo, testo):
    st.session_state["anag_messaggi"] = [(tipo, testo)]


def render_anagrafica(utente, ruolo, nome_societa=""):
    st.subheader("👦 Anagrafica")
    st.session_state["anag_societa"] = nome_societa  # intestazione dei moduli privacy
    st.caption("Dati di minori: si scrive solo quello che serve al tesseramento. Del documento e del certificato "
               "medico si salvano tipo, numero e scadenza, mai la foto. Niente di questa pagina va sulla pagina "
               "pubblica.")
    for tipo, testo in st.session_state.pop("anag_messaggi", []):
        getattr(st, tipo)(testo)

    stagione, gruppi = gruppi_correnti()
    nomi_gruppi = [g["gruppo"] for g in gruppi]
    staff = ruolo in ("admin", "segreteria")
    miei = nomi_gruppi if staff else [g for g in gruppi_utente(utente) if g in nomi_gruppi]
    if not staff and not miei:
        st.info("Non ti è ancora stata assegnata nessuna squadra: chiedi all'amministratore di farlo in "
                "⚙️ Opzioni → 👥 Utenti.")
        return

    tab_ragazzi, tab_staff = st.tabs([RAGAZZI, STAFF])  # come i sottomenu di Allenamenti e Statistiche
    with tab_ragazzi:
        _elenco(False, stagione, gruppi, nomi_gruppi, miei, staff, ruolo)
    with tab_staff:
        _elenco(True, stagione, gruppi, nomi_gruppi, miei, staff, ruolo)


def _elenco(dello_staff, stagione, gruppi, nomi_gruppi, miei, staff, ruolo):
    """L'elenco dei calciatori o di dirigenti e staff, con i filtri e la scheda della riga scelta."""
    lato = "staff" if dello_staff else "ragazzi"  # chiavi diverse: le due schede sono sulla pagina insieme

    tutti = [r for r in elenco_ragazzi() if e_calciatore(r) != dello_staff]
    squadra_di = {r["id"]: (r.get("gruppi") or {}).get(stagione, "") for r in tutti}
    visibili = tutti if staff else [r for r in tutti if squadra_di[r["id"]] in miei]

    avvisi = scadenze(visibili)
    if avvisi:
        with st.expander(f"⚠️ Scadenze: {len(avvisi)} da sistemare (entro {GIORNI_AVVISO} giorni o già scadute)",
                         expanded=True):
            for r, cosa, quando, stato in avvisi:
                st.markdown(f"{SEGNI[stato]} **{nome_completo(r)}** · {cosa} "
                            f"{'scaduto' if stato == 'scaduto' else 'scade'} il {_data(quando)}")

    c1, c2 = st.columns([2, 3])
    scelte = ([TUTTI] + nomi_gruppi + [SENZA]) if staff else miei
    filtro = c1.selectbox(f"👥 Squadra ({stagione})", scelte, key=f"anag_filtro_{lato}")
    cerca = c2.text_input("🔍 Cerca", key=f"anag_cerca_{lato}", placeholder="Cognome, nome o matricola")
    if filtro == SENZA:
        elenco = [r for r in visibili if not squadra_di[r["id"]]]
    elif filtro != TUTTI:
        elenco = [r for r in visibili if squadra_di[r["id"]] == filtro]
    else:
        elenco = visibili
    if cerca.strip():
        parole = cerca.upper().split()
        elenco = [r for r in elenco if all(p in f"{nome_completo(r)} {r.get('matricola', '')}" for p in parole)]

    n = st.session_state.get("anag_n", 0)
    if st.session_state.get("anag_nuovo") == lato:
        _scheda({"tipo": "Dirigente"} if dello_staff else {}, stagione, miei if not staff else nomi_gruppi, staff, n,
                nuova=True)
        return

    if st.button("➕ Nuovo dirigente, allenatore o staff" if dello_staff else "➕ Nuovo ragazzo",
                 width="stretch", key=f"anag_nuovo_btn_{lato}"):
        st.session_state["anag_nuovo"] = lato
        st.rerun()

    if not elenco:
        st.info("Nessuno con questi filtri." if visibili else
                "Nessun dirigente o allenatore: aggiungili con ➕." if dello_staff else
                "L'anagrafica è vuota: aggiungi i ragazzi con ➕ oppure importali dalle rose qui sotto.")
    elif dello_staff:
        righe = [{"Nome": nome_completo(r), "Tipo": r.get("tipo", ""), "Qualifica": r.get("qualifica", ""),
                  "Squadra": squadra_di[r["id"]], "Tessera FIGC": r.get("matricola", ""),
                  "Documento": _con_segno(r.get("documento_scadenza")),
                  "Foto": SEGNI_FOTO[r.get("consenso_foto", "")]} for r in elenco]
        scelta = st.dataframe(pd.DataFrame(righe), hide_index=True, width="stretch", on_select="rerun",
                              selection_mode="single-row", key=f"anag_staff_{filtro}_{cerca}_{n}",
                              height=min(35 * len(righe) + 40, 460))
        st.caption(f"{len(elenco)} persone. Seleziona una riga per aprire la scheda.")
        if scelta.selection.rows:
            _scheda(elenco[scelta.selection.rows[0]], stagione, miei if not staff else nomi_gruppi, staff, n)
    else:
        righe = [{"Ragazzo": nome_completo(r),
                  "Nato": _data(r.get("nascita")) or r.get("anno_nascita", ""),
                  "Squadra": squadra_di[r["id"]], "Ruolo": r.get("ruolo", ""), "Matricola": r.get("matricola", ""),
                  "Certificato": _con_segno(r.get("certificato_scadenza")),
                  "Documento": _con_segno(r.get("documento_scadenza")),
                  "Foto": SEGNI_FOTO[r.get("consenso_foto", "")],
                  "Nome online": SEGNI_FOTO[r.get("consenso_nome", "")]} for r in elenco]
        tabella = pd.DataFrame(righe)
        scelta = st.dataframe(tabella, hide_index=True, width="stretch", on_select="rerun",
                              selection_mode="single-row", key=f"anag_tabella_{filtro}_{cerca}_{n}",
                              height=min(35 * len(righe) + 40, 460))
        st.caption(f"{len(elenco)} ragazzi. Seleziona una riga per aprire la scheda. Foto = consenso a foto e "
                   "video sui canali della società; Nome online = nome sulla pagina live (❔ non ancora chiesto).")
        no_foto = [r for r in elenco if r.get("consenso_foto") == CONSENSO_NO]
        if no_foto:
            with st.expander(f"🚫 Senza consenso foto ({len(no_foto)}): da non pubblicare"):
                st.markdown("\n".join(f"- {nome_completo(r)} · {squadra_di[r['id']] or 'senza squadra'}"
                                       for r in no_foto))
        if scelta.selection.rows:
            _scheda(elenco[scelta.selection.rows[0]], stagione, miei if not staff else nomi_gruppi, staff, n)

    if elenco:
        _moduli_elenco(elenco, stagione, squadra_di, lato)
    if staff and not dello_staff:
        _importa_tabulato(stagione, gruppi)
        _importa_csv(stagione, gruppi)
    if ruolo == "admin" and not dello_staff:
        _importa(stagione, nomi_gruppi)


def _moduli_elenco(elenco, stagione, squadra_di, lato):
    """Tutti i moduli privacy delle persone in elenco, una pagina ciascuno, da stampare insieme."""
    with st.expander(f"📄 Moduli privacy e consensi da far firmare ({len(elenco)})"):
        st.caption("Una pagina per persona, già compilata con i dati della scheda e con le caselle dei consensi "
                   "vuote: le risposte firmate si riportano poi nella scheda (📷 foto e 🌐 nome). Il testo "
                   "dell'informativa è un'impostazione di partenza: fallo controllare a chi segue la privacy "
                   "per la società e completa sede ed email.")
        senza = [r for r in elenco if not r.get("consenso_foto") or not r.get("consenso_nome")]
        solo = st.checkbox(f"Solo chi non ha ancora risposto ({len(senza)})", key=f"anag_moduli_senza_{lato}")
        scelti = senza if solo else elenco
        firma = tuple(r["id"] for r in scelti)  # il PDF pronto vale solo per l'elenco con cui è stato fatto
        if st.button("Prepara il PDF", width="stretch", key=f"anag_moduli_prepara_{lato}", disabled=not scelti):
            st.session_state[f"anag_moduli_{lato}"] = (firma, genera_moduli(
                scelti, stagione, st.session_state.get("anag_societa", ""), squadra_di))
        pronto, pdf = st.session_state.get(f"anag_moduli_{lato}") or (None, None)
        if pdf and pronto == firma:
            st.download_button("⬇️ Scarica i moduli", data=pdf, file_name="moduli_privacy_consensi.pdf",
                               mime="application/pdf", type="primary", width="stretch",
                               key=f"anag_moduli_scarica_{lato}")


def _scheda(r, stagione, gruppi_ammessi, staff, n, nuova=False):
    """Il modulo di una scheda, nuova o esistente."""
    st.markdown("---")
    persona_staff = not e_calciatore(r)
    nuovo = "➕ Nuovo dirigente, allenatore o staff" if persona_staff else "➕ Nuovo ragazzo"
    st.markdown(f"**{nuovo if nuova else '✏️ ' + nome_completo(r)}**")
    squadra = (r.get("gruppi") or {}).get(stagione, "")
    squadre = ([""] if staff else []) + gruppi_ammessi
    if squadra and squadra not in squadre:
        squadre.append(squadra)
    oggi = date.today()
    with st.form(f"anag_scheda_{r.get('id') or ('nuova_staff' if persona_staff else 'nuova')}_{n}"):
        c1, c2 = st.columns(2)
        cognome = c1.text_input("Cognome *", value=r.get("cognome", ""))
        nome = c2.text_input("Nome *", value=r.get("nome", ""))
        c1, c2 = st.columns(2)
        nascita = c1.date_input("Data di nascita", value=data_da_iso(r.get("nascita")), format="DD/MM/YYYY",
                                min_value=date(1950, 1, 1), max_value=oggi)
        gruppo = c2.selectbox(f"Squadra {stagione}", squadre, index=squadre.index(squadra) if squadra in squadre else 0,
                              format_func=lambda g: g or "— nessuna —")
        c1, c2 = st.columns(2)
        if persona_staff:
            tipi = TIPI_PERSONA[1:]
            tipo_persona = c1.selectbox("Tipo", tipi, index=tipi.index(r["tipo"]) if r.get("tipo") in tipi else 0)
            qualifica = c2.text_input("Qualifica (come in distinta)", value=r.get("qualifica", ""),
                                      placeholder="Es. Dirigente accompagnatore, Massaggiatore sportivo")
            ruolo = ""
            matricola = st.text_input("N° tessera FIGC", value=r.get("matricola", ""))
        else:
            tipo_persona, qualifica = CALCIATORE, ""
            ruolo = c1.selectbox("Ruolo", RUOLI_CAMPO, index=RUOLI_CAMPO.index(r.get("ruolo", "")) if r.get("ruolo", "") in RUOLI_CAMPO else 0,
                                 format_func=lambda x: x or "—")
            matricola = c2.text_input("Matricola FIGC", value=r.get("matricola", ""))
        st.markdown("🪪 **Documento d'identità**")
        c1, c2, c3 = st.columns(3)
        tipo = c1.selectbox("Tipo", TIPI_DOCUMENTO, format_func=lambda x: x or "—",
                            index=TIPI_DOCUMENTO.index(r.get("documento_tipo", "")) if r.get("documento_tipo", "") in TIPI_DOCUMENTO else 0)
        numero_doc = c2.text_input("Numero", value=r.get("documento_numero", ""))
        scad_doc = c3.date_input("Scadenza", value=data_da_iso(r.get("documento_scadenza")), format="DD/MM/YYYY",
                                 min_value=date(2000, 1, 1), max_value=date(2100, 1, 1))
        rilascio = st.text_input("Rilasciato da", value=r.get("documento_rilascio", ""),
                                 placeholder="Es. Comune di Due Carrare")
        if persona_staff:
            scad_cert, genitore = data_da_iso(r.get("certificato_scadenza")), ""
            telefono = st.text_input("Telefono", value=r.get("telefono", ""))
        else:
            c1, c2, c3 = st.columns(3)
            scad_cert = c1.date_input("🩺 Certificato medico: scadenza", value=data_da_iso(r.get("certificato_scadenza")),
                                      format="DD/MM/YYYY", min_value=date(2000, 1, 1), max_value=date(2100, 1, 1))
            genitore = c2.text_input("Genitore di riferimento", value=r.get("genitore", ""))
            telefono = c3.text_input("Telefono", value=r.get("telefono", ""))
        chi = "dalla persona" if persona_staff else "dai genitori (o dal giocatore maggiorenne)"
        c1, c2 = st.columns(2)
        consenso_foto = c1.selectbox(
            "📷 Consenso a foto e video", CONSENSI_FOTO,
            index=CONSENSI_FOTO.index(r.get("consenso_foto", "")) if r.get("consenso_foto", "") in CONSENSI_FOTO else 0,
            format_func=lambda x: {"": "❔ Non ancora chiesto", CONSENSO_SI: "✅ Sì, firmato",
                                   CONSENSO_NO: "🚫 No"}[x],
            help=f"Il modulo firmato {chi} resta in segreteria: qui si segna solo la risposta.")
        consenso_nome = c2.selectbox(
            "🌐 Nome sulla pagina pubblica", CONSENSI_FOTO,
            index=CONSENSI_FOTO.index(r.get("consenso_nome", "")) if r.get("consenso_nome", "") in CONSENSI_FOTO else 0,
            format_func=lambda x: {"": "❔ Non ancora chiesto", CONSENSO_SI: "✅ Sì, firmato: nome completo",
                                   CONSENSO_NO: "🚫 No, solo il numero"}[x],
            help="Nella distinta e nella diretta della pagina live. Non chiesto: come scelto per la squadra in "
                 "⚙️ Opzioni (giovanili: cognome e iniziale). Sì: nome completo, senza anno di nascita. No: solo il "
                 "numero di maglia. Nell'app e nel PDF per l'arbitro il nome resta sempre completo.")
        salva, annulla = st.columns(2)
        premuto = salva.form_submit_button("💾 Salva", type="primary", width="stretch")
        chiudi = annulla.form_submit_button("✖️ Chiudi", width="stretch")
    if chiudi:
        st.session_state.pop("anag_nuovo", None)
        st.session_state["anag_n"] = n + 1
        st.rerun()
    if premuto:
        if not cognome.strip() or not nome.strip():
            st.error("Cognome e nome sono obbligatori.")
            return
        gruppi = {**(r.get("gruppi") or {}), stagione: gruppo}
        scheda = {**r, "cognome": cognome, "nome": nome, "nascita": nascita, "tipo": tipo_persona,
                  "qualifica": qualifica,
                  "ruolo": ruolo, "matricola": matricola, "documento_tipo": tipo, "documento_numero": numero_doc,
                  "documento_rilascio": rilascio,
                  "documento_scadenza": scad_doc, "certificato_scadenza": scad_cert, "genitore": genitore,
                  "telefono": telefono, "consenso_foto": consenso_foto, "consenso_nome": consenso_nome, "gruppi": gruppi}
        uguale = doppione({**scheda, "cognome": cognome.upper(), "nome": nome.upper(),
                           "nascita": nascita.strftime("%Y-%m-%d") if nascita else ""}, elenco_ragazzi())
        if uguale:
            st.error(f"C'è già {nome_completo(uguale)} con la stessa data di nascita.")
            return
        salvata = salva_scheda(scheda)
        st.session_state.pop("anag_nuovo", None)
        st.session_state["anag_n"] = n + 1
        _messaggio("success", f"Scheda di {nome_completo(salvata)} salvata.")
        st.rerun()

    if not nuova:
        st.download_button("📄 Modulo privacy e consensi da far firmare (PDF)", width="stretch",
                           data=genera_moduli([r], stagione, st.session_state.get("anag_societa", ""),
                                              {r.get("id"): squadra}),
                           file_name=f"consensi_{nome_completo(r).replace(' ', '_')}.pdf", mime="application/pdf",
                           key=f"anag_modulo_{r['id']}")
    if staff and not nuova:
        if st.session_state.get("anag_elimina") == r["id"]:
            st.warning(f"Eliminare la scheda di {nome_completo(r)}? Non si può annullare.")
            c1, c2 = st.columns(2)
            if c1.button("🗑️ Sì, elimina", type="primary", width="stretch", key=f"anag_elimina_si_{r['id']}"):
                elimina_scheda(r["id"])
                st.session_state.pop("anag_elimina", None)
                st.session_state["anag_n"] = n + 1
                _messaggio("success", f"Scheda di {nome_completo(r)} eliminata.")
                st.rerun()
            if c2.button("Annulla", width="stretch", key=f"anag_elimina_no_{r['id']}"):
                st.session_state.pop("anag_elimina", None)
                st.rerun()
        elif st.button("🗑️ Elimina la scheda", key=f"anag_elimina_btn_{r['id']}"):
            st.session_state["anag_elimina"] = r["id"]
            st.rerun()


def _importa(stagione, gruppi):
    from rose import rosa_squadra
    with st.expander("📥 Importa i ragazzi dalle rose dell'anno"):
        st.caption("Crea una scheda per ogni giocatore delle rose di 👕 Rose che non è ancora in anagrafica, già "
                   "nella sua squadra. Il nome è preso come l'ultima parola: controlla i cognomi doppi "
                   "(es. DE ROSSI) e aggiungi data di nascita, matricola e scadenze.")
        if st.button("📥 Importa", key="anag_importa", disabled=not gruppi):
            quanti = importa_rose(stagione, gruppi, rosa_squadra)
            st.session_state["anag_n"] = st.session_state.get("anag_n", 0) + 1
            _messaggio("success" if quanti else "info",
                       f"Importati {quanti} ragazzi." if quanti else "Nessun ragazzo nuovo da importare.")
            st.rerun()


def _prima_squadra(gruppi):
    """Il gruppo che gioca la Prima Categoria (dove vanno i ragazzi nuovi), altrimenti il primo."""
    for g in gruppi:
        if any("prima categoria" in c.lower() for c in g.get("competizioni", [])) or "prima" in g["gruppo"].lower():
            return g["gruppo"]
    return gruppi[0]["gruppo"] if gruppi else ""


def _importa_csv(stagione, gruppi):
    nomi = [g["gruppo"] for g in gruppi]
    with st.expander("📄 Importa o completa da un file CSV"):
        st.caption("Colonne riconosciute: Cognome, Nome, Data di nascita, Matricola, Tipo documento (C.I., PAT...), "
                   "Numero documento, Rilasciato da, Scadenza documento, Scadenza certificato, Ruolo, Squadra. "
                   "Chi è già in anagrafica (stessa matricola, o stesso nome e data di nascita) riceve solo i dati "
                   "che mancano; gli altri vengono aggiunti.")
        file = st.file_uploader("File CSV", type=["csv"], key=f"anag_csv_{st.session_state.get('anag_n', 0)}")
        predefinito = _prima_squadra(gruppi)
        squadra = st.selectbox(f"Squadra {stagione} per chi non ce l'ha", nomi,
                               index=nomi.index(predefinito) if predefinito in nomi else 0, key="anag_csv_squadra",
                               disabled=not nomi)
        if file is not None:
            try:
                righe = schede_da_csv(file.getvalue())
            except CsvErrore as e:
                st.error(str(e))
                return
            st.caption(f"{len(righe)} righe nel file.")
            if st.button("📄 Importa", type="primary", key="anag_csv_ok", disabled=not righe):
                aggiunti, aggiornati = importa_schede(righe, stagione, squadra)
                st.session_state["anag_n"] = st.session_state.get("anag_n", 0) + 1
                _messaggio("success", f"Aggiunti {aggiunti} ragazzi, completate {aggiornati} schede.")
                st.rerun()


def _importa_tabulato(stagione, gruppi):
    """Dal tabulato calciatori del portale FIGC-LND: matricola e data di nascita a chi non le ha, e una scheda
    nuova per i tesserati che non sono in anagrafica (nella squadra scelta riga per riga)."""
    nomi = [g["gruppo"] for g in gruppi]
    with st.expander("🪪 Completa dal tabulato tesserati FIGC (PDF)"):
        st.caption("Carica il «Tabulato calciatori dilettanti» scaricato dal portale della società. Aggiungo "
                   "matricola e data di nascita a chi non le ha e creo le schede dei tesserati che mancano. Il "
                   "codice fiscale serve solo a separare cognome e nome e non viene salvato.")
        n = st.session_state.get("anag_n", 0)
        file = st.file_uploader("Tabulato (PDF)", type=["pdf"], key=f"anag_tab_{n}")
        if file is None:
            return
        try:
            tesserati = leggi_tabulato(file.getvalue())
        except Exception as e:
            st.error(f"Non riesco a leggere il PDF: {e}")
            return
        if not tesserati:
            st.error("Nel PDF non ho trovato tesserati: serve il «Tabulato calciatori dilettanti» del portale FIGC-LND.")
            return
        ragazzi = elenco_ragazzi()
        per_id = {r["id"]: r for r in ragazzi}
        confronti = confronta_tabulato(tesserati, ragazzi)
        predefinita = _prima_squadra(gruppi)
        righe = []
        for c in confronti:
            t = c["tesserato"]
            if c["id"] is None:
                esito = "➕ nuovo"
            elif c["mancanti"]:
                esito = "✏️ aggiungo " + " e ".join({"matricola": "matricola", "nascita": "data di nascita"}[m]
                                                    for m in c["mancanti"])
            else:
                esito = "✅ già a posto"
            if c["diverso"]:
                esito = f"✏️ correggo la data di nascita ({c['diverso']})" + \
                    (" e aggiungo la matricola" if "matricola" in c["mancanti"] else "")
            r = per_id.get(c["id"]) or {}
            righe.append({"Sì": c["id"] is None or bool(c["mancanti"]), "Cognome": t["cognome"], "Nome": t["nome"],
                          "Nato il": f"{data_da_iso(t['nascita']):%d/%m/%Y}", "Matricola": t["matricola"],
                          "Esito": esito,
                          "Squadra": ((r.get("gruppi") or {}).get(stagione) or SENZA) if r else (predefinita or SENZA)})
        nuovi = sum(c["id"] is None for c in confronti)
        da_completare = sum(bool(c["mancanti"]) for c in confronti)
        st.caption(f"{len(tesserati)} tesserati: {nuovi} nuovi, {da_completare} schede da completare, "
                   f"{len(tesserati) - nuovi - da_completare} già a posto. Per i nuovi scegli la squadra; togli la "
                   "spunta a chi non vuoi importare.")
        tabella = st.data_editor(pd.DataFrame(righe), hide_index=True, width="stretch", key=f"anag_tab_ed_{n}",
                                 disabled=["Cognome", "Nome", "Nato il", "Matricola", "Esito"],
                                 column_config={"Sì": st.column_config.CheckboxColumn(width="small"),
                                                "Squadra": st.column_config.SelectboxColumn(options=nomi + [SENZA])})
        scelte = [(c, "" if riga["Squadra"] == SENZA else riga["Squadra"])
                  for c, riga in zip(confronti, tabella.to_dict("records"))
                  if riga["Sì"] and (c["id"] is None or c["mancanti"])]
        if st.button(f"🪪 Applica ({len(scelte)})", type="primary", key="anag_tab_ok", disabled=not scelte):
            aggiunti, completati = applica_tabulato(scelte, stagione)
            st.session_state["anag_n"] = n + 1
            _messaggio("success", f"Aggiunti {aggiunti} tesserati, completate {completati} schede.")
            st.rerun()
