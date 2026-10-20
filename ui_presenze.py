"""🏃 Allenamenti: l'allenatore segna chi c'era e vede le statistiche delle presenze.

Le sigle sono quelle delle tabelle del mister: C completo, P parziale, D differenziato, Z presenza (c'era ma
non si è allenato), A assente; in più I infortunato e G giustificato. Le tabelle già fatte (PDF o CSV)
si importano da qui. Un allenatore vede solo i gruppi squadra assegnati in ⚙️ Opzioni → 👥 Utenti;
segreteria e amministratori li vedono tutti. I ragazzi sono quelli dell'👦 Anagrafica nel gruppo dell'anno.
"""
from datetime import date

import pandas as pd
import streamlit as st

from anagrafica import (anno_di, data_da_iso, elenco_ragazzi, nome_completo, nuova_da_nome, ragazzi_del_gruppo,
                        salva_scheda, trova_per_nome)
from presenze import (IN_CAMPO, SIGLE, SIGLE_TABELLA, STATI, aggiungi_allenamenti, elimina_allenamento, etichetta_corta, giorno_di,
                      leggi_tabella, mesi_della_stagione, nel_periodo, numero_di, ordina, presenze_gruppo,
                      salva_allenamento, seduta, sposta_allenamento, statistiche, testo_da_file)
from stagioni import gruppi_correnti
from statistiche_pdf import genera_pdf_presenze
from utenti import gruppi_utente

NOMI = {"completo": "Completo", "parziale": "Parziale", "differenziato": "Differenziato",
        "presenza": "Presenza (non si allena)", "assente": "Assente", "infortunato": "Infortunato",
        "giustificato": "Giustificato"}
ETICHETTE = {s: f"{SIGLE[s]} · {NOMI[s]}" for s in STATI}
DA_ETICHETTA = {v: k for k, v in ETICHETTE.items()}
SIGLE_BASE = SIGLE_TABELLA
TUTTA, ALTRO = "Tutta la stagione", "Altro periodo..."
NUOVO, SALTA = "➕ Nuovo in anagrafica", "✖️ Non importare"


def _messaggio(tipo, testo):
    st.session_state["pres_messaggi"] = [(tipo, testo)]


def _gg(chiave):
    testo = data_da_iso(giorno_di(chiave)).strftime("%d/%m/%Y")
    return testo + (f" ({numero_di(chiave)}° allenamento)" if numero_di(chiave) > 1 else "")


def _riassunto(segnati):
    return " · ".join(f"{SIGLE[s]} {n}" for s in STATI if (n := sum(1 for v in segnati.values() if v == s)))


def render_presenze(utente, ruolo):
    st.subheader("🏃 Presenze allenamenti")
    for tipo, testo in st.session_state.pop("pres_messaggi", []):
        getattr(st, tipo)(testo)

    stagione, gruppi = gruppi_correnti()
    nomi_gruppi = [g["gruppo"] for g in gruppi]
    staff = ruolo in ("admin", "segreteria")
    miei = nomi_gruppi if staff else [g for g in gruppi_utente(utente) if g in nomi_gruppi]
    if not miei:
        st.info("Nessuna squadra disponibile: " + ("crea i gruppi squadra in ⚙️ Opzioni → 🏆 Campionati."
                if staff else "chiedi all'amministratore di assegnartene una in ⚙️ Opzioni → 👥 Utenti."))
        return
    gruppo = st.selectbox(f"👥 Squadra ({stagione})", miei, key="pres_gruppo")
    ragazzi = ragazzi_del_gruppo(stagione, gruppo)
    allenamenti = presenze_gruppo(stagione, gruppo)

    segna, numeri, importa = st.tabs(["✅ Segna presenze", "📈 Statistiche", "📥 Importa tabelle"])
    with segna:
        _segna(stagione, gruppo, ragazzi, allenamenti)
    with numeri:
        _statistiche(stagione, gruppo, ragazzi, allenamenti)
    with importa:
        _importa(stagione, gruppo, ragazzi, allenamenti)


