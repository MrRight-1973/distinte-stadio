"""Sezione "Archivio" del pannello segreteria: le partite chiuse, lo spazio occupato su Supabase,
il backup ZIP (dati, resoconto PDF, foto, note vocali) e la liberazione dello spazio."""
import json
import re
from datetime import datetime

import pandas as pd
import streamlit as st

import archivio_cloud
from cronaca_manager import (
    ELENCHI_FOTO,
    alleggerisci_partita,
    carica_cronaca,
    conta_file,
    crea_backup,
    elimina_partita_archiviata,
    fase_in_corso,
    file_collegati,
    pulisci_file_orfani,
    partite_archiviate,
    riapri_partita,
    ripristina_backup,
    stato_archivio_online,
)
from cronaca_pdf import genera_pdf_resoconto
from ui_partita_lettura import render_partita_sola_lettura
from giornata import normalizza_giornata
from stagioni import gruppo_di, impostazioni_stagioni, stagione_di_oggi, stagione_partita
from nomi_file import nome_file_gara
from archivio_stagione import crea_archivio_stagione, partite_della_stagione

# Limiti del piano gratuito di Supabase
LIMITE_FILE = 1024 ** 3        # 1 GB per foto e note vocali
LIMITE_DATI = 500 * 1024 ** 2  # 500 MB di database
CARTELLE = ("foto", "audio", "distinte_pubblicate", "in_lavorazione")


def _misura(n):
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB".replace(".", ",")
    return f"{n / 1024 ** 3:.2f} GB".replace(".", ",")


def _spazio(tutte):
    """Indicatori dello spazio usato, in un riquadro chiuso; restituisce {percorso online: byte}
    per pesare ogni partita. tutte: {id: dati} di tutte le partite salvate."""
    file = {}
    for cartella in CARTELLE:
        file.update({f"{cartella}/{nome}": byte for nome, byte in archivio_cloud.elenco_file(cartella).items()})
    usati_file = sum(file.values())
    usati_dati = sum(len(json.dumps(d, ensure_ascii=False).encode()) for d in tutte.values())
    if usati_file > 0.8 * LIMITE_FILE:
        st.warning("Lo spazio per le foto è quasi pieno: fai un backup delle partite vecchie e libera spazio.")
    with st.expander(f"💾 Spazio su Supabase: foto {usati_file / LIMITE_FILE:.0%}, dati {usati_dati / LIMITE_DATI:.1%}"):
        st.progress(min(usati_file / LIMITE_FILE, 1.0),
                    text=f"Foto e note vocali: {_misura(usati_file)} su 1 GB ({usati_file / LIMITE_FILE:.0%})")
        st.progress(min(usati_dati / LIMITE_DATI, 1.0),
                    text=f"Dati delle partite: {_misura(usati_dati)} su 500 MB ({usati_dati / LIMITE_DATI:.1%})")
        _dettaglio_spazio(file, tutte)
    return file


def _dettaglio_spazio(file, tutte):
    """Di chi sono le foto: archivio, partita aperta, distinte pubblicate, file rimasti senza partita."""
    usati = file_collegati(tutte)
    gruppi = {"archivio": 0, "aperta": 0, "distinte": 0, "orfani": 0}
    orfani = []
    for percorso, byte in file.items():
        if percorso.startswith(("distinte_pubblicate/", "in_lavorazione/")):
            gruppi["distinte"] += byte
        elif percorso in usati["aperta"]:
            gruppi["aperta"] += byte
        elif percorso in usati["archivio"]:
            gruppi["archivio"] += byte
        else:
            gruppi["orfani"] += byte
            orfani.append(percorso)
    st.caption(f"Partite in archivio {_misura(gruppi['archivio'])} · partita aperta in Cronaca "
               f"{_misura(gruppi['aperta'])} · foto delle distinte caricate e pubblicate {_misura(gruppi['distinte'])}"
               + (f" · file non più usati {_misura(gruppi['orfani'])}" if orfani else ""))
    if orfani and st.button(f"🧽 Elimina {len(orfani)} file non più usati ({_misura(gruppi['orfani'])})",
                            use_container_width=True):
        if _prova(pulisci_file_orfani, orfani):
            st.session_state["arch_messaggio"] = f"🧽 Eliminati {len(orfani)} file che nessuna partita usava."
            st.rerun()


