"""📝 Crea distinta: si scelgono partita, giocatori e persone in panchina dall'anagrafica e si stampa la
distinta ufficiale sul modello della società. Le distinte si salvano per riaprirle e ristamparle; una
nuova riparte dall'ultima della stessa squadra (stessi giocatori, numeri e dirigenti). Dal calendario
del Comitato si preparano in un colpo le distinte vuote di tutte le partite.
"""
import time
from datetime import date

import streamlit as st

from anagrafica import anno_di, data_da_iso, e_calciatore, elenco_ragazzi, nome_completo, tipo_di
from calendario import distinte_da_calendario, leggi_calendario, nostra_squadra, partite_di, squadre
from distinta_ufficiale import (ASSISTENTE, MASSAGGIATORE, MAX_GIOCATORI, RIGHE_PANCHINA_AGGIUNTIVA, RUOLI_PANCHINA, controlli,
                                distinte_stagione, elimina_distinta, etichetta, genera_pdf_distinta, in_elenco,
                                in_scadenza, salva_distinta, salva_distinte, ultima_del_gruppo)
from disciplina import DIFFIDATO, partite_della_competizione, per_persona, situazione, tipo_competizione
from presenze import nel_periodo, presenze_gruppo, statistiche
from nomi_file import nome_file_gara
import squalifiche
from stagioni import gruppi_correnti
from utenti import gruppi_utente

NUOVA = "➕ Nuova distinta"
IN_CASA, FUORI = "🏠 In casa", "🚌 In trasferta"
ALTRA = "✏️ Altra competizione..."
NESSUNO = ""
VUOTA = "—"  # cella senza giocatore (o senza C/VC) nella tabella delle 20 righe
ULTIMI_ALLENAMENTI = 12  # la % accanto ai nomi: gli ultimi allenamenti prima della partita (circa 4 settimane)


def _partite_giocate():
    """Le partite della Cronaca (archivio e aperta), rilette al massimo ogni 5 minuti: servono per i cartellini."""
    salvate = st.session_state.get("cd_partite")
    if not salvate or time.time() - salvate[0] > 300:
        from ui_statistiche import _partite
        salvate = (time.time(), _partite())
        st.session_state["cd_partite"] = salvate
    return salvate[1]


def _messaggio(tipo, testo):
    st.session_state["cd_messaggi"] = [(tipo, testo)]


def _base(scelta, distinte, gruppo, nome_squadra):
    """La distinta da cui partire: quella aperta, oppure per una nuova l'ultima della squadra senza i dati
    della partita (avversario, data, campo cambiano ogni volta)."""
    if scelta != NUOVA:
        if st.session_state.get("cd_riprendi") == scelta and not distinte[scelta].get("giocatori"):
            # distinta ancora vuota: giocatori e numeri dall'ultima che li ha
            prima = ultima_del_gruppo(distinte, gruppo, distinte[scelta].get("data") or "9999", scelta) or {}
            return {**distinte[scelta], "giocatori": prima.get("giocatori", [])}
        return distinte[scelta]
    ultima = ultima_del_gruppo(distinte, gruppo) or {}
    return {"gruppo": gruppo, "squadra": ultima.get("squadra") or nome_squadra, "in_casa": True,
            "competizione": ultima.get("competizione", ""), "giocatori": ultima.get("giocatori", []),
            **({"ruoli": ultima["ruoli"]} if "ruoli" in ultima else {}), "panchina": ultima.get("panchina", [])}


