import hashlib
import io
import json
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import qrcode
import streamlit as st

import archivio_cloud
from ui_archivio import render_archivio
from utenti import (
    RUOLI,
    UtentiErrore,
    accedi,
    aggiungi_utente,
    cambia_password,
    cambia_ruolo,
    elenco_utenti,
    elimina_utente,
)
from cronaca_manager import (
    impostazioni_lettura,
    leggi_distinta_caricata,
    leggi_liste_in_lavorazione,
    registra_costo_lettura,
    salva_distinta_caricata,
    salva_foto_distinte_pubblicate,
    salva_impostazioni_lettura,
    salva_liste_in_lavorazione,
    storico_costi,
    togli_distinte_caricate,
    togli_liste_in_lavorazione,
)
from controlli import controlla_lista
from estrattore import MODELLI_LETTURA, analizza_distinta, unisci_scansioni
from github_publisher import PubblicazioneErrore, leggi_file, pubblica_su_github, url_pagina_da_repo
from pdf_manager import genera_pdf, loghi_da_cartella_locale, numero_sponsor
from squadra_manager import (
    giocatori_da_griglia,
    griglia_vuota,
    pulisci_widget_squadra,
    render_colonna_squadra,
    reset_stato_squadra,
)
from ui_components import render_download_buttons, render_info_match
from ui_cronaca import render_cronaca
from ui_sponsor import loghi_per_pdf, render_gestione_sponsor
from ui_statistiche import render_statistiche

# Deve essere il PRIMO comando Streamlit
st.set_page_config(page_title="Segreteria - Distinta Digitale Azzurra", page_icon="⚽", layout="wide")

# Menu, Deploy e barra superiore si nascondono da .streamlit/config.toml
st.markdown("<style>.block-container { padding-top: 1rem !important; }</style>", unsafe_allow_html=True)


def leggi_secret(nome, default=None):
    """Legge un secret senza esplodere se secrets.toml non esiste."""
    try:
        return st.secrets.get(nome, default)
    except Exception:
        return default


archivio_cloud.configura(leggi_secret("SUPABASE_URL"), leggi_secret("SUPABASE_KEY"))


def link_pagina_spettatori():
    """Indirizzo della pagina pubblica (quello del QR code)."""
    esplicito = leggi_secret("LINK_PUBBLICO")
    if esplicito:
        return str(esplicito)
    return url_pagina_da_repo(str(leggi_secret("GITHUB_REPO", "")))


def genera_qr_png(link):
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(link)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


def firma_file(f):
    """Identifica il file per contenuto/id, non solo per nome (IMG_0001.jpg si ripete)."""
    if f is None:
        return ""
    return getattr(f, "file_id", None) or f"{f.name}-{f.size}"


class FileCaricato(io.BytesIO):
    """Foto di una distinta tenuta in memoria: si comporta come il file appena caricato."""

    def __init__(self, salvato):
        super().__init__(salvato["dati"])
        self.name, self.size, self.file_id = salvato["nome"], len(salvato["dati"]), salvato["id"]


def carica_distinta(colonna, etichetta, lato):
    """Uploader che ricorda la foto fino alla prossima partita: resta salvata (disco e Supabase) anche
    cambiando sezione, dopo un riavvio o da un altro dispositivo, finché non si preme "Cambia" o si
    archivia/cancella la partita."""
    chiave = f"distinta_caricata_{lato}"
    if chiave not in st.session_state:  # prima volta in questa sessione: quella salvata (anche da un altro dispositivo)
        st.session_state[chiave] = leggi_distinta_caricata(lato)
        if st.session_state[chiave]:
            st.session_state[chiave]["id"] = hashlib.md5(st.session_state[chiave]["dati"]).hexdigest()
    salvato = st.session_state.get(chiave)
    if salvato:
        colonna.markdown(f"**{etichetta}**")
        c_nome, c_cambia = colonna.columns([3, 1])
        c_nome.success(f"📎 {salvato['nome']}")
        if c_cambia.button("Cambia", key=f"cambia_{lato}", use_container_width=True):
            st.session_state[chiave] = None
            st.session_state.pop(f"uploader_file_{lato}", None)
            togli_distinte_caricate([lato])
            st.rerun()
        return FileCaricato(salvato)
    f = colonna.file_uploader(etichetta, type=["png", "jpg", "jpeg", "pdf"], key=f"uploader_file_{lato}")
    if f is not None:
        st.session_state[chiave] = {"nome": f.name, "dati": f.getvalue(), "id": hashlib.md5(f.getvalue()).hexdigest()}
        salva_distinta_caricata(lato, f.name, f.getvalue())
    return f