def _prova(funzione, *argomenti):
    try:
        funzione(*argomenti)
        return True
    except archivio_cloud.ArchivioErrore as e:
        st.error(str(e))
        return False


ORDINI = {"📅 Data": "data", "🔢 Giornata": "giornata"}


def data_ordinabile(data):
    """(anno, mese, giorno) da "dd/mm/yyyy ...", per l'ordine; senza data in fondo."""
    numeri = re.findall(r"\d+", str(data or ""))
    if len(numeri) >= 3:
        anno = int(numeri[2]) + (2000 if len(numeri[2]) == 2 else 0)
        return (anno, int(numeri[1]), int(numeri[0]))
    return (0, 0, 0)


def _data_breve(data):
    """"05/10/2026 ore 15:30" -> "05/10/26": la tabella resta stretta anche sul telefono."""
    a, m, g = data_ordinabile(data)
    return f"{g:02d}/{m:02d}/{a % 100:02d}" if a else str(data or "").split(" ore")[0]


def ordina_partite(partite, per="data"):
    """Dalla più recente: per data della partita, oppure per giornata (a parità, per data)."""
    def chiave(p):
        giornata = int(normalizza_giornata(p.get("giornata")) or 0)
        data = data_ordinabile(p.get("data"))
        return (giornata, data) if per == "giornata" else (data, giornata)
    return sorted(partite, key=chiave, reverse=True)


def _filtri(partite):
    """Anno sportivo, gruppo squadra e competizione: ogni squadra della società ha le sue partite.
    Restituisce (partite filtrate, firma del filtro per la tabella)."""
    for p in partite:
        p["stagione"] = stagione_partita(p)
        p["gruppo"] = gruppo_di(p.get("campionato"), p["stagione"])
    corrente = impostazioni_stagioni()["corrente"]
    anni = sorted({p["stagione"] for p in partite if p["stagione"]}, reverse=True)
    c1, c2, c3 = st.columns(3)
    scelte_anni = ["Tutti gli anni"] + anni
    anno = c1.selectbox("📅 Anno sportivo", scelte_anni, key="arch_anno",
                        index=scelte_anni.index(corrente) if corrente in anni else 0)
    if anno != "Tutti gli anni":
        partite = [p for p in partite if p["stagione"] == anno]
    gruppi = sorted({p["gruppo"] for p in partite} - {""})
    gruppo = c2.selectbox("👥 Squadra", ["Tutte le squadre"] + gruppi, key="arch_gruppo")
    if gruppo != "Tutte le squadre":
        partite = [p for p in partite if p["gruppo"] == gruppo]
    campionati = sorted({p.get("campionato") or "" for p in partite} - {""})
    scelte = ["Tutte le competizioni"] + campionati + (["Senza campionato"] if any(not p.get("campionato") for p in partite) else [])
    campionato = c3.selectbox("🏆 Competizione", scelte, key=f"arch_campionato_{gruppo}")
    if campionato == "Senza campionato":
        partite = [p for p in partite if not p.get("campionato")]
    elif campionato != "Tutte le competizioni":
        partite = [p for p in partite if p.get("campionato") == campionato]
    return partite, f"{anno}|{gruppo}|{campionato}"