def _svuota(k, chiavi):
    """Prima del disegno della pagina: righe dei giocatori, C/VC e tutta la panchina (anche allenatore e dirigente
    accompagnatore) tornano vuote."""
    for c_gioc, c_cap in chiavi:
        st.session_state[c_gioc] = VUOTA
        st.session_state[c_cap] = VUOTA
    for chiave, _ in [ASSISTENTE] + RUOLI_PANCHINA + [MASSAGGIATORE]:
        st.session_state[f"cd_{chiave}_{k}"] = NESSUNO
    st.session_state[f"cd_panchina_{k}"] = []
    _messaggio("info", "Distinta svuotata: scegli i giocatori e salva.")


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
    _render_calendario(stagione, gruppi, miei, distinte, staff, utente, nome_societa)
    # in ordine di data e ora della partita (non di inserimento o importazione)
    elenco = sorted((d for d in distinte.values() if d.get("gruppo") in miei),
                    key=lambda d: (d.get("data") or "9999", d.get("ora") or "", d.get("gruppo", "")))
    if "cd_apri" in st.session_state:  # dopo il salvataggio di una nuova: resta aperta quella
        st.session_state["cd_scelta"] = st.session_state.pop("cd_apri")
    if st.session_state.get("cd_scelta") not in [NUOVA] + [d["id"] for d in elenco]:
        st.session_state["cd_scelta"] = NUOVA
    scelta = st.selectbox("📂 Distinta", [NUOVA] + [d["id"] for d in elenco], key="cd_scelta",
                          format_func=lambda i: i if i == NUOVA else f"{etichetta(distinte[i])} · {distinte[i]['gruppo']}"
                          + ("" if distinte[i].get("giocatori") else " · da compilare"))
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
    # Presenza agli ultimi allenamenti prima della partita, per scegliere i convocati
    allenamenti = presenze_gruppo(stagione, gruppo)
    ultimi = nel_periodo(allenamenti, al=giorno.isoformat() if giorno else None)[-ULTIMI_ALLENAMENTI:]
    allenato = statistiche({s: allenamenti[s] for s in ultimi})
    # Diffidati e squalificati per questa partita, dai cartellini segnati in Cronaca nella stessa competizione
    giocate = partite_della_competizione(_partite_giocate(), (squadra, nome_societa), stagione, gruppo, comp,
                                         giorno.isoformat() if giorno else "")
    disciplina = per_persona(situazione(giocate), {r["id"]: r for r in giocabili})
    # Le squalifiche segnate dal Comunicato valgono più del conto dai cartellini
    elenco_squalifiche = squalifiche.elenco()
    giorno_iso = giorno.isoformat() if giorno else ""
    disciplina.update(squalifiche.per_partita(elenco_squalifiche, stagione, gruppo, tipo_competizione(comp),
                                              giocate, giorno_iso))
    # Nella tendina: nome, anno, % di allenamenti, diffida o squalifica e (se di un'altra squadra) la squadra
    etichette = {}
    for r in giocabili:
        v = allenato.get(r["id"])
        d = disciplina.get(r["id"])
        etichette[r["id"]] = f"{nome_completo(r)} ({anno_di(r) or '?'})" + \
            (f" · 🏃 {v['percentuale']}%" if v and v["segnati"] else "") + \
            ((" · ⚠️ diffidato" if d[0] == DIFFIDATO else " · ⛔ squalificato") if d else "") + \
            ("" if squadra_di[r["id"]] == gruppo else f" · {squadra_di[r['id']] or 'senza squadra'}")
    # 20 righe come nel modulo, numerate da 1 a 20 (il numero è quello di maglia): giocatore scelto dalla
    # tendina e C/VC. Ogni tendina mostra solo i giocatori non ancora scelti nelle altre righe (e il C o il VC
    # solo se nessun altro li ha).
    chiavi = [(f"cd_gioc_{k}_{r}", f"cd_cap_{k}_{r}") for r in range(MAX_GIOCATORI)]
    per_riga = {}
    for g in precedenti:  # ognuno alla riga del suo numero; chi ha un numero oltre il 20 nelle righe libere
        if isinstance(g.get("numero"), int) and 1 <= g["numero"] <= MAX_GIOCATORI and g["numero"] - 1 not in per_riga:
            per_riga[g["numero"] - 1] = g
    for g in precedenti:
        if g not in per_riga.values():
            libera = next((r for r in range(MAX_GIOCATORI) if r not in per_riga), None)
            if libera is not None:
                per_riga[libera] = g
    for riga, (c_gioc, c_cap) in enumerate(chiavi):
        g = per_riga.get(riga, {})
        gia = {st.session_state.get(c) for c, _ in chiavi[:riga]}
        st.session_state.setdefault(c_gioc, g["id"] if g.get("id") in etichette and g["id"] not in gia else VUOTA)
        if st.session_state[c_gioc] not in etichette:  # tolto dall'anagrafica nel frattempo
            st.session_state[c_gioc] = VUOTA
        st.session_state.setdefault(c_cap, g.get("cap") or VUOTA)
    scelti = [st.session_state[c_gioc] for c_gioc, _ in chiavi]
    fasce = [st.session_state[c_cap] for _, c_cap in chiavi]
    giocatori = []
    with st.container(key="cd_righe"):
        # Sul telefono le tre colonne restano affiancate e compatte (senza freccia nelle tendine piccole)
        st.html("<style>.st-key-cd_righe{gap:.35rem}"
                ".st-key-cd_righe [data-testid='stHorizontalBlock']{flex-wrap:nowrap;gap:.4rem}"
                ".st-key-cd_righe [data-testid='stColumn']{min-width:0 !important}"
                ".st-key-cd_righe input[role='combobox']{padding-left:.5rem;padding-right:0;min-width:0}"
                ".st-key-cd_righe [data-testid='stColumn']:first-child p{text-align:center;margin:0}"
                ".st-key-cd_righe [data-testid='stColumn']:not(:nth-child(2)) button[aria-haspopup]"
                "{padding:0 .15rem 0 0;width:auto}"
                ".st-key-cd_righe [data-testid='stColumn']:not(:nth-child(2)) button[aria-haspopup] svg"
                "{width:.9rem;height:.9rem}</style>")
        c1, c2, c3 = st.columns([0.7, 6, 1.4], vertical_alignment="center")
        c1.caption("N°")
        c2.caption("Giocatore")
        c3.caption("Cap.")
        for riga, (c_gioc, c_cap) in enumerate(chiavi):
            altri = set(scelti[:riga] + scelti[riga + 1:])
            fasce_altre = set(fasce[:riga] + fasce[riga + 1:])
            c1, c2, c3 = st.columns([0.7, 6, 1.4], vertical_alignment="center")
            c1.markdown(f"**{riga + 1}**")
            scelto = c2.selectbox("Giocatore", [VUOTA] + [i for i in etichette if i not in altri], key=c_gioc,
                                  format_func=lambda i: etichette.get(i, VUOTA), label_visibility="collapsed")
            cap = c3.selectbox("Cap.", [VUOTA] + [f for f in ("C", "VC") if f not in fasce_altre],
                               key=c_cap, label_visibility="collapsed")
            if scelto in etichette:
                giocatori.append({"id": scelto, "numero": riga + 1,
                                  "cap": cap if cap in ("C", "VC") else ""})
    st.caption("Scegli il nome nella riga del suo numero di maglia: chi è già in distinta non compare più nelle "
               "altre tendine. In Cap. metti C per il capitano e VC per il vice. Le righe vuote restano vuote nella "
               "stampa."
               + (f" 🏃 è la presenza agli ultimi {len(ultimi)} allenamenti prima della partita." if ultimi else ""))
    if giocatori or any(st.session_state.get(f"cd_{c}_{k}") for c, _ in [ASSISTENTE] + RUOLI_PANCHINA + [MASSAGGIATORE]) \
            or st.session_state.get(f"cd_panchina_{k}"):
        st.button("🧹 Svuota giocatori e panchina", key=f"cd_svuota_{k}", on_click=_svuota, args=(k, chiavi),
                  help="Toglie tutti i giocatori, capitano e vice, e tutte le persone in panchina, "
                       "allenatore e dirigente compresi. I dati della partita restano. Finché non salvi, la distinta salvata non cambia.")
    if scelta != NUOVA and not giocatori and ultima_del_gruppo(distinte, gruppo, distinte[scelta].get("data") or "9999",
                                                              scelta):
        if st.button("📋 Riprendi giocatori e numeri dall'ultima distinta", key=f"cd_riprendi_{k}"):
            st.session_state["cd_riprendi"] = scelta
            st.session_state["cd_n"] = n + 1
            st.rerun()

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

    # una distinta salvata con la panchina vuota (🧹 Svuota) resta vuota: la proposta vale solo per le nuove
    ruoli_base = base["ruoli"] if "ruoli" in base else _proposta_ruoli(staff, gruppo, stagione)
    ruoli = {}
    for posto, (chiave, etichetta_) in enumerate([ASSISTENTE] + RUOLI_PANCHINA + [MASSAGGIATORE]):
        if posto % 2 == 0:  # una riga per coppia: sul telefono restano nell'ordine del modulo
            colonne = st.columns(2)
        attuale = ruoli_base.get(chiave, NESSUNO)
        ruoli[chiave] = colonne[posto % 2].selectbox(
            etichetta_.replace(" Sig.", "").replace(" Dott.", ""), ids_staff, format_func=chi, key=f"cd_{chiave}_{k}",
            index=ids_staff.index(attuale) if attuale in ids_staff and f"cd_{chiave}_{k}" not in st.session_state else 0)
    altri = RIGHE_PANCHINA_AGGIUNTIVA - (1 if ruoli.get(MASSAGGIATORE[0]) else 0)
    panchina = st.multiselect(f"Altri in panchina aggiuntiva (al massimo {altri})", ids_staff[1:],
                              default=None if f"cd_panchina_{k}" in st.session_state else
                              [i for i in base.get("panchina", []) if i in ids_staff and i != ruoli.get(MASSAGGIATORE[0])][:altri],
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
                "giornata": base.get("giornata", ""),
                "autore": base.get("autore") or utente}

    # --- Controlli, salvataggio e stampa
    problemi = controlli(distinta, persone)
    if problemi:
        with st.expander(f"⚠️ Da controllare prima di stampare ({len(problemi)})", expanded=True):
            for p in problemi:
                st.markdown(f"- {p}")
    in_distinta = [(persone[g["id"]], disciplina[g["id"]]) for g in giocatori if g["id"] in disciplina]
    squalificati = [(r, d) for r, d in in_distinta if d[0] != DIFFIDATO]
    if squalificati:
        st.error("⛔ Squalificati per questa partita:\n" + "\n".join(f"- **{nome_completo(r)}**: {d[1]}"
                                                                    for r, d in squalificati))
    diffidati = [(r, d) for r, d in in_distinta if d[0] == DIFFIDATO]
    if diffidati:
        with st.expander(f"⚠️ Diffidati ({len(diffidati)})"):
            for r, d in diffidati:
                st.markdown(f"- {nome_completo(r)}: {d[1]}")
    if in_distinta:
        st.caption("Calcolati dai cartellini segnati in 🎙️ Cronaca nella stessa competizione e dalle squalifiche "
                   "segnate dal Comunicato: fa fede il Comunicato Ufficiale.")
    _render_squalifiche(elenco_squalifiche, persone, giocabili, stagione, gruppo, comp, giocate, giorno_iso, utente)
    avvisi = in_scadenza(distinta, persone)
    if avvisi:
        with st.expander(f"⏰ Da rinnovare a breve ({len(avvisi)})"):
            for a in avvisi:
                st.markdown(f"- {a}")
            st.caption("Validi il giorno della gara, ma scadono entro un mese: tutte le scadenze sono in 👦 Anagrafica.")
    c1, c2 = st.columns(2)
    if c1.button("💾 Salva", width="stretch", key=f"cd_salva_{k}", disabled=not avversario.strip()):
        salvata = salva_distinta(stagione, distinta)
        st.session_state["cd_apri"] = salvata["id"]
        st.session_state["cd_n"] = n + 1
        _messaggio("success", f"Distinta {etichetta(salvata)} salvata.")
        st.rerun()
    if c2.button("🖨️ Salva e prepara il PDF", type="primary", width="stretch", key=f"cd_pdf_{k}",
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
                           type="primary", width="stretch", key="cd_scarica")
        st.caption("Stampala e falla firmare al dirigente accompagnatore. Se cambi qualcosa, prepara di nuovo il PDF.")

    if scelta != NUOVA:
        if st.session_state.get("cd_elimina") == scelta:
            st.warning(f"Eliminare la distinta {etichetta(distinte[scelta])}?")
            c1, c2 = st.columns(2)
            if c1.button("🗑️ Sì, elimina", type="primary", width="stretch", key="cd_elimina_si"):
                elimina_distinta(stagione, scelta)
                st.session_state.pop("cd_elimina", None)
                st.session_state["cd_n"] = n + 1
                _messaggio("success", "Distinta eliminata.")
                st.rerun()
            if c2.button("Annulla", width="stretch", key="cd_elimina_no"):
                st.session_state.pop("cd_elimina", None)
                st.rerun()
        elif st.button("🗑️ Elimina questa distinta", key="cd_elimina_btn"):
            st.session_state["cd_elimina"] = scelta
            st.rerun()