def _segna(stagione, gruppo, ragazzi, allenamenti):
    if not ragazzi:
        st.info(f"Nessun ragazzo in 👦 Anagrafica nella squadra {gruppo} per il {stagione}.")
        return
    if "pres_apri" in st.session_state:  # dall'elenco: giorno e numero vanno scelti prima dei widget
        st.session_state["pres_giorno"], st.session_state["pres_numero"] = st.session_state.pop("pres_apri")
    oggi = date.today()
    st.session_state.setdefault("pres_giorno", oggi)
    st.session_state.setdefault("pres_numero", 1)
    c1, c2 = st.columns([3, 2])
    giorno = c1.date_input("📅 Allenamento del", max_value=oggi, format="DD/MM/YYYY", key="pres_giorno")
    numero = c2.selectbox("Del giorno", [1, 2, 3], key="pres_numero", format_func=lambda n: f"{n}° allenamento")
    chiave = seduta(giorno.strftime("%Y-%m-%d"), numero)
    gia = allenamenti.get(chiave)
    n = st.session_state.get("pres_n", 0)
    nuova = chiave
    if gia:
        st.info(f"✏️ Stai modificando l'allenamento del {_gg(chiave)}: cambia le sigle e salva.")
        sposta = st.date_input("Sposta a un altro giorno (se la data era sbagliata)", value=giorno, max_value=oggi,
                               format="DD/MM/YYYY", key=f"pres_sposta_{gruppo}_{chiave}_{n}")
        nuova = seduta(sposta.strftime("%Y-%m-%d"), numero)
        if nuova != chiave and nuova in allenamenti:
            st.warning(f"Il {_gg(nuova)} c'è già un allenamento: salvando verrà sostituito.")
    else:
        st.caption("Partono tutti con C (completo): cambia solo chi ha fatto altro.")
    righe = [{"Ragazzo": nome_completo(r),
              "Presenza": ETICHETTE[(gia or {}).get(r["id"], "completo" if not gia else "assente")]}
             for r in ragazzi]
    tabella = st.data_editor(
        pd.DataFrame(righe), hide_index=True, use_container_width=True, key=f"pres_tab_{gruppo}_{chiave}_{n}",
        disabled=["Ragazzo"], height=min(35 * len(righe) + 40, 640),
        column_config={"Presenza": st.column_config.SelectboxColumn(options=list(ETICHETTE.values()), required=True)})
    stati = [DA_ETICHETTA.get(v, "completo") for v in tabella["Presenza"]]
    segnati = {r["id"]: s for r, s in zip(ragazzi, stati)}
    st.caption(_riassunto(segnati) + " · C completo, P parziale, D differenziato, Z presenza, A assente, "
                                     "I infortunato, G giustificato")
    c1, c2 = st.columns(2)
    if c1.button("💾 Salva modifiche" if gia else "💾 Salva presenze", type="primary", use_container_width=True,
                 key="pres_salva"):
        if gia and nuova != chiave:
            sposta_allenamento(stagione, gruppo, chiave, nuova, segnati)
            st.session_state["pres_apri"] = (data_da_iso(giorno_di(nuova)), numero)
        else:
            salva_allenamento(stagione, gruppo, chiave, segnati)
        st.session_state["pres_n"] = n + 1
        in_campo = sum(1 for s in stati if s in IN_CAMPO)
        _messaggio("success", f"Allenamento del {_gg(nuova)} salvato: {in_campo} allenati su {len(stati)}.")
        st.rerun()
    if gia and c2.button("🗑️ Togli questo allenamento", use_container_width=True, key="pres_elimina"):
        elimina_allenamento(stagione, gruppo, chiave)
        st.session_state["pres_n"] = n + 1
        _messaggio("success", f"Allenamento del {_gg(chiave)} tolto.")
        st.rerun()

    if allenamenti:
        _salvati(stagione, allenamenti, chiave, n)


