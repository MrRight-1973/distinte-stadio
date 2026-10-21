"""🏃 Allenamenti: l'allenatore segna chi c'era e vede le statistiche delle presenze.

Le sigle sono quelle delle tabelle del mister: C completo, P parziale, D differenziato, Z presenza (c'era ma
non si è allenato), A assente; in più I infortunato e G giustificato. Le tabelle già fatte (PDF o CSV)
si importano da qui. Un allenatore vede solo i gruppi squadra assegnati in ⚙️ Opzioni → 👥 Utenti;
segreteria e amministratori li vedono tutti. I ragazzi sono quelli dell'👦 Anagrafica nel gruppo dell'anno.
"""
import html
from datetime import date

import pandas as pd
import streamlit as st

from anagrafica import (anno_di, calciatori, data_da_iso, elenco_ragazzi, nome_completo, nuova_da_nome, ragazzi_del_gruppo,
                        salva_scheda, trova_per_nome)
from presenze import (DA_SIGLA, IN_CAMPO, SIGLE, SIGLE_TABELLA, STATI, aggiungi_allenamenti, elimina_allenamento, etichetta_corta, giorno_di,
                      leggi_tabella, mesi_della_stagione, nel_periodo, numero_di, ordina, presenze_gruppo,
                      salva_allenamento, seduta, sposta_allenamento, statistiche, testo_da_file)
from stagioni import gruppi_correnti
from statistiche_pdf import genera_pdf_presenze
from utenti import gruppi_utente

ORDINE_SIGLE = [DA_SIGLA[x] for x in "CAPDZIG"]  # l'ordine delle tabelle del mister
LEGENDA = ("C completo · A assente · P parziale · D differenziato · Z presenza (c'era ma non si è allenato) · "
           "I infortunato · G giustificato")
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
    st.caption(LEGENDA)
    # Un tasto per sigla accanto a ogni ragazzo: niente tabella da scorrere di lato né tastiera sul telefono.
    # Nel modulo i tocchi non ricaricano la pagina: si salva tutto insieme.
    # I ragazzi si dispongono uno accanto all'altro finché c'è spazio (sul telefono uno per riga), in ordine
    # alfabetico per righe: la lista occupa meno spazio in altezza.
    with st.form(f"pres_form_{gruppo}_{chiave}_{n}", border=False):
        segnati = {}
        with st.container(horizontal=True, gap="small", key="pres_griglia"):
            st.html("<style>.st-key-pres_griglia{row-gap:.2rem;column-gap:1.5rem}</style>")
            for r in ragazzi:
                with st.container(width=310):
                    segnati[r["id"]] = st.segmented_control(
                        f"**{nome_completo(r)}**", ORDINE_SIGLE, required=True, format_func=SIGLE.get,
                        default=(gia or {}).get(r["id"], "completo" if not gia else "assente"),
                        key=f"pres_{gruppo}_{chiave}_{n}_{r['id']}")
        salva = st.form_submit_button("💾 Salva modifiche" if gia else "💾 Salva presenze", type="primary",
                                      use_container_width=True)
    stati = list(segnati.values())
    if salva:
        if gia and nuova != chiave:
            sposta_allenamento(stagione, gruppo, chiave, nuova, segnati)
            st.session_state["pres_apri"] = (data_da_iso(giorno_di(nuova)), numero)
        else:
            salva_allenamento(stagione, gruppo, chiave, segnati)
        st.session_state["pres_n"] = n + 1
        in_campo = sum(1 for s in stati if s in IN_CAMPO)
        _messaggio("success", f"Allenamento del {_gg(nuova)} salvato: {in_campo} allenati su {len(stati)} "
                              f"({_riassunto(segnati)}).")
        st.rerun()
    if gia and st.button("🗑️ Togli questo allenamento", use_container_width=True, key="pres_elimina"):
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
    ordine_vista = st.segmented_control("Ordina per", ["🔤 Nome", "🏃 Allenato %"], default="🔤 Nome",
                                        required=True, key="pres_ordina")
    if ordine_vista != "🔤 Nome":
        righe = sorted(righe, key=lambda r: (-r["Allenato %"], r["Ragazzo"]))
    st.html(_tabella_statistiche(righe, sigle))
    st.caption("C completo · A assente · P parziale · D differenziato · Z presenza (c'era ma non si è allenato)"
               + (" · I infortunato · G giustificato" if len(sigle) > 5 else "")
               + ". Sotto ogni numero la percentuale; Allenato % conta C, P e D.")
    with st.expander(f"🔎 Allenamento per allenamento ({len(sedute)})"):
        griglia = pd.DataFrame([{"Ragazzo": nome_di[i], **{etichetta_corta(s): SIGLE.get(allenamenti[s].get(i), "")
                                                            for s in sedute}} for i in ordine])
        st.dataframe(griglia, hide_index=True, use_container_width=True)

    firma = (gruppo, periodo, tuple(sedute), segnati, in_campo)
    if st.button("🖨️ Prepara il PDF come la tabella del mister", key="pres_pdf"):
        tabella = [(nome_di[i], r["Anno"], [SIGLE.get(allenamenti[s].get(i), "") for s in sedute])
                   for i, r in zip(ordine, righe)]
        st.session_state["pres_pdf_pronto"] = (firma, genera_pdf_presenze(
            gruppo, stagione, periodo, tabella, [etichetta_corta(s) for s in sedute], sigle,
            dal=_gg(dal or giorno_di(sedute[0])), al=_gg(al or giorno_di(sedute[-1]))))
    pronto = st.session_state.get("pres_pdf_pronto")
    if pronto and pronto[0] == firma:
        st.download_button("⬇️ Scarica il PDF", pronto[1], mime="application/pdf", key="pres_pdf_scarica",
                           file_name=f"presenze_{gruppo}_{periodo}.pdf".replace(" ", "_").replace("/", "-"))