def _render_squalifiche(elenco, persone, giocabili, stagione, gruppo, comp, giocate, giorno, utente):
    """⚖️ Le squalifiche del Comunicato per questa squadra: quante giornate restano a questa partita, e il modulo
    per segnarne una nuova (a giornate o a tempo)."""
    tipo = tipo_competizione(comp)
    date_giocate = [d for d, _ in giocate]
    mie = [s for s in elenco if s.get("stagione") == stagione and s["persona"] in persone
           and (s.get("gruppo") == gruppo or s.get("fino_al"))]
    attive = [s for s in mie if (s.get("fino_al") or s.get("tipo") == tipo)
              and squalifiche._data_iso(s.get("data_cu")) < squalifiche._data_iso(giorno)
              and squalifiche.restano(s, date_giocate, giorno)]
    with st.expander(f"⚖️ Squalifiche dal Comunicato ({len(attive)} da scontare)" if attive
                     else "⚖️ Squalifiche dal Comunicato"):
        st.caption("Quando il Giudice Sportivo dà più giornate (o una squalifica a tempo), segnala qui: le giornate "
                   "si contano sulle partite di questa squadra e competizione segnate in 🎙️ Cronaca dopo la data "
                   "del Comunicato.")
        for s in sorted(mie, key=lambda s: s.get("data_cu", ""), reverse=True):
            r = persone[s["persona"]]
            if s.get("fino_al"):
                durata = f"fino al {squalifiche._gg_mm(s['fino_al'])}"
            else:
                durata = f"{s['giornate']} giornat{'a' if s['giornate'] == 1 else 'e'} in {s.get('tipo', 'campionato')}"
            if s.get("tipo") != tipo and not s.get("fino_al"):
                esito = "vale per l'altra competizione"
            elif squalifiche._data_iso(s.get("data_cu")) >= squalifiche._data_iso(giorno):
                esito = "Comunicato dopo questa partita"
            else:
                n = squalifiche.restano(s, date_giocate, giorno)
                esito = (f"⛔ resta da scontare questa{' e altre ' + str(n - 1) if n > 1 else ''}"
                         if n and not s.get("fino_al") else "⛔ squalificato" if n else "✅ scontata")
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"**{nome_completo(r)}**: {durata}, Comunicato del {squalifiche._gg_mm(s['data_cu'])} · {esito}")
            if c2.button("🗑️", key=f"cd_sq_del_{s['id']}", help="Elimina questa squalifica"):
                squalifiche.elimina(s["id"])
                st.rerun()
        st.markdown("**➕ Segna una squalifica**")
        nomi = {r["id"]: nome_completo(r) for r in giocabili}
        chi = st.selectbox("Giocatore", list(nomi), format_func=nomi.get, index=None,
                           placeholder="Scegli il giocatore", key="cd_sq_chi")
        c1, c2 = st.columns(2)
        data_cu = c1.date_input("Data del Comunicato", value=date.today(), format="DD/MM/YYYY", key="cd_sq_cu")
        modo = c2.segmented_control("Squalifica", ["📅 A giornate", "⏳ A tempo"], default="📅 A giornate",
                                    required=True, key="cd_sq_modo")
        c1, c2 = st.columns(2)
        if modo == "⏳ A tempo":
            fino = c1.date_input("Fino al (compreso)", value=None, format="DD/MM/YYYY", key="cd_sq_fino")
            giornate = 0
        else:
            fino = None
            giornate = c1.number_input("Giornate", min_value=1, max_value=50, value=1, step=1, key="cd_sq_gg")
            tipo = c2.selectbox("Competizione", ["campionato", "coppa"], index=0 if tipo == "campionato" else 1,
                                format_func=str.capitalize, key="cd_sq_tipo")
        if st.button("⚖️ Segna squalifica", key="cd_sq_salva",
                     disabled=not chi or not data_cu or (modo == "⏳ A tempo" and not fino)):
            squalifiche.aggiungi(chi, stagione, gruppo, tipo, data_cu.isoformat(), giornate,
                                 fino.isoformat() if fino else "", utente)
            st.session_state["cd_messaggi"] = [("success", f"⚖️ Squalifica di {nomi[chi]} segnata.")]
            for chiave in ("cd_sq_chi", "cd_sq_fino"):
                st.session_state.pop(chiave, None)
            st.rerun()