def render_opzioni_lettura():
    """Modello e lettura ingrandita usati dalla scansione, per tutti i dispositivi."""
    st.subheader("🤖 Lettura AI delle distinte")
    attuali = impostazioni_lettura()
    modelli = list(MODELLI_LETTURA)
    modello = st.selectbox("Modello", modelli, format_func=MODELLI_LETTURA.get, key="opzioni_modello",
                           index=modelli.index(attuali["modello"]) if attuali["modello"] in modelli else 0)
    ingrandita = st.checkbox("Lettura ingrandita: manda la foto anche in strisce, per le scritte piccole",
                             value=attuali["ingrandita"], key="opzioni_ingrandita")
    if (modello, ingrandita) != (attuali["modello"], attuali["ingrandita"]):
        salva_impostazioni_lettura(modello, ingrandita)
        st.success("Impostazione salvata: vale dalla prossima scansione, anche dagli altri dispositivi.")
    st.caption("Per confrontare: fai la scansione, poi «🗑️ Svuota Liste e Ripristina Scansione», cambia qui "
               "l'impostazione e rifai la scansione con le stesse foto. La lettura ingrandita e i modelli più "
               "nuovi costano un po' di più; GPT-5 impiega molto più tempo.")
    render_costi_letture(dettaglio=True)


def render_controllo_liste(dati_c, dati_o):
    """Quello che conviene ricontrollare sul foglio, aggiornato a ogni correzione."""
    avvisi = (controlla_lista(dati_c["squadra"] or "Casa", giocatori_da_griglia("griglia_casa"), dati_c["allenatore"])
              + controlla_lista(dati_o["squadra"] or "Ospite", giocatori_da_griglia("griglia_ospite"),
                                dati_o["allenatore"]))
    with st.container(border=True):
        if not avvisi:
            st.markdown("🔎 **Controllo liste:** ✅ nessun problema trovato.")
            return
        st.markdown(f"🔎 **Controllo liste:** {len(avvisi)} cose da ricontrollare sul foglio prima di pubblicare")
        st.markdown("\n".join(f"- {a}" for a in avvisi))


def descrizione_lettura(modello, ingrandita):
    return MODELLI_LETTURA.get(modello, modello).split(" (")[0] + (", lettura ingrandita" if ingrandita else "")


def formatta_dollari(valore):
    return f"{valore:.3f} $".replace(".", ",")


def render_costi_letture(dettaglio=False):
    """Quanto sono costate le scansioni fatte finora (stima dai token dichiarati da OpenAI);
    con dettaglio anche le ultime 10 scansioni."""
    storico = storico_costi()
    if not storico:
        if dettaglio:
            st.caption("💵 Il costo di ogni scansione comparirà qui dopo la prima lettura.")
        return
    mese = datetime.now(ZoneInfo("Europe/Rome")).strftime("/%m/%Y")
    del_mese = [v for v in storico if v.get("quando", "")[2:10] == mese]
    def quante(n):
        return f"{n} scansion{'e' if n == 1 else 'i'}"
    st.markdown(f"**💵 Costo delle scansioni** (stima): questo mese {formatta_dollari(sum(v['costo'] for v in del_mese))} "
                f"({quante(len(del_mese))}), in totale {formatta_dollari(sum(v['costo'] for v in storico))} "
                f"({quante(len(storico))}).")
    if not dettaglio:
        return
    ultime = [{"Quando": v["quando"], "Gara": v.get("gara", ""),
               "Lettura": MODELLI_LETTURA.get(v["modello"], v["modello"]).split(" (")[0]
                          + (" ingrandita" if v.get("ingrandita") else ""),
               "Costo": formatta_dollari(v["costo"])} for v in reversed(storico[-10:])]
    st.dataframe(pd.DataFrame(ultime), hide_index=True, use_container_width=True)
    st.caption("Calcolato sui prezzi di listino OpenAI; il credito residuo si vede solo su platform.openai.com.")


