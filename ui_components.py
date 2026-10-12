import streamlit as st

from nomi_file import nome_file_gara


def render_info_match(info):
    """Mostra i campi di input della terna arbitrale e informazioni gara"""
    st.subheader("🏁 Informazioni Generali Match (Terna Ufficiale)")
    c_g1, c_g2 = st.columns(2)
    with c_g1:
        campionato = st.text_input("🏆 Campionato / Categoria", value=info["campionato"])
        arbitro = st.text_input("🏁 Arbitro (Nome e Cognome)", value="")
        ass1 = st.text_input("🚩 Assistente Arbitrale 1", value=info.get("ass_casa", ""))
    with c_g2:
        data = st.text_input("📅 Data Partita", value=info["data"])
        st.write("")
        ass2 = st.text_input("🚩 Assistente Arbitrale 2", value=info.get("ass_ospite", ""))
    return {"campionato": campionato, "data": data, "arbitro": arbitro, "assistente1": ass1, "assistente2": ass2}


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
            use_container_width=True,
        )