def _render_calendario(stagione, gruppi, miei, distinte, staff, utente, nome_societa):
    """Dal PDF del calendario del Comitato: una distinta vuota (partita, data, ora e campo già scritti) per
    ogni partita della nostra squadra. Le partite che hanno già una distinta si saltano."""
    with st.expander("📅 Prepara le distinte dal calendario"):
        st.caption("Carica il PDF del calendario gare del Comitato: preparo una distinta per ogni partita della "
                   "squadra, con avversario, data, ora e campo. I giocatori si scelgono poi partita per partita.")
        f = st.file_uploader("Calendario (PDF)", type=["pdf"], key="cd_cal_file")
        if f is None:
            return
        try:
            cal = leggi_calendario(f.getvalue())
        except Exception as e:
            st.error(f"Non riesco a leggere il calendario: {e}")
            return
        if not cal["partite"]:
            st.error("Nel PDF non ho trovato le giornate: serve il calendario gare del Comitato (LND).")
            return
        st.success(f"{cal['titolo'] or 'Calendario'}: {2 * max(p['giornata'] for p in cal['partite'])} giornate, "
                   f"{len(squadre(cal))} squadre.")
        c1, c2 = st.columns(2)
        gruppo = c1.selectbox(f"👥 Squadra ({stagione})", miei, key="cd_cal_gruppo")
        elenco_squadre = squadre(cal)
        noi = nostra_squadra(cal, nome_societa)
        nostra = c2.selectbox("Noi nel calendario", elenco_squadre, key="cd_cal_noi",
                              index=elenco_squadre.index(noi) if noi in elenco_squadre else 0)
        competizioni = next((g["competizioni"] for g in gruppi if g["gruppo"] == gruppo), []) or [cal["titolo"]]
        comp = st.selectbox("Valevole per", competizioni, key=f"cd_cal_comp_{gruppo}")
        da_oggi = st.toggle("Solo le partite ancora da giocare", value=True, key="cd_cal_da_oggi")
        partite = partite_di(cal, nostra, date.today().isoformat() if da_oggi else "")
        ultima = ultima_del_gruppo(distinte, gruppo) or {}
        modello = {"gruppo": gruppo, "squadra": ultima.get("squadra") or nome_societa, "competizione": comp,
                   "ruoli": ultima.get("ruoli") or _proposta_ruoli(staff, gruppo, stagione), "autore": utente}
        righe, nuove, per_riga = distinte_da_calendario(cal, nostra, partite, modello, distinte)
        if not righe:
            st.info(f"Nessuna partita di {nostra} da preparare.")
            return
        st.caption("Tocca una partita per prepararne la distinta, oppure creale tutte insieme.")
        tabella = st.dataframe(righe, hide_index=True, width="stretch", on_select="rerun",
                               selection_mode="single-row", key=f"cd_cal_tab_{gruppo}_{nostra}")
        selezionate = tabella.selection.rows if tabella else []
        c1, c2 = st.columns(2)
        if c1.button("✏️ Prepara la partita scelta", type="primary", width="stretch",
                     disabled=not selezionate, key="cd_cal_una"):
            scelta = per_riga[selezionate[0]]
            if isinstance(scelta, dict):  # ancora da creare: si crea solo questa
                scelta = salva_distinta(stagione, scelta)["id"]
            st.session_state["cd_apri"] = scelta
            _messaggio("success", f"Aperta la partita del {righe[selezionate[0]]['Data']} "
                                  f"({righe[selezionate[0]]['Avversario']}): scegli i giocatori qui sotto, sotto "
                                  "📂 Distinta, e salva.")
            st.session_state["cd_n"] = st.session_state.get("cd_n", 0) + 1
            st.rerun()
        if c2.button(f"📅 Crea tutte ({len(nuove)})", width="stretch", disabled=not nuove, key="cd_cal_crea"):
            salvate = salva_distinte(stagione, nuove)
            st.session_state["cd_apri"] = min(salvate, key=lambda d: d["data"])["id"]  # apre la prossima partita
            st.session_state["cd_n"] = st.session_state.get("cd_n", 0) + 1
            _messaggio("success", f"Preparate {len(nuove)} distinte: le trovi nell'elenco 📂 Distinta (qui è aperta "
                                  "la prossima partita). Scegli i giocatori e salva.")
            st.rerun()