def _tabella_partite(partite, dettagli, file_online, ordine, aperta_da=None, sola_lettura=False):
    """Le partite in una tabella compatta, una riga ciascuna: si selezionano con la casella a sinistra.
    In sola lettura se ne sceglie una per guardarla, e la colonna dei file non serve."""
    righe = []
    for p in partite:
        gol = "–" if p.get("gol_casa") is None else f"{p['gol_casa']}-{p['gol_ospite']}"
        righe.append({
            "G.": normalizza_giornata(p.get("giornata")),
            "Data": _data_breve(p.get("data")),
            "Partita": f"{p.get('casa') or 'Casa'} {gol} {p.get('ospite') or 'Ospite'}",
            "Campionato": p.get("campionato") or "",
        })
        if not sola_lettura:
            righe[-1]["File"] = (("✏️ aperta in Cronaca · " if p["id"] == aperta_da else "")
                                 + _descrizione_file(dettagli.get(p["id"], {}), file_online))
    scelta = st.dataframe(pd.DataFrame(righe), hide_index=True, use_container_width=True,
                          on_select="rerun", selection_mode="single-row" if sola_lettura else "multi-row",
                          key=f"arch_tabella_{ordine}_{st.session_state.get('arch_tabella_n', 0)}",
                          height=min(35 * len(righe) + 40, 420),
                          column_config={"G.": st.column_config.TextColumn(width="small"),
                                         "Partita": st.column_config.TextColumn(width="large")})
    return [partite[i] for i in scelta.selection.rows]


def _azioni_partita(p, cronaca):
    """Con una sola partita selezionata: guardarla, riaprirla in Cronaca o eliminarla."""
    if st.session_state.get("arch_da_eliminare") == p["id"]:
        st.warning(f"Eliminare definitivamente {p.get('casa')} – {p.get('ospite')}, con foto e note vocali?")
        c1, c2 = st.columns(2)
        if c1.button("🗑️ Sì, elimina", key="arch_si", type="primary", use_container_width=True):
            if _prova(elimina_partita_archiviata, p["id"]):
                st.session_state.pop("arch_da_eliminare", None)
                _deseleziona()
                st.rerun()
        if c2.button("Annulla", key="arch_no", use_container_width=True):
            st.session_state.pop("arch_da_eliminare", None)
            st.rerun()
        return
    c0, c1, c2 = st.columns(3)
    guardata = st.session_state.get("arch_guarda") == p["id"]
    if c0.button("🙈 Chiudi la visione" if guardata else "👁️ Guarda in sola lettura", key="arch_guarda_btn",
                 use_container_width=True):
        st.session_state["arch_guarda"] = None if guardata else p["id"]
        st.rerun()
    if c1.button("📂 Riapri in Cronaca", key="arch_apri", use_container_width=True):
        if fase_in_corso(cronaca):
            st.error("C'è un tempo in corso nella Cronaca: chiudilo prima di riaprire un'altra partita.")
        else:
            if not _prova(riapri_partita, cronaca, p["id"]):
                return
            _deseleziona()
            st.session_state["vai_a_sezione"] = "🎙️ Cronaca partita"
            st.session_state["partita_vista"] = "🎙️ Cronaca partita"
            st.session_state["cronaca_messaggio"] = ("success", "📂 Partita riaperta: in archivio resta com'era finché "
                                                                "non la archivi di nuovo. Quella di prima è in archivio.")
            st.rerun()
    if c2.button("🗑️ Elimina", key="arch_elimina", use_container_width=True):
        st.session_state["arch_da_eliminare"] = p["id"]
        st.rerun()


def _deseleziona():
    """La tabella riparte senza righe selezionate."""
    st.session_state["arch_tabella_n"] = st.session_state.get("arch_tabella_n", 0) + 1


def _descrizione_file(dati_partita, file_online):
    """Testo tipo "📷 4 foto · 🎙️ 2 vocali · 3,1 MB" oppure "📦 solo dati" per una partita."""
    if dati_partita.get("alleggerita"):
        a = dati_partita["alleggerita"]
        return f"📦 solo dati: foto e vocali tolti il {a.get('il', '')} (sono nel backup)"
    foto, audio = conta_file(dati_partita)
    if not foto and not audio:
        return ""
    nomi = [f"foto/{n}" for e in ELENCHI_FOTO for n in dati_partita.get(e) or []]
    nomi += [f"audio/{n['audio']}" for n in dati_partita.get("note") or [] if n.get("audio")]
    byte = sum(file_online.get(n, 0) for n in nomi)
    parti = [f"📷 {foto} foto"] if foto else []
    if audio:
        parti.append(f"🎙️ {audio} vocali")
    return " · ".join(parti + [_misura(byte)])