GIORNI = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def _salvati(stagione, allenamenti, aperta, n):
    """Gli allenamenti salvati in una tabella compatta, un mese alla volta; un tocco su una riga lo apre."""
    mesi = [m for m in mesi_della_stagione(stagione) if nel_periodo(allenamenti, m[1], m[2])]
    st.markdown(f"**🗓️ Allenamenti salvati ({len(allenamenti)})** · tocca una riga per modificarlo")
    etichette = [m[0] for m in reversed(mesi)] + [TUTTA]
    mese = st.selectbox("Mese", etichette, key="pres_salvati_mese", label_visibility="collapsed")
    dal, al = next(((m[1], m[2]) for m in mesi if m[0] == mese), (None, None))
    sedute = list(reversed(nel_periodo(allenamenti, dal, al)))
    righe = []
    for s in sedute:
        giorno = data_da_iso(giorno_di(s))
        riga = {"Data": f"{GIORNI[giorno.weekday()]} {giorno:%d/%m}" + (f" ({numero_di(s)}°)" if numero_di(s) > 1 else ""),
                "Allenati": sum(1 for v in allenamenti[s].values() if v in IN_CAMPO)}
        riga.update({SIGLE[k]: sum(1 for v in allenamenti[s].values() if v == k) for k in STATI})
        righe.append(riga)
    tabella = pd.DataFrame(righe)
    usate = [c for c in tabella.columns if c in ("Data", "Allenati") or tabella[c].sum()]
    scelta = st.dataframe(tabella[usate], hide_index=True, use_container_width=True, on_select="rerun",
                          selection_mode="single-row", key=f"pres_salvati_{mese}_{n}_{aperta}",
                          height=min(35 * len(righe) + 40, 320))
    if scelta.selection.rows:
        s = sedute[scelta.selection.rows[0]]
        if s != aperta:
            st.session_state["pres_apri"] = (data_da_iso(giorno_di(s)), numero_di(s))
            st.rerun()


def _periodo(stagione, allenamenti):
    """(etichetta, dal, al) scelti: un mese con allenamenti, tutta la stagione o date a piacere."""
    mesi = [m for m in mesi_della_stagione(stagione) if nel_periodo(allenamenti, m[1], m[2])]
    scelte = [TUTTA] + [m[0] for m in mesi] + [ALTRO]
    scelta = st.selectbox("🗓️ Periodo", scelte, key="pres_periodo")
    if scelta == TUTTA:
        return f"stagione {stagione}", None, None
    if scelta != ALTRO:
        return next(m for m in mesi if m[0] == scelta)
    c1, c2 = st.columns(2)
    dal = c1.date_input("Dal", value=data_da_iso(mesi_della_stagione(stagione)[0][1]), format="DD/MM/YYYY",
                        key="pres_dal")
    al = c2.date_input("Al", value=date.today(), format="DD/MM/YYYY", key="pres_al")
    return f"dal {dal:%d/%m/%Y} al {al:%d/%m/%Y}", dal.isoformat(), al.isoformat()


