"""👦 Anagrafica: i ragazzi della società con matricola, documento e certificato medico.

Segreteria e amministratori vedono tutti; un allenatore solo i ragazzi dei gruppi squadra
che gli sono stati assegnati in ⚙️ Opzioni → 👥 Utenti.
"""
from datetime import date

import pandas as pd
import streamlit as st

from anagrafica import (GIORNI_AVVISO, RUOLI_CAMPO, TIPI_DOCUMENTO, data_da_iso, doppione, elenco_ragazzi,
                        elimina_scheda, importa_rose, importa_schede, nome_completo, salva_scheda, scadenze,
                        stato_scadenza)
from import_csv import CsvErrore, schede_da_csv
from stagioni import gruppi_correnti
from utenti import gruppi_utente

TUTTI, SENZA = "Tutti i ragazzi", "Senza squadra quest'anno"
SEGNI = {"scaduto": "🔴", "in scadenza": "🟠", "ok": "🟢", "": ""}


def _data(valore):
    giorno = data_da_iso(valore)
    return giorno.strftime("%d/%m/%Y") if giorno else ""


def _con_segno(valore):
    stato = stato_scadenza(valore)
    return f"{SEGNI[stato]} {_data(valore)}".strip() if stato else "—"


def _messaggio(tipo, testo):
    st.session_state["anag_messaggi"] = [(tipo, testo)]


def render_anagrafica(utente, ruolo):
    st.subheader("👦 Anagrafica ragazzi")
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

    tutti = elenco_ragazzi()
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
    filtro = c1.selectbox(f"👥 Squadra ({stagione})", scelte, key="anag_filtro")
    cerca = c2.text_input("🔍 Cerca", key="anag_cerca", placeholder="Cognome, nome o matricola")
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
    if st.session_state.get("anag_nuovo"):
        _scheda({}, stagione, miei if not staff else nomi_gruppi, staff, n, nuova=True)
        return

    if st.button("➕ Nuovo ragazzo", use_container_width=True):
        st.session_state["anag_nuovo"] = True
        st.rerun()

    if not elenco:
        st.info("Nessun ragazzo con questi filtri." if visibili else
                "L'anagrafica è vuota: aggiungi i ragazzi con ➕ oppure importali dalle rose qui sotto.")
    else:
        righe = [{"Ragazzo": nome_completo(r),
                  "Nato": _data(r.get("nascita")) or r.get("anno_nascita", ""),
                  "Squadra": squadra_di[r["id"]], "Ruolo": r.get("ruolo", ""), "Matricola": r.get("matricola", ""),
                  "Certificato": _con_segno(r.get("certificato_scadenza")),
                  "Documento": _con_segno(r.get("documento_scadenza"))} for r in elenco]
        tabella = pd.DataFrame(righe)
        scelta = st.dataframe(tabella, hide_index=True, use_container_width=True, on_select="rerun",
                              selection_mode="single-row", key=f"anag_tabella_{filtro}_{cerca}_{n}",
                              height=min(35 * len(righe) + 40, 460))
        st.caption(f"{len(elenco)} ragazzi. Seleziona una riga per aprire la scheda.")
        if scelta.selection.rows:
            _scheda(elenco[scelta.selection.rows[0]], stagione, miei if not staff else nomi_gruppi, staff, n)

    if staff:
        _importa_csv(stagione, gruppi)
    if ruolo == "admin":
        _importa(stagione, nomi_gruppi)


def _scheda(r, stagione, gruppi_ammessi, staff, n, nuova=False):
    """Il modulo di una scheda, nuova o esistente."""
    st.markdown("---")
    st.markdown(f"**{'➕ Nuovo ragazzo' if nuova else '✏️ ' + nome_completo(r)}**")
    squadra = (r.get("gruppi") or {}).get(stagione, "")
    squadre = ([""] if staff else []) + gruppi_ammessi
    if squadra and squadra not in squadre:
        squadre.append(squadra)
    oggi = date.today()
    with st.form(f"anag_scheda_{r.get('id', 'nuova')}_{n}"):
        c1, c2 = st.columns(2)
        cognome = c1.text_input("Cognome *", value=r.get("cognome", ""))
        nome = c2.text_input("Nome *", value=r.get("nome", ""))
        c1, c2 = st.columns(2)
        nascita = c1.date_input("Data di nascita", value=data_da_iso(r.get("nascita")), format="DD/MM/YYYY",
                                min_value=date(1950, 1, 1), max_value=oggi)
        gruppo = c2.selectbox(f"Squadra {stagione}", squadre, index=squadre.index(squadra) if squadra in squadre else 0,
                              format_func=lambda g: g or "— nessuna —")
        c1, c2 = st.columns(2)
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
        c1, c2, c3 = st.columns(3)
        scad_cert = c1.date_input("🩺 Certificato medico: scadenza", value=data_da_iso(r.get("certificato_scadenza")),
                                  format="DD/MM/YYYY", min_value=date(2000, 1, 1), max_value=date(2100, 1, 1),
                                  )
        genitore = c2.text_input("Genitore di riferimento", value=r.get("genitore", ""))
        telefono = c3.text_input("Telefono", value=r.get("telefono", ""))
        salva, annulla = st.columns(2)
        premuto = salva.form_submit_button("💾 Salva", type="primary", use_container_width=True)
        chiudi = annulla.form_submit_button("✖️ Chiudi", use_container_width=True)
    if chiudi:
        st.session_state.pop("anag_nuovo", None)
        st.session_state["anag_n"] = n + 1
        st.rerun()
    if premuto:
        if not cognome.strip() or not nome.strip():
            st.error("Cognome e nome sono obbligatori.")
            return
        gruppi = {**(r.get("gruppi") or {}), stagione: gruppo}
        scheda = {**r, "cognome": cognome, "nome": nome, "nascita": nascita,
                  "ruolo": ruolo, "matricola": matricola, "documento_tipo": tipo, "documento_numero": numero_doc,
                  "documento_rilascio": rilascio,
                  "documento_scadenza": scad_doc, "certificato_scadenza": scad_cert, "genitore": genitore,
                  "telefono": telefono, "gruppi": gruppi}
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

    if staff and not nuova:
        if st.session_state.get("anag_elimina") == r["id"]:
            st.warning(f"Eliminare la scheda di {nome_completo(r)}? Non si può annullare.")
            c1, c2 = st.columns(2)
            if c1.button("🗑️ Sì, elimina", type="primary", use_container_width=True, key="anag_elimina_si"):
                elimina_scheda(r["id"])
                st.session_state.pop("anag_elimina", None)
                st.session_state["anag_n"] = n + 1
                _messaggio("success", f"Scheda di {nome_completo(r)} eliminata.")
                st.rerun()
            if c2.button("Annulla", use_container_width=True, key="anag_elimina_no"):
                st.session_state.pop("anag_elimina", None)
                st.rerun()
        elif st.button("🗑️ Elimina la scheda", key="anag_elimina_btn"):
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
