"""📝 Crea distinta: si scelgono partita, giocatori e persone in panchina dall'anagrafica e si stampa la
distinta ufficiale sul modello della società. Le distinte si salvano per riaprirle e ristamparle; una
nuova riparte dall'ultima della stessa squadra (stessi giocatori, numeri e dirigenti).
"""
from datetime import date

import streamlit as st

from anagrafica import anno_di, data_da_iso, e_calciatore, elenco_ragazzi, nome_completo, tipo_di
from distinta_ufficiale import (ASSISTENTE, MASSAGGIATORE, MAX_GIOCATORI, RIGHE_PANCHINA_AGGIUNTIVA, RUOLI_PANCHINA, controlli,
                                distinte_stagione, elimina_distinta, etichetta, genera_pdf_distinta, ordinate,
                                salva_distinta, ultima_del_gruppo)
from nomi_file import nome_file_gara
from stagioni import gruppi_correnti
from utenti import gruppi_utente

NUOVA = "➕ Nuova distinta"
IN_CASA, FUORI = "🏠 In casa", "🚌 In trasferta"
ALTRA = "✏️ Altra competizione..."
NESSUNO = ""
VUOTA = "—"  # cella senza giocatore (o senza C/VC) nella tabella delle 20 righe


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
    massaggiatore = next((r["id"] for r in staff if "massagg" in (r.get("qualifica") or "").lower()), NESSUNO)
    return {"allenatore": allenatore, "accompagnatore": dirigente, "massaggiatore": massaggiatore}


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
    precedenti = sorted((g for g in base.get("giocatori", []) if g["id"] in persone),
                        key=lambda g: g.get("numero") or 99)
    # Etichette uniche per la tendina: nome, anno e (se di un'altra squadra) la squadra
    etichette, contate = {}, {}
    for r in giocabili:
        testo = f"{nome_completo(r)} ({anno_di(r) or '?'})" + \
            ("" if squadra_di[r["id"]] == gruppo else f" · {squadra_di[r['id']] or 'senza squadra'}")
        contate[testo] = contate.get(testo, 0) + 1
        etichette[r["id"]] = testo if contate[testo] == 1 else f"{testo} #{contate[testo]}"
    da_etichetta = {v: i for i, v in etichette.items()}
    # 20 righe come nel modulo: numero di maglia, giocatore scelto dalla tendina, C/VC. Ogni tendina mostra
    # solo i giocatori non ancora scelti nelle altre righe (e il C o il VC solo se nessun altro li ha).
    chiavi = [(f"cd_num_{k}_{r}", f"cd_gioc_{k}_{r}", f"cd_cap_{k}_{r}") for r in range(MAX_GIOCATORI)]
    for riga, (c_num, c_gioc, c_cap) in enumerate(chiavi):
        g = precedenti[riga] if riga < len(precedenti) else {}
        st.session_state.setdefault(c_num, g.get("numero") or riga + 1)
        gia = {st.session_state.get(c) for _, c, _ in chiavi[:riga]}
        st.session_state.setdefault(c_gioc, etichette.get(g.get("id"), VUOTA) if g.get("id") not in
                                    {da_etichetta.get(e) for e in gia} else VUOTA)
        st.session_state.setdefault(c_cap, g.get("cap") or VUOTA)
    scelti = [st.session_state[c_gioc] for _, c_gioc, _ in chiavi]
    fasce = [st.session_state[c_cap] for _, _, c_cap in chiavi]
    giocatori = []
    with st.container(key="cd_righe"):
        # Sul telefono le tre colonne restano affiancate e compatte (senza freccia nelle tendine piccole)
        st.html("<style>.st-key-cd_righe{gap:.35rem}"
                ".st-key-cd_righe [data-testid='stHorizontalBlock']{flex-wrap:nowrap;gap:.4rem}"
                ".st-key-cd_righe [data-testid='stColumn']{min-width:0 !important}"
                ".st-key-cd_righe input[role='combobox']{padding-left:.5rem;padding-right:0;min-width:0}"
                ".st-key-cd_righe [data-testid='stColumn']:not(:nth-child(2)) button[aria-haspopup]"
                "{padding:0 .15rem 0 0;width:auto}"
                ".st-key-cd_righe [data-testid='stColumn']:not(:nth-child(2)) button[aria-haspopup] svg"
                "{width:.9rem;height:.9rem}</style>")
        c1, c2, c3 = st.columns([1.3, 6, 1.4], vertical_alignment="bottom")
        c1.caption("N°")
        c2.caption("Giocatore")
        c3.caption("Cap.")
        for riga, (c_num, c_gioc, c_cap) in enumerate(chiavi):
            altri = set(scelti[:riga] + scelti[riga + 1:])
            fasce_altre = set(fasce[:riga] + fasce[riga + 1:])
            c1, c2, c3 = st.columns([1.3, 6, 1.4], vertical_alignment="bottom")
            numero = c1.selectbox("N°", list(range(1, 100)), key=c_num, label_visibility="collapsed")
            nome = c2.selectbox("Giocatore", [VUOTA] + [e for e in etichette.values() if e not in altri],
                                key=c_gioc, label_visibility="collapsed")
            cap = c3.selectbox("Cap.", [VUOTA] + [f for f in ("C", "VC") if f not in fasce_altre],
                               key=c_cap, label_visibility="collapsed")
            if nome in da_etichetta:
                giocatori.append({"id": da_etichetta[nome], "numero": int(numero),
                                  "cap": cap if cap in ("C", "VC") else ""})
    st.caption("Scegli il nome in ogni riga: chi è già in distinta non compare più nelle altre tendine. Il numero "
               "è quello di maglia; in Cap. metti C per il capitano e VC per il vice. Le righe vuote restano "
               "vuote nella stampa.")

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
    for posto, (chiave, etichetta_) in enumerate([ASSISTENTE] + RUOLI_PANCHINA + [MASSAGGIATORE]):
        if posto % 2 == 0:  # una riga per coppia: sul telefono restano nell'ordine del modulo
            colonne = st.columns(2)
        attuale = ruoli_base.get(chiave, NESSUNO)
        ruoli[chiave] = colonne[posto % 2].selectbox(
            etichetta_.replace(" Sig.", "").replace(" Dott.", ""), ids_staff, format_func=chi, key=f"cd_{chiave}_{k}",
            index=ids_staff.index(attuale) if attuale in ids_staff else 0)
    altri = RIGHE_PANCHINA_AGGIUNTIVA - (1 if ruoli.get(MASSAGGIATORE[0]) else 0)
    panchina = st.multiselect(f"Altri in panchina aggiuntiva (al massimo {altri})", ids_staff[1:],
                              default=[i for i in base.get("panchina", [])
                                       if i in ids_staff and i != ruoli.get(MASSAGGIATORE[0])][:altri],
                              max_selections=altri, format_func=chi, key=f"cd_panchina_{k}",
                              placeholder="Scegli dallo staff")

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