def _azioni_selezione(selezionate, loghi_sponsor, cronaca):
    st.markdown(f"**☑️ {len(selezionate)} partit{'a selezionata' if len(selezionate) == 1 else 'e selezionate'}**")
    if len(selezionate) == 1:
        _azioni_partita(selezionate[0], cronaca)
    chiave = tuple(sorted(p["id"] for p in selezionate))
    backup = st.session_state.get("arch_backup")
    if not backup or backup["ids"] != chiave:
        st.caption("Il backup è un file ZIP con dati, resoconto PDF, foto e note vocali: salvalo sul PC o su Google Drive.")
        if st.button("📦 Prepara backup", type="primary", use_container_width=True):
            with st.spinner("Preparo il backup (scarico foto e creo i PDF)..."):
                loghi = loghi_sponsor()
                try:
                    zip_ = crea_backup(chiave, lambda c: genera_pdf_resoconto(c, sponsor_loghi=loghi))
                except archivio_cloud.ArchivioErrore as e:
                    st.error(str(e))
                    return
            st.session_state["arch_backup"] = {"ids": chiave, "zip": zip_, "scaricato": False}
            st.rerun()
        return

    if len(selezionate) == 1:
        p = selezionate[0]
        nome = nome_file_gara("Backup", p.get("data"), p.get("casa"), p.get("ospite"), "zip")
    else:
        nome = f"Backup_{len(selezionate)}_partite_{datetime.now():%Y-%m-%d}.zip"

    def scaricato():
        st.session_state["arch_backup"]["scaricato"] = True

    st.download_button(f"⬇️ Scarica backup ({_misura(len(backup['zip']))})", backup["zip"], file_name=nome,
                       mime="application/zip", on_click=scaricato, type="primary", use_container_width=True)
    if not backup["scaricato"]:
        st.caption("Dopo aver scaricato il backup potrai liberare spazio.")
        return

    st.markdown("**🧹 Libera spazio**")
    scelta = st.radio("Cosa togliere da Supabase?", [
        "Solo foto e note vocali: note, tabellino, articolo e statistiche restano",
        "Tutta la partita: resta solo nel backup",
    ], key="arch_cosa_togliere")
    conferma = st.checkbox("Ho salvato il backup in un posto sicuro", key="arch_conferma_backup")
    if st.button("🧹 Libera spazio", disabled=not conferma, use_container_width=True):
        azione = alleggerisci_partita if scelta.startswith("Solo") else elimina_partita_archiviata
        for id_partita in chiave:
            if not _prova(azione, id_partita):
                return
        _deseleziona()
        st.session_state.pop("arch_backup", None)
        st.session_state["arch_messaggio"] = f"🧹 Spazio liberato per {len(chiave)} partite."
        st.rerun()


def _ripristino(cronaca):
    with st.expander("♻️ Ripristina da un backup"):
        st.caption("Rimette nell'archivio le partite di un file ZIP creato qui, con foto e note vocali.")
        f = st.file_uploader("File di backup (.zip)", type=["zip"], key=f"arch_zip_{st.session_state.get('arch_zip_n', 0)}")
        if f and st.button("♻️ Ripristina", use_container_width=True):
            try:
                nomi, saltate = ripristina_backup(f.getvalue(), cronaca.get("id", ""))
            except Exception as e:
                st.error(f"Backup non leggibile: {e}")
                return
            st.session_state["arch_zip_n"] = st.session_state.get("arch_zip_n", 0) + 1
            st.session_state["arch_messaggio"] = (f"♻️ Ripristinate {len(nomi)} partite: " + ", ".join(nomi)) if nomi \
                else "Nel file non c'erano partite da ripristinare."
            if saltate:
                st.session_state["arch_messaggio"] += (" La partita aperta nella Cronaca non è stata toccata: "
                                                       "per ripristinarla, apri prima una nuova partita.")
            st.rerun()