def render_prendi_da_crea_distinta():
    """Nella 📋 Distinta: la nostra lista presa da una distinta preparata in 📝 Crea distinta, al posto della
    scansione della nostra foto. Restituisce (lato, griglia, campionato, dati della gara) quando si preme
    il pulsante, altrimenti None."""
    from estrattore import data_con_ora
    from rose import griglia_convocati
    stagione, _ = gruppi_correnti()
    distinte = distinte_stagione(stagione)
    pronte = [d for d in in_elenco(distinte, date.today().isoformat()) if d.get("giocatori")]
    if not pronte:
        return None
    with st.expander("📝 Prendi la nostra lista da Crea distinta (senza scansione)"):
        scelta = st.selectbox("Distinta", [d["id"] for d in pronte], key="prendi_cd",
                              format_func=lambda i: f"{etichetta(distinte[i])} · {distinte[i].get('gruppo', '')}")
        d = distinte[scelta]
        persone = {r["id"]: r for r in elenco_ragazzi()}
        giocatori = [{"giocatore": nome_completo(persone[g["id"]]) + (f" ({g['cap']})" if g.get("cap") else ""),
                      "anno": anno_di(persone[g["id"]]), "numero": g.get("numero")}
                     for g in d["giocatori"] if g["id"] in persone]
        st.caption(f"{len(giocatori)} giocatori. L'altra squadra si compila come sempre: foto, CSV o a mano.")
        if st.button("✅ Metti nella distinta", type="primary", width="stretch", key="prendi_cd_ok"):
            lato = "casa" if d.get("in_casa", True) else "ospite"
            ruoli = d.get("ruoli") or {}

            def nome(chiave):
                return nome_completo(persone[ruoli[chiave]]) if ruoli.get(chiave) in persone else ""
            giorno = data_da_iso(d.get("data"))
            numero_giornata = "".join(c for c in str(d.get("giornata", "")).split("ª")[0] if c.isdigit())
            gara = {"data": data_con_ora(f"{giorno:%d/%m/%Y}" if giorno else "", d.get("ora", "")),
                    "giornata": numero_giornata, "nome_casa": d.get("casa", ""), "nome_ospite": d.get("ospite", ""),
                    f"all_{lato}": nome("allenatore"), f"ass_{lato}": nome("assistente")}
            return lato, griglia_convocati(giocatori, []), d.get("competizione", ""), gara
    return None