def _statistiche(stagione, gruppo, ragazzi, allenamenti):
    if not allenamenti:
        st.info("Ancora nessun allenamento segnato per questa squadra.")
        return
    periodo, dal, al = _periodo(stagione, allenamenti)
    sedute = nel_periodo(allenamenti, dal, al)
    if not sedute:
        st.info("Nessun allenamento in questo periodo.")
        return
    conti = statistiche(allenamenti, dal, al)
    schede = {r["id"]: r for r in elenco_ragazzi()}
    in_rosa = {r["id"] for r in ragazzi}
    nome_di = {i: nome_completo(schede[i]) if i in schede else "(scheda eliminata)" for i in conti}
    sigle = SIGLE_BASE + [SIGLE[s] for s in ("infortunato", "giustificato") if any(v[s] for v in conti.values())]
    ordine = sorted(conti, key=lambda i: nome_di[i])
    righe = []
    for i in ordine:
        v, scheda = conti[i], schede.get(i, {})
        riga = {"Ragazzo": nome_di[i] + ("" if i in in_rosa else " · non più in squadra"),
                "Anno": scheda.get("anno_nascita") or (scheda.get("nascita") or "")[:4]}
        for k in sigle:
            quante = v[next(s for s in STATI if SIGLE[s] == k)]
            riga[k], riga[f"{k}%"] = quante, round(100 * quante / v["segnati"]) if v["segnati"] else 0
        riga["Allenato %"] = v["percentuale"]
        righe.append(riga)
    in_campo = sum(v[s] for v in conti.values() for s in IN_CAMPO)
    segnati = sum(v["segnati"] for v in conti.values())
    m1, m2, m3 = st.columns(3)
    m1.metric("Numero allenamenti", len(sedute))
    m2.metric("Allenati in media", f"{round(100 * in_campo / segnati) if segnati else 0}%")
    m3.metric("Completi", f"{round(100 * sum(v['completo'] for v in conti.values()) / segnati) if segnati else 0}%")
    percentuali = {f"{k}%": st.column_config.NumberColumn(format="%d%%") for k in sigle}
    st.dataframe(pd.DataFrame(righe), hide_index=True, use_container_width=True,
                 height=min(35 * len(righe) + 40, 760),
                 column_config={**percentuali, "Allenato %": st.column_config.ProgressColumn(
                     format="%d%%", min_value=0, max_value=100)})
    st.caption("C completo · A assente · P parziale · D differenziato · Z presenza (c'era ma non si è allenato)"
               + (" · I infortunato · G giustificato" if len(sigle) > 5 else "")
               + ". Allenato % conta C, P e D.")
    with st.expander(f"🔎 Allenamento per allenamento ({len(sedute)})"):
        griglia = pd.DataFrame([{"Ragazzo": nome_di[i], **{etichetta_corta(s): SIGLE.get(allenamenti[s].get(i), "")
                                                            for s in sedute}} for i in ordine])
        st.dataframe(griglia, hide_index=True, use_container_width=True)

    firma = (gruppo, periodo, tuple(sedute), segnati, in_campo)
    if st.button("🖨️ Prepara il PDF come la tabella del mister", key="pres_pdf"):
        tabella = [(nome_di[i], r["Anno"], [SIGLE.get(allenamenti[s].get(i), "") for s in sedute])
                   for i, r in zip(ordine, righe)]
        st.session_state["pres_pdf_pronto"] = (firma, genera_pdf_presenze(
            gruppo, stagione, periodo, tabella, [etichetta_corta(s) for s in sedute], sigle))
    pronto = st.session_state.get("pres_pdf_pronto")
    if pronto and pronto[0] == firma:
        st.download_button("⬇️ Scarica il PDF", pronto[1], mime="application/pdf", key="pres_pdf_scarica",
                           file_name=f"presenze_{gruppo}_{periodo}.pdf".replace(" ", "_").replace("/", "-"))