def _chiudi_stagione(dettagli, loghi_sponsor, cronaca, nome_societa):
    """📦 Un unico ZIP con l'anno sportivo (partite, statistiche, presenze, anagrafica), poi spazio libero."""
    with st.expander("📦 Chiudi stagione"):
        st.caption("Un unico file ZIP con tutto l'anno sportivo: partite (resoconti, foto, note vocali), "
                   "statistiche in PDF, presenze agli allenamenti e anagrafica dei ragazzi. Dopo averlo "
                   "salvato puoi liberare spazio su Supabase; l'anagrafica resta nell'app per l'anno dopo.")
        stagioni = sorted({stagione_partita(d.get("partita")) for d in dettagli.values() if d}
                          | {impostazioni_stagioni().get("corrente") or stagione_di_oggi()} - {"", None}, reverse=True)
        stagione = st.selectbox("Stagione", stagioni, key="arch_stagione")
        archivio = st.session_state.get("arch_stagione_zip")
        if not archivio or archivio["stagione"] != stagione:
            if st.button("📦 Prepara archivio stagione", type="primary", use_container_width=True):
                with st.spinner("Preparo l'archivio (scarico foto, creo resoconti e statistiche)..."):
                    loghi = loghi_sponsor()
                    try:
                        zip_, fatto = crea_archivio_stagione(
                            stagione, nome_societa, lambda c: genera_pdf_resoconto(c, sponsor_loghi=loghi))
                    except archivio_cloud.ArchivioErrore as e:
                        st.error(str(e))
                        return
                st.session_state["arch_stagione_zip"] = {"stagione": stagione, "zip": zip_, "fatto": fatto,
                                                         "scaricato": False}
                st.rerun()
            return

        fatto = archivio["fatto"]
        st.markdown(f"Dentro: **{fatto['partite']}** partite, statistiche di "
                    f"{', '.join(fatto['statistiche']) or 'nessuna squadra'}, presenze di "
                    f"{', '.join(fatto['presenze']) or 'nessuna squadra'}, **{fatto['ragazzi']}** ragazzi.")
        for problema in fatto["problemi"]:
            st.warning(problema)

        def scaricato():
            st.session_state["arch_stagione_zip"]["scaricato"] = True

        st.download_button(f"⬇️ Scarica archivio {stagione} ({_misura(len(archivio['zip']))})", archivio["zip"],
                           file_name=f"Archivio_stagione_{re.sub(r'[^0-9]+', '-', stagione).strip('-')}.zip",
                           mime="application/zip", on_click=scaricato, type="primary", use_container_width=True)
        aperta = {cronaca.get("id"), cronaca.get("archivio_id")} - {None, ""}
        ids = sorted(set(partite_della_stagione(stagione)) - aperta)
        if not archivio["scaricato"] or not ids:
            st.caption("Dopo aver scaricato l'archivio potrai liberare spazio." if ids
                       else "Nessuna partita archiviata da togliere da Supabase.")
            return

        st.markdown(f"**🧹 Libera spazio** · {len(ids)} partite della stagione {stagione}")
        scelta = st.radio("Cosa togliere da Supabase?", [
            "Solo foto e note vocali: note, tabellino, articolo e statistiche restano",
            "Tutte le partite: restano solo nell'archivio",
        ], key="arch_stagione_cosa")
        st.caption("Anagrafica e presenze agli allenamenti restano nell'app.")
        conferma = st.checkbox("Ho salvato l'archivio in un posto sicuro", key="arch_stagione_conferma")
        if st.button("🧹 Libera spazio della stagione", disabled=not conferma, use_container_width=True):
            azione = alleggerisci_partita if scelta.startswith("Solo") else elimina_partita_archiviata
            for id_partita in ids:
                if not _prova(azione, id_partita):
                    return
            _deseleziona()
            st.session_state.pop("arch_stagione_zip", None)
            st.session_state["arch_messaggio"] = f"🧹 Spazio liberato per le {len(ids)} partite della stagione {stagione}."
            st.rerun()