def ripristina_liste_salvate():
    """Prima volta in questa sessione: le liste in lavorazione salvate (dopo un riavvio, da un altro
    dispositivo o riaprendo la pagina) tornano nella sezione Distinta come erano state lasciate."""
    if st.session_state.get("liste_controllate"):
        return
    st.session_state["liste_controllate"] = True
    salvate = leggi_liste_in_lavorazione()
    if not salvate or "dati_mappati" in st.session_state:
        return
    info, casa, ospite = salvate.get("info_gara") or {}, salvate.get("casa") or {}, salvate.get("ospite") or {}
    st.session_state["macro_info"] = {
        **unisci_scansioni({}, {}), **(salvate.get("macro_info") or {}),
        "campionato": info.get("campionato", ""), "giornata": info.get("giornata", ""),
        "data": info.get("data", ""), "arbitro": info.get("arbitro", ""),
        "ass_casa": info.get("assistente1", ""), "ass_ospite": info.get("assistente2", ""),
        "nome_casa": casa.get("squadra", ""), "all_casa": casa.get("allenatore", ""),
        "nome_ospite": ospite.get("squadra", ""), "all_ospite": ospite.get("allenatore", ""),
    }
    for chiave, squadra in (("griglia_casa", casa), ("griglia_ospite", ospite)):
        if squadra.get("giocatori"):
            st.session_state[chiave] = pd.DataFrame(squadra["giocatori"]).set_index("N°")
        pulisci_widget_squadra(chiave)
    st.session_state["firma_scansione_attiva"] = salvate.get("firma", "")
    st.session_state["liste_salvate"] = salvate
    st.session_state["dati_mappati"] = True


def salva_liste_se_cambiate(info_gara, dati_c, dati_o):
    """Salva (disco e Supabase) le liste ogni volta che cambiano: scansione, CSV o correzioni a mano."""
    attuali = {
        "info_gara": info_gara,
        "casa": {**dati_c, "giocatori": giocatori_da_griglia("griglia_casa")},
        "ospite": {**dati_o, "giocatori": giocatori_da_griglia("griglia_ospite")},
        "macro_info": {k: v for k, v in st.session_state["macro_info"].items() if k == "avvisi"},
        "firma": st.session_state.get("firma_scansione_attiva", ""),
    }
    if attuali != st.session_state.get("liste_salvate"):
        salva_liste_in_lavorazione(attuali)
        st.session_state["liste_salvate"] = attuali


def reset_solo_dati_ai():
    togli_liste_in_lavorazione()
    st.session_state.pop("liste_salvate", None)
    for chiave in ["dati_mappati", "macro_info", "firma_scansione_attiva", "pdf_interattivo_pronto"]:
        st.session_state.pop(chiave, None)
    reset_stato_squadra("griglia_casa")
    reset_stato_squadra("griglia_ospite")
    st.rerun()


