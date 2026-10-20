"""📝 Crea distinta: si scelgono partita, giocatori e persone in panchina dall'anagrafica e si stampa la
distinta ufficiale sul modello della società. Le distinte si salvano per riaprirle e ristamparle; una
nuova riparte dall'ultima della stessa squadra (stessi giocatori, numeri e dirigenti).
"""
from datetime import date

import pandas as pd
import streamlit as st

from anagrafica import anno_di, data_da_iso, e_calciatore, elenco_ragazzi, nome_completo, tipo_di
from distinta_ufficiale import (ASSISTENTE, MAX_GIOCATORI, RIGHE_PANCHINA_AGGIUNTIVA, RUOLI_PANCHINA, controlli,
                                distinte_stagione, elimina_distinta, etichetta, genera_pdf_distinta, ordinate,
                                salva_distinta, ultima_del_gruppo)
from nomi_file import nome_file_gara
from stagioni import gruppi_correnti
from utenti import gruppi_utente

NUOVA = "➕ Nuova distinta"
IN_CASA, FUORI = "🏠 In casa", "🚌 In trasferta"
ALTRA = "✏️ Altra competizione..."
NESSUNO = ""


def _messaggio(tipo, testo):
    st.session_state["cd_messaggi"] = [(tipo, testo)]


def _base(scelta, distinte, gruppo, nome_squadra):
    """La distinta da cui partire: quella aperta, oppure per una nuova l'ultima della squadra senza i dati
    della partita (avversario, data, campo cambiano ogni volta)."""
    if scelta != NUOVA:
        return distinte[scelta]
    ultima = ultima_del_gruppo(distinte, gruppo) or {}
    return {"gruppo": gruppo, "squadra": ultima.get("squadra") or nome_squadra, "in_casa": True,
            "competizione": ultima.get("competizione", ""), "giocatori": ultima.get("giocatori", []),
            "ruoli": ultima.get("ruoli", {}), "panchina": ultima.get("panchina", [])}


def _proposta_ruoli(staff, gruppo, stagione):
    """Senza distinte precedenti: l'allenatore e il primo dirigente della squadra."""
    della_squadra = [r for r in staff if (r.get("gruppi") or {}).get(stagione) == gruppo]
    allenatore = next((r["id"] for r in della_squadra if tipo_di(r) == "Allenatore"), NESSUNO)
    dirigente = next((r["id"] for r in della_squadra if tipo_di(r) == "Dirigente"), NESSUNO)
    return {"allenatore": allenatore, "accompagnatore": dirigente}


