"""📊 Statistiche → 📅 Risultati e 🔍 Avversari: tutte le giornate del girone (risultati e calendario) e i numeri
di ogni squadra, letti in automatico dalla pagina della LND dalla GitHub Action "Classifiche"."""
import pandas as pd
import streamlit as st

import girone
import loghi
from classifica import classifiche, nostra_riga
from scelta_squadra import scegli
from stagioni import gruppi_correnti

FORMA = {"V": "🟢", "N": "🟡", "P": "🔴"}


def _data(iso):
    return f"{iso[8:10]}/{iso[5:7]}" if iso and len(iso) >= 10 else ""


def _risultato(p):
    return f"{p['gol_casa']} - {p['gol_ospite']}" if p.get("gol_casa") is not None else "–"


def _nostra(squadre, nome_societa):
    pos = nostra_riga([{"pos": i, "squadra": s} for i, s in enumerate(squadre)], nome_societa)
    return squadre[pos] if pos is not None else None


def _scegli_gruppo(chiave):
    """(stagione, gruppo, dati del girone) oppure None, con il messaggio se non ci sono ancora dati."""
    stagione, gruppi = gruppi_correnti()
    nomi = [g["gruppo"] for g in gruppi]
    if not nomi:
        st.info("Prima crea le squadre in ⚙️ Opzioni → 🏆 Campionati.")
        return None
    gruppo = scegli(f"👥 Squadra ({stagione})", nomi, chiave) if len(nomi) > 1 else nomi[0]
    dati = girone.tutti().get(gruppo) or {}
    if dati.get("stagione") != stagione or not dati.get("giornate"):
        st.info(f"Ancora nessuna giornata per {gruppo}. Arrivano da sole, mattina e sera, quando in ⚙️ Opzioni → 🌐 Dati LND "
                "è salvato il link della LND (gare.lnd.it).")
        return None
    giorno, _, ora = dati.get("aggiornato", "").partition(" ")
    st.caption(f"Aggiornati il {giorno[8:10]}/{giorno[5:7]} alle {ora} · dati LND · fa fede il Comunicato Ufficiale.")
    return stagione, gruppo, dati


def _evidenzia(df, colonne, nome):
    return df.style.apply(lambda riga: ["font-weight:700;background-color:rgba(30,90,200,.12)"
                                        if nome and nome in [riga[c] for c in colonne] else "" for _ in riga], axis=1)


def _tabella_partite(partite, nostra, con_giornata=False):
    stemmi = loghi.tutti()
    con_stemmi = any(loghi.di(p[lato], stemmi) for _, p in partite for lato in ("casa", "ospite"))
    righe = [{**({"Giornata": girone.etichetta(k)} if con_giornata else {}), "Data": _data(p.get("data")),
              "Ora": p.get("ora", ""), **({"S1": loghi.di(p["casa"], stemmi) or None} if con_stemmi else {}),
              "Casa": p["casa"], "Risultato": _risultato(p),
              **({"S2": loghi.di(p["ospite"], stemmi) or None} if con_stemmi else {}),
              "Ospite": p["ospite"], "Campo": p.get("campo", "")} for k, p in partite]
    df = pd.DataFrame(righe)
    st.dataframe(_evidenzia(df, ["Casa", "Ospite"], nostra), hide_index=True, width="stretch",
                 column_config={"S1": st.column_config.ImageColumn("", width="small"),
                                "S2": st.column_config.ImageColumn("", width="small")})


def _giornata_attuale(giornate):
    """L'ultima giornata con almeno un risultato (o la prima, se non ne ha nessuna)."""
    giocate = [k for k in sorted(giornate) if any(p.get("gol_casa") is not None for p in giornate[k])]
    return giocate[-1] if giocate else sorted(giornate)[0]


