import streamlit as st

from giornata import normalizza_giornata
from nomi_file import nome_file_gara
from stagioni import campionati_correnti


ALTRO = "✏️ Altro (lo scrivo io)"


def scegli_campionato(attuale, chiave=None):
    """(anno sportivo, campionato) scelto dall'elenco impostato in ⚙️ Opzioni → 🏆 Campionati.
    Senza elenco si scrive a mano come prima."""
    stagione, elenco = campionati_correnti()
    if not elenco:
        campionato = st.text_input("🏆 Campionato / Categoria", value=attuale or "", key=chiave,
                                   help="Imposta i campionati della società in ⚙️ Opzioni → 🏆 Campionati "
                                        "per sceglierli da un elenco")
        return stagione, campionato
    if attuale in elenco:
        indice = elenco.index(attuale)
    else:
        indice = 0 if len(elenco) == 1 and not attuale else (len(elenco) if attuale else None)
    scelta = st.selectbox(f"🏆 Campionato / Categoria ({stagione})", elenco + [ALTRO], index=indice,
                          placeholder="Scegli il campionato", key=chiave and f"{chiave}_scelta")
    if scelta == ALTRO:
        return stagione, st.text_input("Campionato non in elenco", value=attuale or "", key=chiave,
                                       label_visibility="collapsed", placeholder="Scrivi il campionato")
    return stagione, scelta or ""


def render_info_match(info):
    """Mostra i campi di input della terna arbitrale e informazioni gara"""
    st.subheader("🏁 Informazioni Generali Match (Terna Ufficiale)")
    c_g1, c_g2 = st.columns(2)
    with c_g1:
        stagione, campionato = scegli_campionato(info["campionato"])
        arbitro = st.text_input("🏁 Arbitro (Nome e Cognome)", value=info.get("arbitro", ""))
        ass1 = st.text_input("🚩 Assistente Arbitrale 1", value=info.get("ass_casa", ""))
    with c_g2:
        c_data, c_giornata = st.columns([3, 1])
        data = c_data.text_input("📅 Data Partita", value=info["data"])
        giornata = c_giornata.text_input("📆 Giornata", value=info.get("giornata", ""), placeholder="es. 5")
        ass2 = st.text_input("🚩 Assistente Arbitrale 2", value=info.get("ass_ospite", ""))
    return {"campionato": campionato, "stagione": stagione, "giornata": normalizza_giornata(giornata), "data": data,
            "arbitro": arbitro,
            "assistente1": ass1, "assistente2": ass2}


def _nome_distinta():
    d = st.session_state.get("ultima_distinta") or {}
    return nome_file_gara("Distinta", (d.get("info_gara") or {}).get("data", ""),
                          (d.get("casa") or {}).get("squadra", ""), (d.get("ospite") or {}).get("squadra", ""))


def render_download_buttons():
    """Mostra l'unico pulsante ufficiale per scaricare il PDF generato"""
    if "pdf_interattivo_pronto" in st.session_state:
        st.write("")
        st.download_button(
            label="💾 SCARICA DISTINTA UFFICIALE GENERATA (PDF)",
            data=st.session_state["pdf_interattivo_pronto"],
            file_name=_nome_distinta(),
            mime="application/pdf",
            type="primary",
            width="stretch",
        )