def render_archivio(loghi_sponsor=lambda: None, nome_societa="", sola_lettura=False, gruppi=None):
    """sola_lettura: le partite si guardano soltanto (niente riapri, elimina, backup o spazio).
    gruppi: se indicati, solo le partite di queste squadre (un allenatore vede le sue)."""
    st.header("📚 Archivio partite")
    if sola_lettura:
        _render_sola_lettura(loghi_sponsor, gruppi)
        return
    if stato_archivio_online() is None:
        st.info("L'archivio funziona con Supabase: aggiungi SUPABASE_URL e SUPABASE_KEY nei secrets dell'app.")
        return
    messaggio = st.session_state.pop("arch_messaggio", None)
    if messaggio:
        st.success(messaggio)

    cronaca = carica_cronaca()
    try:
        dettagli = archivio_cloud.dati_partite()
        file_online = _spazio(dettagli)
        partite = partite_archiviate(cronaca)
    except archivio_cloud.ArchivioErrore as e:
        st.warning(str(e))
        return

    if not partite:
        st.caption("Nessuna partita in archivio: ci finiscono con \"🆕 Nuova partita\" nella Cronaca.")
    else:
        st.caption("Le partite chiuse; quella aperta è nella Cronaca. Spunta una o più righe per riaprirle, "
                   "eliminarle o farne il backup.")
        partite, filtro = _filtri(partite)
        ordine = st.segmented_control("Ordina per", list(ORDINI), default="📅 Data", key="arch_ordine",
                                      label_visibility="collapsed") or "📅 Data"
        partite = ordina_partite(partite, ORDINI[ordine])
        if not partite:
            st.caption("Nessuna partita con questi filtri.")
        else:
            selezionate = _tabella_partite(partite, dettagli, file_online, f"{ORDINI[ordine]}_{filtro}",
                                           cronaca.get("archivio_id"))
            if selezionate:
                _azioni_selezione(selezionate, loghi_sponsor, cronaca)
            guardata = st.session_state.get("arch_guarda")
            if len(selezionate) == 1 and selezionate[0]["id"] == guardata:
                render_partita_sola_lettura(guardata, dettagli.get(guardata), loghi_sponsor)
    st.markdown("---")
    if st.session_state.get("ruolo") == "admin":
        _chiudi_stagione(dettagli, loghi_sponsor, cronaca, nome_societa)
    _ripristino(cronaca)


def _render_sola_lettura(loghi_sponsor, gruppi):
    cronaca = carica_cronaca()
    try:
        dettagli = archivio_cloud.dati_partite()
        partite = partite_archiviate(cronaca)
    except archivio_cloud.ArchivioErrore as e:
        st.warning(str(e))
        return
    if not partite:
        st.caption("Nessuna partita in archivio.")
        return
    st.caption("Scegli una partita per guardarne liste, tabellino, note, articolo e foto, o scaricarne il PDF. "
               "Qui non si cambia niente.")
    if gruppi is not None:
        partite = [p for p in partite if gruppo_di(p.get("campionato"), stagione_partita(p)) in gruppi]
    partite, filtro = _filtri(partite)
    ordine = st.segmented_control("Ordina per", list(ORDINI), default="📅 Data", key="arch_ordine",
                                  label_visibility="collapsed") or "📅 Data"
    partite = ordina_partite(partite, ORDINI[ordine])
    if not partite:
        st.caption("Nessuna partita con questi filtri." if gruppi is None or gruppi
                   else "Non ti è ancora stata assegnata nessuna squadra: chiedi all'amministratore di farlo in "
                        "⚙️ Opzioni → 👥 Utenti.")
        return
    scelte = _tabella_partite(partite, dettagli, {}, f"lettura_{ORDINI[ordine]}_{filtro}", sola_lettura=True)
    if scelte:
        render_partita_sola_lettura(scelte[0]["id"], dettagli.get(scelte[0]["id"]), loghi_sponsor)