def pubblica_distinta(info_gara, dati_c, dati_o):
    """Genera il PDF e lo pubblica insieme ai dati sul repository della pagina."""
    link = link_pagina_spettatori()
    qr_bytes = genera_qr_png(link) if link else None

    loghi, avviso_sponsor = loghi_per_pdf(
        leggi_secret("GITHUB_TOKEN"), leggi_secret("GITHUB_REPO"), leggi_secret("GITHUB_BRANCH")
    )
    if avviso_sponsor:
        st.warning(avviso_sponsor)
    n_sponsor = len(loghi) if loghi is not None else numero_sponsor()
    if n_sponsor == 0:
        st.info("Il PDF è senza sponsor: caricali dalla sezione ⚙️ Opzioni in alto.")

    pdf_bytes = genera_pdf(dati_c, dati_o, info_gara, qr_bytes, sponsor_loghi=loghi)
    st.session_state["pdf_interattivo_pronto"] = pdf_bytes  # il PDF resta scaricabile anche se GitHub non risponde

    if not link:
        st.warning("Link della pagina spettatori non configurato: il PDF è stato creato senza QR code.")

    pacchetto = {
        "info_gara": info_gara,
        "casa": dati_c,
        "ospite": dati_o,
        "aggiornato": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    st.session_state["ultima_distinta"] = pacchetto  # la usa anche la cronaca della partita
    file_da_pubblicare = {
        "distinta.json": json.dumps(pacchetto, ensure_ascii=False, indent=2).encode("utf-8"),
        "distinta.pdf": pdf_bytes,
    }

    try:
        pubblica_su_github(
            token=leggi_secret("GITHUB_TOKEN"),
            repo=leggi_secret("GITHUB_REPO"),
            file_da_pubblicare=file_da_pubblicare,
            messaggio=f"Distinta {dati_c.get('squadra') or 'casa'} - {dati_o.get('squadra') or 'ospite'}",
            branch=leggi_secret("GITHUB_BRANCH"),  # se assente: ramo principale del repository
        )
    except PubblicazioneErrore as e:
        st.error(f"❌ Pubblicazione online non riuscita: {e}")
        st.info("Il PDF è comunque pronto qui sotto. Puoi riprovare a pubblicare.")
        return

    st.success(
        "🎉 Distinta inviata a GitHub. La pagina spettatori si aggiorna entro circa 1-2 minuti"
        + (f": {link}" if link else ".")
    )


def pubblica_attesa():
    """Partita archiviata o cancellata: la pagina spettatori mostra l'attesa della prossima partita
    (senza più liste dei giocatori né PDF della partita chiusa)."""
    token, repo, branch = leggi_secret("GITHUB_TOKEN"), leggi_secret("GITHUB_REPO"), leggi_secret("GITHUB_BRANCH")
    if not (token and repo):
        return False
    attesa = json.dumps({"stato": "in_attesa", "aggiornato": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                        ensure_ascii=False, indent=2).encode("utf-8")
    for file in ({"distinta.json": attesa, "distinta.pdf": None}, {"distinta.json": attesa}):
        try:  # il PDF potrebbe non esserci già più: allora si aggiorna solo distinta.json
            pubblica_su_github(token=token, repo=repo, file_da_pubblicare=file,
                               messaggio="In attesa della prossima partita", branch=branch)
            return True
        except PubblicazioneErrore as e:
            errore = e
    st.warning(f"Pagina spettatori non aggiornata con l'attesa della prossima partita: {errore}")
    return False


def render_forza_attesa():
    """Mette subito la pagina spettatori in attesa della prossima partita, senza toccare liste e cronaca."""
    if st.button("⏳ Metti la pagina live in attesa della prossima partita", use_container_width=True):
        st.session_state["conferma_attesa"] = True
        st.rerun()
    if st.session_state.get("conferma_attesa"):
        st.warning("La pagina degli spettatori toglie liste e PDF e mostra «In attesa della prossima partita». "
                   "Qui nell'app non cambia nulla: per rimettere la distinta basta pubblicarla di nuovo. Continuare?")
        c1, c2 = st.columns(2)
        if c1.button("✅ Sì, metti in attesa", type="primary", use_container_width=True):
            st.session_state.pop("conferma_attesa", None)
            with st.spinner("Aggiorno la pagina spettatori..."):
                if pubblica_attesa():
                    st.session_state["messaggio_attesa"] = ("⏳ Pagina spettatori in attesa della prossima partita "
                                                            "(si aggiorna entro 1-2 minuti).")
                    st.rerun()
        if c2.button("Annulla", key="annulla_attesa", use_container_width=True):
            st.session_state.pop("conferma_attesa", None)
            st.rerun()
    messaggio = st.session_state.pop("messaggio_attesa", None)
    if messaggio:
        st.success(messaggio)


def loghi_sponsor_pdf():
    """Loghi sponsor per i PDF: quelli pubblicati, o la cartella locale di riserva."""
    loghi, _ = loghi_per_pdf(leggi_secret("GITHUB_TOKEN"), leggi_secret("GITHUB_REPO"), leggi_secret("GITHUB_BRANCH"))
    return loghi if loghi is not None else loghi_da_cartella_locale()


def distinta_pubblicata():
    """Ultima distinta pubblicata: quella di questa sessione, altrimenti distinta.json dal repository della pagina."""
    if st.session_state.get("ultima_distinta"):
        return st.session_state["ultima_distinta"]
    if not (leggi_secret("GITHUB_TOKEN") and leggi_secret("GITHUB_REPO")):
        return None
    dati = leggi_file(leggi_secret("GITHUB_TOKEN"), leggi_secret("GITHUB_REPO"), "distinta.json", leggi_secret("GITHUB_BRANCH"))
    distinta = json.loads(dati) if dati else None
    return distinta if distinta and distinta.get("casa") else None  # "in attesa": nessuna distinta


def render_login():
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.title("⚽ Segreteria - Distinta Digitale")
        st.caption("A.S.D. Azzurra Due Carrare")
        password_emergenza = leggi_secret("SEGRETERIA_PASSWORD")
        nome = st.text_input("Utente", key="utente_segreteria",
                             help="Lascia vuoto per entrare con la password della segreteria.")
        password_inserita = st.text_input("Password", type="password", key="pwd_segreteria")
        if st.button("Accedi", type="primary", use_container_width=True):
            accesso = accedi(nome, password_inserita, password_emergenza)
            if accesso:
                st.session_state["autenticato"] = True
                st.session_state["utente"], st.session_state["ruolo"] = accesso
                st.rerun()
            else:
                time.sleep(1)  # rallenta chi prova password a raffica
                st.error("❌ Utente o password errati. Accesso negato.")


def azzera_sezione_distinta():
    """Dopo l'archiviazione di una partita: via foto caricate, dati letti, PDF e ultima distinta."""
    for chiave in ["dati_mappati", "macro_info", "firma_scansione_attiva", "pdf_interattivo_pronto",
                   "ultima_distinta", "uploader_file_casa", "uploader_file_ospite",
                   "distinta_caricata_casa", "distinta_caricata_ospite", "liste_salvate"]:
        st.session_state.pop(chiave, None)
    reset_stato_squadra("griglia_casa")
    reset_stato_squadra("griglia_ospite")


SEZIONI = ["📋 Distinta", "🎙️ Cronaca partita", "📚 Archivio", "📊 Statistiche", "⚙️ Opzioni"]
SOTTOSEZIONI_OPZIONI = ["🤖 Lettura AI", "🏷️ Sponsor", "👥 Utenti"]  # per una nuova impostazione basta aggiungerla qui
SEZIONI_PER_RUOLO = {"admin": SEZIONI, "user": SEZIONI[:2]}


def render_gestione_utenti():
    st.subheader("👥 Utenti")
    st.caption("Gli amministratori vedono tutte le sezioni; gli utenti solo Distinta e Cronaca partita. "
               "Le password sono salvate cifrate. Con utente vuoto e la password della segreteria "
               "(nei secrets) si entra sempre come amministratore.")
    for tipo, testo in st.session_state.pop("utenti_messaggi", []):
        getattr(st, tipo)(testo)
    utenti = elenco_utenti()
    if not utenti:
        st.info("Nessun utente creato: per ora si entra solo con la password della segreteria.")
    for nome, dati in sorted(utenti.items()):
        with st.expander(f"{'🛡️' if dati.get('ruolo') == 'admin' else '👤'} {nome} · {RUOLI.get(dati.get('ruolo'), '')}"):
            ruolo = st.selectbox("Ruolo", list(RUOLI), format_func=RUOLI.get, key=f"ruolo_{nome}",
                                 index=list(RUOLI).index(dati.get("ruolo", "user")))
            if ruolo != dati.get("ruolo"):
                cambia_ruolo(nome, ruolo)
                st.success("Ruolo aggiornato.")
            nuova = st.text_input("Nuova password", type="password", key=f"nuova_pwd_{nome}")
            c1, c2 = st.columns(2)
            if c1.button("🔑 Cambia password", key=f"cambia_pwd_{nome}", use_container_width=True):
                try:
                    cambia_password(nome, nuova)
                    st.session_state["utenti_messaggi"] = [("success", f"Password di {nome} cambiata.")]
                    st.session_state.pop(f"nuova_pwd_{nome}", None)
                    st.rerun()
                except UtentiErrore as e:
                    st.error(str(e))
            if c2.button("🗑️ Elimina utente", key=f"elimina_{nome}", use_container_width=True,
                         disabled=nome == st.session_state.get("utente")):
                elimina_utente(nome)
                st.session_state["utenti_messaggi"] = [("success", f"Utente {nome} eliminato.")]
                st.rerun()

    with st.form("nuovo_utente", clear_on_submit=True):
        st.markdown("**➕ Nuovo utente**")
        c1, c2, c3 = st.columns(3)
        nome = c1.text_input("Nome utente")
        password = c2.text_input("Password", type="password")
        ruolo = c3.selectbox("Ruolo", list(RUOLI), format_func=RUOLI.get, index=1)
        if st.form_submit_button("Crea utente", type="primary"):
            try:
                creato = aggiungi_utente(nome, password, ruolo)
                st.session_state["utenti_messaggi"] = [("success", f"Utente {creato} creato.")]
                st.rerun()
            except UtentiErrore as e:
                st.error(str(e))


def render_segreteria():
    if st.session_state.pop("azzera_distinta", False):
        azzera_sezione_distinta()
        with st.spinner("Aggiorno la pagina spettatori: in attesa della prossima partita..."):
            pubblica_attesa()
    if "vai_a_sezione" in st.session_state:  # es. "Riapri" dall'archivio porta alla Cronaca
        st.session_state["sezione_segreteria"] = st.session_state.pop("vai_a_sezione")
    sezioni = SEZIONI_PER_RUOLO.get(st.session_state.get("ruolo"), SEZIONI_PER_RUOLO["user"])
    if st.session_state.get("sezione_segreteria") not in sezioni:
        st.session_state["sezione_segreteria"] = sezioni[0]
    sezione_attuale = st.session_state["sezione_segreteria"]
    col_titolo, col_esci = st.columns([5, 1])
    with col_titolo:
        st.title(f"⚽ Centro Gestione Gara - {sezione_attuale.split(' ', 1)[1]}")
    with col_esci:
        st.write("")
        if st.button("Esci", type="secondary", use_container_width=True):
            for chiave in ("autenticato", "utente", "ruolo", "sezione_segreteria"):
                st.session_state.pop(chiave, None)
            st.rerun()

    sezione = st.radio("Sezione", sezioni, horizontal=True, label_visibility="collapsed", key="sezione_segreteria")
    st.caption(f"👤 {st.session_state.get('utente', '')}")
    if sezione == "⚙️ Opzioni":
        sotto = st.segmented_control("Opzioni", SOTTOSEZIONI_OPZIONI, key="sottosezione_opzioni",
                                     default=SOTTOSEZIONI_OPZIONI[0], label_visibility="collapsed")
        sotto = sotto or SOTTOSEZIONI_OPZIONI[0]  # un secondo clic sul pulsante scelto lo deseleziona
        if sotto == "🤖 Lettura AI":
            render_opzioni_lettura()
            return
        if sotto == "👥 Utenti":
            render_gestione_utenti()
            return
        st.subheader("🏷️ Sponsor")
        render_gestione_sponsor(leggi_secret("GITHUB_TOKEN"), leggi_secret("GITHUB_REPO"), leggi_secret("GITHUB_BRANCH"))
        return
    if sezione == "📊 Statistiche":
        render_statistiche(leggi_secret("NOME_SOCIETA") or "Azzurra Duecarrare")
        return
    if sezione == "📚 Archivio":
        render_archivio(loghi_sponsor_pdf)
        return
    if sezione == "🎙️ Cronaca partita":
        render_cronaca(leggi_secret("OPENAI_API_KEY"), st.session_state.get("macro_info"), loghi_sponsor_pdf,
                       distinta_pubblicata)
        return

    link = link_pagina_spettatori()
    st.write(
        "La pubblicazione genera il PDF A4 e aggiorna la pagina web degli spettatori"
        + (f" ({link})." if link else ".")
    )
    if not (leggi_secret("GITHUB_TOKEN") and leggi_secret("GITHUB_REPO")):
        st.warning("GITHUB_TOKEN / GITHUB_REPO non configurati nei secrets: la pubblicazione online non è disponibile.")

    api_key_openai = leggi_secret("OPENAI_API_KEY")
    if not api_key_openai:
        st.warning("OPENAI_API_KEY non configurata nei secrets: la scansione AI non è disponibile.")

    ripristina_liste_salvate()
    if "griglia_casa" not in st.session_state:
        st.session_state["griglia_casa"] = griglia_vuota()
    if "griglia_ospite" not in st.session_state:
        st.session_state["griglia_ospite"] = griglia_vuota()

    col_f1, col_f2 = st.columns(2)
    file_casa = carica_distinta(col_f1, "Carica distinta LOCALE (foto o PDF)", "casa")
    file_ospite = carica_distinta(col_f2, "Carica distinta OSPITE (foto o PDF)", "ospite")

    c_scan, c_reset = st.columns(2)
    with c_reset:
        if st.button("🗑️ Svuota Liste e Ripristina Scansione", type="secondary", use_container_width=True):
            reset_solo_dati_ai()

    firma_correnti = f"{firma_file(file_casa)}__{firma_file(file_ospite)}"

    if file_casa and file_ospite:
        # File cambiati: la scansione precedente (e il PDF) non sono più validi
        if st.session_state.get("firma_scansione_attiva") != firma_correnti:
            st.session_state.pop("dati_mappati", None)
            st.session_state.pop("pdf_interattivo_pronto", None)

        if "dati_mappati" not in st.session_state:
            lettura = impostazioni_lettura()
            modello, ingrandita = lettura["modello"], lettura["ingrandita"]
            st.caption(f"🤖 Lettura con {descrizione_lettura(modello, ingrandita)} (si cambia in ⚙️ Opzioni).")
            render_costi_letture()
            with c_scan:
                if st.button("🔍 Fase 1: Esegui Scansione AI delle Liste", type="primary", use_container_width=True):
                    with st.spinner(f"Estrazione giocatori e date in corso con {MODELLI_LETTURA[modello].split(' (')[0]}"
                                    + (" (lettura ingrandita)" if ingrandita else "") + "..."):
                        try:
                            casa_raw = analizza_distinta(file_casa, "CASA", api_key_openai, modello, ingrandita)
                            ospite_raw = analizza_distinta(file_ospite, "OSPITE", api_key_openai, modello, ingrandita)
                        except Exception as e:
                            st.error(f"Errore nell'estrazione: {e}")
                        else:
                            st.session_state["griglia_casa"] = pd.DataFrame(casa_raw["giocatori"]).set_index("N°")
                            st.session_state["griglia_ospite"] = pd.DataFrame(ospite_raw["giocatori"]).set_index("N°")
                            pulisci_widget_squadra("griglia_casa")
                            pulisci_widget_squadra("griglia_ospite")
                            st.session_state["macro_info"] = unisci_scansioni(casa_raw, ospite_raw)
                            st.session_state["macro_info"]["lettura"] = descrizione_lettura(modello, ingrandita)
                            costo = sum(r.get("consumo", {}).get("costo", 0) for r in (casa_raw, ospite_raw))
                            st.session_state["macro_info"]["costo_lettura"] = costo
                            info = st.session_state["macro_info"]
                            try:
                                registra_costo_lettura(f"{info.get('nome_casa', '')} - {info.get('nome_ospite', '')}",
                                                       modello, ingrandita, costo)
                            except OSError:
                                pass  # il costo è solo informativo: non deve bloccare la scansione
                            st.session_state["firma_scansione_attiva"] = firma_correnti
                            st.session_state["dati_mappati"] = True
                            st.rerun()

    if "dati_mappati" not in st.session_state:
        if st.button("✍️ Compila le liste a mano o da CSV (senza scansione)", use_container_width=True):
            st.session_state["macro_info"] = unisci_scansioni({}, {})
            st.session_state["dati_mappati"] = True
            st.session_state["firma_scansione_attiva"] = firma_correnti
            st.rerun()

    if "dati_mappati" in st.session_state:
        st.markdown("---")
        if st.session_state["macro_info"].get("lettura"):
            costo = st.session_state["macro_info"].get("costo_lettura")
            st.caption(f"🤖 Liste lette con {st.session_state['macro_info']['lettura']}."
                       + (f" 💵 Costo della scansione: circa {formatta_dollari(costo)}." if costo else ""))
        info_gara = render_info_match(st.session_state["macro_info"])

        st.markdown("---")
        c_sq1, c_sq2 = st.columns(2)
        inf = st.session_state["macro_info"]

        with c_sq1:
            dati_c = render_colonna_squadra("🏠 SQUADRA CASA", "griglia_casa", inf["all_casa"], inf.get("nome_casa", ""))
        with c_sq2:
            dati_o = render_colonna_squadra("🚀 SQUADRA OSPITE", "griglia_ospite", inf["all_ospite"], inf.get("nome_ospite", ""))

        salva_liste_se_cambiate(info_gara, dati_c, dati_o)

        mancanti = [n for n, v in (("data", inf.get("data")), ("nome squadra casa", inf.get("nome_casa")),
                                   ("nome squadra ospite", inf.get("nome_ospite"))) if not v]
        if mancanti:
            st.info("Non sono riuscito a leggere dalle distinte: " + ", ".join(mancanti) + ". Compilali a mano prima di pubblicare.")
        for avviso in inf.get("avvisi", []):
            st.warning(avviso)
        render_controllo_liste(dati_c, dati_o)

        st.markdown("---")
        if st.button("⚡ Fase 3: Pubblica su Web e Genera PDF A4", type="primary", use_container_width=True):
            with st.spinner("Generazione PDF e pubblicazione su GitHub..."):
                dati_c = {**dati_c, "giocatori": giocatori_da_griglia("griglia_casa")}
                dati_o = {**dati_o, "giocatori": giocatori_da_griglia("griglia_ospite")}
                pubblica_distinta(info_gara, dati_c, dati_o)
                try:  # per il PDF del resoconto; restano solo sul disco dell'app
                    salva_foto_distinte_pubblicate({"casa": file_casa.getvalue() if file_casa else None,
                                                    "ospite": file_ospite.getvalue() if file_ospite else None})
                except Exception as e:
                    st.warning(f"Foto delle distinte non salvate per il resoconto: {e}")

    render_download_buttons()
    if leggi_secret("GITHUB_TOKEN") and leggi_secret("GITHUB_REPO"):
        render_forza_attesa()



# --- ROUTING: questa app è solo per la segreteria; gli spettatori usano la pagina su GitHub Pages ---
if st.session_state.get("autenticato"):
    render_segreteria()
else:
    render_login()