def _importa(stagione, gruppo, ragazzi, allenamenti):
    st.caption("Carica le tabelle delle presenze già fatte dal mister (PDF o CSV esportati dal suo foglio, con le "
               "colonne NOME E COGNOME, ANNO, le date e le sigle C, A, P, D, Z). Gli allenamenti con la stessa "
               "data vengono sostituiti.")
    n = st.session_state.get("pres_imp_n", 0)
    files = st.file_uploader("Tabelle del mister", type=["pdf", "csv", "txt"], accept_multiple_files=True,
                             key=f"pres_imp_{n}")
    if not files:
        return
    tabelle = []
    for f in files:
        try:
            tabelle.append((f.name, leggi_tabella(testo_da_file(f.name, f.getvalue()), stagione)))
        except Exception as e:  # PDF rovinato o non di testo
            st.error(f"{f.name}: non riesco a leggerlo ({e}).")
    tutti = elenco_ragazzi()
    preferiti = {r["id"] for r in ragazzi}
    nomi, sedute, problemi = [], {}, []
    for nome_file, t in tabelle:
        if not t["sedute"]:
            problemi.append(f"{nome_file}: non trovo la riga con le date (es. 01-set).")
            continue
        if t["stagione"] != stagione:
            problemi.append(f"{nome_file}: è della stagione {t['stagione']}, non della {stagione}.")
            continue
        problemi += [f"{nome_file}: {p}" for p in t["problemi"]]
        for nome, anno, stati in t["righe"]:
            if (nome, anno) not in nomi:
                nomi.append((nome, anno))
            for chiave, stato in zip(t["sedute"], stati):
                sedute.setdefault(chiave, {})[(nome, anno)] = stato
    for p in problemi:
        st.warning(p)
    if not sedute:
        return

    # Abbinamenti: proposti in automatico, si possono correggere a mano
    etichette, contate = {}, {}
    for r in sorted(tutti, key=nome_completo):
        base = f"{nome_completo(r)} ({anno_di(r) or '?'})"
        contate[base] = contate.get(base, 0) + 1
        etichette[r["id"]] = base if contate[base] == 1 else f"{base} #{contate[base]}"
    da_id = {v: k for k, v in etichette.items()}
    proposti = {k: trova_per_nome(k[0], k[1], tutti, preferiti) for k in nomi}
    tabella = pd.DataFrame([{"Nella tabella": f"{n_} ({a})" if a else n_,
                             "In anagrafica": etichette[r["id"]] if r else NUOVO} for (n_, a), r in proposti.items()])
    gia = [s for s in sedute if s in allenamenti]
    st.markdown(f"**{len(sedute)} allenamenti** dal {_gg(min(sedute))} al {_gg(max(sedute))} · {len(nomi)} ragazzi"
                + (f" · {len(gia)} allenamenti già presenti verranno sostituiti" if gia else ""))
    st.caption(f"Controlla gli abbinamenti con l'anagrafica. {NUOVO} crea la scheda nella squadra {gruppo}; "
               f"{SALTA} non importa le sue presenze.")
    scelte = st.data_editor(
        tabella, hide_index=True, use_container_width=True, disabled=["Nella tabella"], key=f"pres_imp_abb_{n}",
        height=min(35 * len(tabella) + 40, 700),
        column_config={"In anagrafica": st.column_config.SelectboxColumn(
            options=[NUOVO, SALTA] + list(etichette.values()), required=True)})
    scelto = dict(zip(nomi, scelte["In anagrafica"]))
    avvisi = [f"{n_} ({a}) → {v}" for (n_, a), v in scelto.items() if v in da_id and a and f"({a})" not in v]
    if avvisi:
        st.warning("Anno di nascita diverso, controlla che sia la stessa persona: " + "; ".join(avvisi))
    doppi = [v for v in set(scelto.values()) if v in da_id and list(scelto.values()).count(v) > 1]
    if doppi:
        st.error("Lo stesso ragazzo è abbinato a più righe: " + ", ".join(doppi))
    if st.button("📥 Importa gli allenamenti", type="primary", key="pres_imp_ok", disabled=bool(doppi)):
        schede = {r["id"]: r for r in tutti}
        abbinati, nuovi = {}, 0
        for k, v in scelto.items():
            if v == SALTA:
                continue
            if v == NUOVO:
                abbinati[k] = nuova_da_nome(k[0], k[1], stagione, gruppo)
                nuovi += 1
                continue
            r = schede[da_id[v]]
            if not (r.get("gruppi") or {}).get(stagione):
                r = salva_scheda({**r, "gruppi": {**(r.get("gruppi") or {}), stagione: gruppo}})
            abbinati[k] = r
        da_scrivere = {s: {abbinati[k]["id"]: v for k, v in segnati.items() if k in abbinati}
                       for s, segnati in sedute.items()}
        aggiungi_allenamenti(stagione, gruppo, da_scrivere)
        st.session_state["pres_imp_n"] = n + 1
        _messaggio("success", f"Importati {len(da_scrivere)} allenamenti"
                   + (f" e {'aggiunto 1 ragazzo' if nuovi == 1 else f'aggiunti {nuovi} ragazzi'} in anagrafica"
                      if nuovi else "") + ".")
        st.rerun()