def _tabella_statistiche(righe, sigle):
    """Tabella HTML a tutta larghezza (niente scorrimento di lato sul telefono, celle non selezionabili)."""
    stile = ("<style>.pres-tab{width:100%;border-collapse:collapse;font-size:0.85rem;table-layout:auto}"
             ".pres-tab th,.pres-tab td{padding:4px 3px;border-bottom:1px solid rgba(128,128,128,.25);"
             "text-align:center;vertical-align:middle}.pres-tab th{font-weight:600;background:rgba(128,128,128,.1)}"
             ".pres-tab td.nome,.pres-tab th.nome{text-align:left;word-break:break-word}"
             ".pres-tab small{display:block;opacity:.6;font-size:0.72rem}"
             ".pres-bar{height:8px;border-radius:4px;background:rgba(128,128,128,.2);margin-top:2px}"
             ".pres-bar div{height:100%;border-radius:4px}</style>")
    testa = "".join(f"<th>{k}</th>" for k in sigle)
    corpo = []
    for r in righe:
        perc = r["Allenato %"]
        colore = "#2F855A" if perc >= 80 else "#D69E2E" if perc >= 60 else "#C53030"
        celle = "".join(f"<td>{r[k]}<small>{r[f'{k}%']}%</small></td>" for k in sigle)
        corpo.append(f"<tr><td class='nome'>{html.escape(r['Ragazzo'])}<small>{html.escape(str(r['Anno'] or ''))}"
                     f"</small></td>{celle}<td><b>{perc}%</b><div class='pres-bar'><div style='width:{perc}%;"
                     f"background:{colore}'></div></div></td></tr>")
    return (f"{stile}<table class='pres-tab'><thead><tr><th class='nome'>Ragazzo</th>{testa}<th>Allenato</th>"
            f"</tr></thead><tbody>{''.join(corpo)}</tbody></table>")


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
    tutti = calciatori(elenco_ragazzi())
    preferiti = {r["id"] for r in ragazzi}
    nomi, anni, sedute, problemi = [], {}, {}, []
    for nome_file, t in tabelle:
        if not t["sedute"]:
            problemi.append(f"{nome_file}: non trovo la riga con le date (es. 01-set).")
            continue
        if t["stagione"] != stagione:
            problemi.append(f"{nome_file}: è della stagione {t['stagione']}, non della {stagione}.")
            continue
        problemi += [f"{nome_file}: {p}" for p in t["problemi"]]
        for nome, anno, stati in t["righe"]:  # l'anno della tabella non conta: spesso è sbagliato
            if nome not in nomi:
                nomi.append(nome)
            anni[nome] = anni.get(nome) or anno
            for chiave, stato in zip(t["sedute"], stati):
                sedute.setdefault(chiave, {})[nome] = stato
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
    # per nome soltanto; l'anno serve solo a scegliere tra due omonimi
    proposti = {k: trova_per_nome(k, "", tutti, preferiti) or trova_per_nome(k, anni[k], tutti, preferiti)
                for k in nomi}
    tabella = pd.DataFrame([{"Nella tabella": n_, "In anagrafica": etichette[r["id"]] if r else NUOVO}
                            for n_, r in proposti.items()])
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
                abbinati[k] = nuova_da_nome(k, anni[k], stagione, gruppo)
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
