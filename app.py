import hashlib
import hmac
import io
import json
from datetime import datetime, timezone

import pandas as pd
import qrcode
import streamlit as st

import archivio_cloud
from ui_archivio import render_archivio
from cronaca_manager import (
    leggi_distinta_caricata,
    salva_distinta_caricata,
    salva_foto_distinte_pubblicate,
    togli_distinte_caricate,
)
from estrattore import analizza_distinta, unisci_scansioni
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


def reset_solo_dati_ai():
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
        st.info("Il PDF è senza sponsor: caricali dalla sezione 'Gestione Sponsor' in fondo alla pagina.")

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
    return json.loads(dati) if dati else None


def render_login():
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        st.title("⚽ Segreteria - Distinta Digitale")
        st.caption("A.S.D. Azzurra Due Carrare")
        password_corretta = leggi_secret("SEGRETERIA_PASSWORD")
        if not password_corretta:
            st.error("Password segreteria non configurata (SEGRETERIA_PASSWORD nei secrets).")
            return
        password_inserita = st.text_input("Password", type="password", key="pwd_segreteria")
        if st.button("Accedi", type="primary", use_container_width=True):
            if hmac.compare_digest(password_inserita.encode(), str(password_corretta).encode()):
                st.session_state["autenticato"] = True
                st.rerun()
            else:
                st.error("❌ Password errata. Accesso negato.")


def azzera_sezione_distinta():
    """Dopo l'archiviazione di una partita: via foto caricate, dati letti, PDF e ultima distinta."""
    for chiave in ["dati_mappati", "macro_info", "firma_scansione_attiva", "pdf_interattivo_pronto",
                   "ultima_distinta", "uploader_file_casa", "uploader_file_ospite",
                   "distinta_caricata_casa", "distinta_caricata_ospite"]:
        st.session_state.pop(chiave, None)
    reset_stato_squadra("griglia_casa")
    reset_stato_squadra("griglia_ospite")


def render_segreteria():
    if st.session_state.pop("azzera_distinta", False):
        azzera_sezione_distinta()
    col_titolo, col_esci = st.columns([5, 1])
    with col_titolo:
        st.title("⚽ Centro Gestione Gara - Pannello Segreteria")
    with col_esci:
        st.write("")
        if st.button("Esci", type="secondary", use_container_width=True):
            st.session_state["autenticato"] = False
            st.rerun()

    if "vai_a_sezione" in st.session_state:  # es. "Riapri" dall'archivio porta alla Cronaca
        st.session_state["sezione_segreteria"] = st.session_state.pop("vai_a_sezione")
    sezione = st.radio(
        "Sezione", ["📋 Distinta", "🎙️ Cronaca partita", "📚 Archivio"], horizontal=True,
        label_visibility="collapsed", key="sezione_segreteria",
    )
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
            with c_scan:
                if st.button("🔍 Fase 1: Esegui Scansione AI delle Liste", type="primary", use_container_width=True):
                    with st.spinner("Estrazione giocatori e date in corso con GPT-4o..."):
                        try:
                            casa_raw = analizza_distinta(file_casa, "CASA", api_key_openai)
                            ospite_raw = analizza_distinta(file_ospite, "OSPITE", api_key_openai)
                        except Exception as e:
                            st.error(f"Errore nell'estrazione: {e}")
                        else:
                            st.session_state["griglia_casa"] = pd.DataFrame(casa_raw["giocatori"]).set_index("N°")
                            st.session_state["griglia_ospite"] = pd.DataFrame(ospite_raw["giocatori"]).set_index("N°")
                            pulisci_widget_squadra("griglia_casa")
                            pulisci_widget_squadra("griglia_ospite")
                            st.session_state["macro_info"] = unisci_scansioni(casa_raw, ospite_raw)
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
        info_gara = render_info_match(st.session_state["macro_info"])

        st.markdown("---")
        c_sq1, c_sq2 = st.columns(2)
        inf = st.session_state["macro_info"]

        with c_sq1:
            dati_c = render_colonna_squadra("🏠 SQUADRA CASA", "griglia_casa", inf["all_casa"], inf.get("nome_casa", ""))
        with c_sq2:
            dati_o = render_colonna_squadra("🚀 SQUADRA OSPITE", "griglia_ospite", inf["all_ospite"], inf.get("nome_ospite", ""))

        mancanti = [n for n, v in (("data", inf.get("data")), ("nome squadra casa", inf.get("nome_casa")),
                                   ("nome squadra ospite", inf.get("nome_ospite"))) if not v]
        if mancanti:
            st.info("Non sono riuscito a leggere dalle distinte: " + ", ".join(mancanti) + ". Compilali a mano prima di pubblicare.")
        for avviso in inf.get("avvisi", []):
            st.warning(avviso)

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

    st.markdown("---")
    render_gestione_sponsor(
        leggi_secret("GITHUB_TOKEN"), leggi_secret("GITHUB_REPO"), leggi_secret("GITHUB_BRANCH")
    )


# --- ROUTING: questa app è solo per la segreteria; gli spettatori usano la pagina su GitHub Pages ---
if st.session_state.get("autenticato"):
    render_segreteria()
else:
    render_login()