def render_crea_distinta(utente, ruolo, nome_societa):
    st.subheader("📝 Crea distinta")
    st.caption("Prepara la distinta da consegnare all'arbitro con i dati dell'👦 Anagrafica (matricole e "
               "documenti) e stampala sul modello della società. Resta tra i dati privati: non va sulla "
               "pagina pubblica.")
    for tipo, testo in st.session_state.pop("cd_messaggi", []):
        getattr(st, tipo)(testo)

    stagione, gruppi = gruppi_correnti()
    nomi_gruppi = [g["gruppo"] for g in gruppi]
    assegnati = [g for g in gruppi_utente(utente) if g in nomi_gruppi]
    miei = assegnati if ruolo not in ("admin", "segreteria") and assegnati else nomi_gruppi
    if not miei:
        st.info("Crea prima i gruppi squadra in ⚙️ Opzioni → 🏆 Campionati.")
        return
    persone = {r["id"]: r for r in elenco_ragazzi()}
    staff = [r for r in persone.values() if not e_calciatore(r)]

    distinte = distinte_stagione(stagione)
    elenco = [d for d in ordinate(distinte) if d.get("gruppo") in miei]
    if "cd_apri" in st.session_state:  # dopo il salvataggio di una nuova: resta aperta quella
        st.session_state["cd_scelta"] = st.session_state.pop("cd_apri")
    if st.session_state.get("cd_scelta") not in [NUOVA] + [d["id"] for d in elenco]:
        st.session_state["cd_scelta"] = NUOVA
    scelta = st.selectbox("📂 Distinta", [NUOVA] + [d["id"] for d in elenco], key="cd_scelta",
                          format_func=lambda i: i if i == NUOVA else f"{etichetta(distinte[i])} · {distinte[i]['gruppo']}")
    n = st.session_state.get("cd_n", 0)

    if scelta == NUOVA:
        gruppo = st.selectbox(f"👥 Squadra ({stagione})", miei, key="cd_gruppo")
    else:
        gruppo = distinte[scelta]["gruppo"]
    base = _base(scelta, distinte, gruppo, nome_societa)
    k = f"{scelta}_{gruppo}_{n}"  # le chiavi cambiano quando si apre un'altra distinta

    # --- La partita
    st.markdown("**🏟️ Partita**")
    c1, c2 = st.columns(2)
    dove = c1.segmented_control("Si gioca", [IN_CASA, FUORI], default=IN_CASA if base.get("in_casa", True) else FUORI,
                                required=True, key=f"cd_dove_{k}")
    squadra = c2.text_input("Nostra squadra (come in distinta)", value=base.get("squadra") or nome_societa,
                            key=f"cd_squadra_{k}")
    avversario = st.text_input("Avversario", value=base.get("avversario", ""), key=f"cd_avversario_{k}")
    competizioni = next((g["competizioni"] for g in gruppi if g["gruppo"] == gruppo), [])
    opzioni = competizioni + [ALTRA]
    attuale = base.get("competizione", "")
    comp = st.selectbox("Valevole per", opzioni, key=f"cd_comp_{k}",
                        index=opzioni.index(attuale) if attuale in opzioni else (len(opzioni) - 1 if attuale else 0))
    if comp == ALTRA:
        comp = st.text_input("Competizione", value=attuale, key=f"cd_comp_testo_{k}")
    c1, c2 = st.columns(2)
    giorno = c1.date_input("In programma il", value=data_da_iso(base.get("data")) or date.today(),
                           format="DD/MM/YYYY", key=f"cd_data_{k}")
    ora = c2.text_input("Ore", value=base.get("ora", "15:30"), key=f"cd_ora_{k}")
    c1, c2 = st.columns(2)
    localita = c1.text_input("Località", value=base.get("localita", ""), key=f"cd_localita_{k}")
    campo = c2.text_input("Stadio / campo", value=base.get("campo", ""), key=f"cd_campo_{k}")

    # --- I giocatori
    st.markdown(f"**👦 Giocatori** (al massimo {MAX_GIOCATORI})")
    squadra_di = {i: (r.get("gruppi") or {}).get(stagione, "") for i, r in persone.items()}
    giocabili = sorted((r for r in persone.values() if e_calciatore(r)),
                       key=lambda r: (squadra_di[r["id"]] != gruppo, nome_completo(r)))
    precedenti = [g for g in base.get("giocatori", []) if g["id"] in persone]
    scelti = st.multiselect(
        "Giocatori in distinta", [r["id"] for r in giocabili], default=[g["id"] for g in precedenti],
        max_selections=MAX_GIOCATORI, key=f"cd_giocatori_{k}", placeholder="Scegli i giocatori",
        format_func=lambda i: f"{nome_completo(persone[i])} ({anno_di(persone[i]) or '?'})"
                              + ("" if squadra_di[i] == gruppo else f" · {squadra_di[i] or 'senza squadra'}"))
    numeri = st.session_state.setdefault(f"cd_numeri_{k}", {g["id"]: g.get("numero") for g in precedenti})
    for i in scelti:  # chi è nuovo prende il primo numero libero
        if not numeri.get(i):
            liberi = sorted(set(range(1, 100)) - {numeri.get(x) for x in scelti})
            numeri[i] = liberi[0]
    giocatori = []
    if scelti:
        righe = sorted(scelti, key=lambda i: numeri[i])
        tabella = st.data_editor(
            pd.DataFrame({"N°": [numeri[i] for i in righe], "Giocatore": [nome_completo(persone[i]) for i in righe]}),
            hide_index=True, use_container_width=True, disabled=["Giocatore"], key=f"cd_tab_{k}_{hash(tuple(righe))}",
            column_config={"N°": st.column_config.NumberColumn(min_value=1, max_value=99, step=1, required=True,
                                                               width="small")},
            height=min(35 * len(righe) + 40, 760))
        for i, numero in zip(righe, tabella["N°"]):
            numeri[i] = int(numero)
        st.caption("Il numero è quello di maglia; per cambiarlo tocca la cella del numero.")
        c1, c2 = st.columns(2)
        capitani = {g["id"]: g.get("cap") for g in precedenti}
        nomi_scelti = [NESSUNO] + scelti
        cap = c1.selectbox("Capitano (C)", nomi_scelti, key=f"cd_cap_{k}",
                           format_func=lambda i: nome_completo(persone[i]) if i else "—",
                           index=next((nomi_scelti.index(i) for i in scelti if capitani.get(i) == "C"), 0))
        vice = c2.selectbox("Vice capitano (VC)", nomi_scelti, key=f"cd_vice_{k}",
                            format_func=lambda i: nome_completo(persone[i]) if i else "—",
                            index=next((nomi_scelti.index(i) for i in scelti if capitani.get(i) == "VC"), 0))
        giocatori = [{"id": i, "numero": numeri[i], "cap": "C" if i == cap else "VC" if i == vice else ""}
                     for i in sorted(scelti, key=lambda i: numeri[i])]

    # --- Panchina
    st.markdown("**👔 Persone ammesse in panchina**")
    if not staff:
        st.info("In 👦 Anagrafica → 👔 Dirigenti e staff non c'è ancora nessuno: aggiungi dirigenti e allenatori.")
    ids_staff = [NESSUNO] + [r["id"] for r in sorted(staff, key=lambda r: (squadra_di[r["id"]] != gruppo,
                                                                           nome_completo(r)))]

    def chi(i):
        if not i:
            return "—"
        r = persone[i]
        return f"{nome_completo(r)} ({r.get('qualifica') or tipo_di(r)})"

    ruoli_base = base.get("ruoli") or _proposta_ruoli(staff, gruppo, stagione)
    ruoli = {}
    for posto, (chiave, etichetta_) in enumerate([ASSISTENTE] + RUOLI_PANCHINA):
        if posto % 2 == 0:  # una riga per coppia: sul telefono restano nell'ordine del modulo
            colonne = st.columns(2)
        attuale = ruoli_base.get(chiave, NESSUNO)
        ruoli[chiave] = colonne[posto % 2].selectbox(
            etichetta_.replace(" Sig.", "").replace(" Dott.", ""), ids_staff, format_func=chi, key=f"cd_{chiave}_{k}",
            index=ids_staff.index(attuale) if attuale in ids_staff else 0)
    panchina = st.multiselect(f"Panchina aggiuntiva (al massimo {RIGHE_PANCHINA_AGGIUNTIVA})", ids_staff[1:],
                              default=[i for i in base.get("panchina", []) if i in ids_staff],
                              max_selections=RIGHE_PANCHINA_AGGIUNTIVA, format_func=chi, key=f"cd_panchina_{k}",
                              placeholder="Es. massaggiatore")

    in_casa = dove == IN_CASA
    distinta = {**({"id": base["id"]} if base.get("id") else {}), "gruppo": gruppo, "squadra": squadra.strip(),
                "in_casa": in_casa, "avversario": avversario.strip(),
                "casa": squadra.strip() if in_casa else avversario.strip(),
                "ospite": avversario.strip() if in_casa else squadra.strip(),
                "competizione": comp.strip(), "data": giorno.isoformat() if giorno else "", "ora": ora.strip(),
                "localita": localita.strip(), "campo": campo.strip(), "giocatori": giocatori,
                "ruoli": {c: i for c, i in ruoli.items() if i}, "panchina": panchina,
                "autore": base.get("autore") or utente}

    # --- Controlli, salvataggio e stampa
    problemi = controlli(distinta, persone)
    if problemi:
        with st.expander(f"⚠️ Da controllare prima di stampare ({len(problemi)})", expanded=True):
            for p in problemi:
                st.markdown(f"- {p}")
    c1, c2 = st.columns(2)
    if c1.button("💾 Salva", use_container_width=True, key=f"cd_salva_{k}", disabled=not avversario.strip()):
        salvata = salva_distinta(stagione, distinta)
        st.session_state["cd_apri"] = salvata["id"]
        st.session_state["cd_n"] = n + 1
        _messaggio("success", f"Distinta {etichetta(salvata)} salvata.")
        st.rerun()
    if c2.button("🖨️ Salva e prepara il PDF", type="primary", use_container_width=True, key=f"cd_pdf_{k}",
                 disabled=not avversario.strip() or not giocatori):
        salvata = salva_distinta(stagione, distinta)
        st.session_state["cd_pdf_pronto"] = (salvata["id"], genera_pdf_distinta(salvata, persone, squadra.strip()),
                                             nome_file_gara("Distinta", giorno.strftime("%d/%m/%Y") if giorno else "",
                                                            salvata["casa"], salvata["ospite"]))
        st.session_state["cd_apri"] = salvata["id"]
        st.session_state["cd_n"] = n + 1
        st.rerun()
    if not avversario.strip():
        st.caption("Scrivi l'avversario per salvare la distinta.")
    pronto = st.session_state.get("cd_pdf_pronto")
    if pronto and pronto[0] == scelta:
        st.download_button("⬇️ Scarica la distinta (PDF)", pronto[1], file_name=pronto[2], mime="application/pdf",
                           type="primary", use_container_width=True, key="cd_scarica")
        st.caption("Stampala e falla firmare al dirigente accompagnatore. Se cambi qualcosa, prepara di nuovo il PDF.")

    if scelta != NUOVA:
        if st.session_state.get("cd_elimina") == scelta:
            st.warning(f"Eliminare la distinta {etichetta(distinte[scelta])}?")
            c1, c2 = st.columns(2)
            if c1.button("🗑️ Sì, elimina", type="primary", use_container_width=True, key="cd_elimina_si"):
                elimina_distinta(stagione, scelta)
                st.session_state.pop("cd_elimina", None)
                st.session_state["cd_n"] = n + 1
                _messaggio("success", "Distinta eliminata.")
                st.rerun()
            if c2.button("Annulla", use_container_width=True, key="cd_elimina_no"):
                st.session_state.pop("cd_elimina", None)
                st.rerun()
        elif st.button("🗑️ Elimina questa distinta", key="cd_elimina_btn"):
            st.session_state["cd_elimina"] = scelta
            st.rerun()