def render_risultati(nome_societa=""):
    scelta = _scegli_gruppo("gi_gruppo_risultati")
    if not scelta:
        return
    _, gruppo, dati = scelta
    giornate = dati["giornate"]
    nostra = _nostra(girone.squadre_del_girone(giornate), nome_societa)
    solo_nostre = st.toggle("Solo le nostre partite", key="gi_solo_nostre", disabled=not nostra)
    if solo_nostre and nostra:
        _tabella_partite(girone.partite_di(giornate, nostra), nostra, con_giornata=True)
        return
    chiavi = sorted(giornate)
    chiave = f"gi_giornata_{gruppo}"
    if st.session_state.get(chiave) not in chiavi:
        st.session_state[chiave] = _giornata_attuale(giornate)
    k = st.selectbox("Giornata", chiavi, format_func=girone.etichetta, key=chiave)
    _tabella_partite([(k, p) for p in giornate[k]], nostra)


def _riassunto(conto):
    return f"{conto['v']}V {conto['n']}N {conto['p']}P · gol {conto['gf']}-{conto['gs']} · {conto['pt']} pt"


def _tutte(giornate, squadre, nostra):
    righe = []
    for s in squadre:
        sc = girone.scheda_squadra(giornate, s)
        t = sc["totale"]
        righe.append({"Squadra": s, "G": t["g"], "Pt": t["pt"], "GF": t["gf"], "GS": t["gs"],
                      "Pt casa": sc["casa"]["pt"], "Pt fuori": sc["fuori"]["pt"],
                      "Ultime": "".join(FORMA[e] for e in sc["forma"])})
    df = pd.DataFrame(righe).sort_values(["Pt", "GF"], ascending=False)
    st.dataframe(_evidenzia(df, ["Squadra"], nostra), hide_index=True, width="stretch")
    st.caption("Calcolata dai risultati letti: può differire dalla classifica ufficiale (penalizzazioni, "
               "partite a tavolino o non ancora lette).")


def render_avversari(nome_societa=""):
    scelta = _scegli_gruppo("gi_gruppo_avversari")
    if not scelta:
        return
    _, gruppo, dati = scelta
    giornate = dati["giornate"]
    squadre = girone.squadre_del_girone(giornate)
    nostra = _nostra(squadre, nome_societa)
    avversari = [s for s in squadre if s != nostra]
    prossima = girone.scheda_squadra(giornate, nostra)["prossima"] if nostra else None
    if prossima:
        k, p = prossima
        st.markdown(f"**Prossima partita** · {girone.etichetta(k)} · {_data(p.get('data'))} {p.get('ora', '')}: "
                    f"{p['casa']} – {p['ospite']}")
    if st.session_state.get(f"gi_squadra_{gruppo}") not in squadre and prossima:
        rivale = prossima[1]["ospite"] if prossima[1]["casa"] == nostra else prossima[1]["casa"]
        if rivale in avversari:
            st.session_state[f"gi_squadra_{gruppo}"] = rivale
    squadra = st.selectbox("🔍 Squadra da guardare", avversari + ([nostra] if nostra else []),
                           key=f"gi_squadra_{gruppo}")
    sc = girone.scheda_squadra(giornate, squadra)
    if loghi.di(squadra):
        st.image(loghi.di(squadra), width=64)
    riga = next((r for r in (classifiche().get(gruppo) or {}).get("righe", [])
                 if r["squadra"].lower() == squadra.lower()), None)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Posizione", f"{riga['pos']}ª" if riga else "–", f"{riga['pt']} pt" if riga else None,
              delta_color="off")
    c2.metric("Gol fatti a partita", sc["media_fatti"])
    c3.metric("Gol subiti a partita", sc["media_subiti"])
    c4.metric("Senza subire gol", sc["senza_subire"])
    st.markdown(f"**Ultime partite:** {' '.join(FORMA[e] for e in sc['forma']) or '–'}  \n"
                f"**In casa:** {_riassunto(sc['casa'])}  \n**Fuori casa:** {_riassunto(sc['fuori'])}")
    if nostra and squadra != nostra:
        contro = [(k, p) for k, p in girone.partite_di(giornate, squadra) if nostra in (p["casa"], p["ospite"])]
        if contro:
            st.markdown("**Contro di noi**")
            _tabella_partite(contro, nostra, con_giornata=True)
    with st.expander(f"📅 Tutte le partite di {squadra}"):
        _tabella_partite(girone.partite_di(giornate, squadra), nostra, con_giornata=True)
    with st.expander("📊 Tutte le squadre: casa, fuori, gol e ultime partite"):
        _tutte(giornate, squadre, nostra)
