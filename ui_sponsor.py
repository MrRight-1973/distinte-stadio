"""Gestione degli sponsor, nella sezione Opzioni del pannello segreteria.

Si caricano i loghi (anche tutti insieme), il sistema li pulisce e li dispone da solo;
con le frecce si cambia l'ordine, col cestino si toglie un logo. "Salva e pubblica"
aggiorna il repository della pagina: la pagina web li mostra dopo 1-2 minuti,
il PDF li usa subito.
"""
import hashlib

import streamlit as st

from github_publisher import PubblicazioneErrore
from sponsor_manager import (
    MAX_SPONSOR,
    leggi_sponsor_pubblicati,
    nome_leggibile,
    prepara_logo,
    salva_sponsor,
)

CHIAVE_LISTA = "sponsor_lista"
CHIAVE_FIRMA_SALVATA = "sponsor_firma_salvata"
CHIAVE_MESSAGGI = "sponsor_messaggi"
CHIAVE_UPLOADER = "sponsor_uploader_n"
COLONNE_ANTEPRIMA = 5


CHIAVE_PER_PDF = "sponsor_per_pdf"   # loghi (bytes) da stampare nel PDF, come caricati o salvati in questa sessione


def loghi_per_pdf(token, repo, branch=None):
    """Loghi (bytes, nell'ordine pubblicato) da stampare nel PDF.

    Restituisce (loghi, avviso). loghi è None quando non si possono leggere da GitHub
    o non c'è ancora un elenco: in quel caso il PDF usa la cartella locale di riserva.

    Se la sezione Sponsor li ha già caricati o salvati in questa sessione si usano quelli:
    sono per definizione i più recenti, mentre GitHub subito dopo un salvataggio può ancora
    rispondere con i dati vecchi.
    """
    if CHIAVE_PER_PDF in st.session_state:
        return st.session_state[CHIAVE_PER_PDF], None
    try:
        voci = leggi_sponsor_pubblicati(token, repo, branch)
    except PubblicazioneErrore as e:
        return None, f"Sponsor non letti da GitHub ({e}). Uso quelli della cartella locale."
    if voci is None:
        return None, None
    return [v["png"] for v in voci], None


def _firma(lista):
    parti = [f"{s['nome']}:{hashlib.sha1(s['png']).hexdigest()}" for s in lista]
    return hashlib.sha1("|".join(parti).encode("utf-8")).hexdigest()


def _sposta(indice, verso):
    lista = st.session_state[CHIAVE_LISTA]
    altro = indice + verso
    if 0 <= altro < len(lista):
        lista[indice], lista[altro] = lista[altro], lista[indice]


def _elimina(indice):
    lista = st.session_state[CHIAVE_LISTA]
    if 0 <= indice < len(lista):
        del lista[indice]


def _aggiungi(file_caricati):
    lista = st.session_state[CHIAVE_LISTA]
    messaggi = []
    presenti = {hashlib.sha1(s["png"]).hexdigest() for s in lista}
    saltati = 0
    for f in file_caricati:
        if len(lista) >= MAX_SPONSOR:
            saltati += 1
            continue
        try:
            png = prepara_logo(f.getvalue())
        except ValueError as e:
            messaggi.append(("error", f"{f.name}: {e}."))
            continue
        impronta = hashlib.sha1(png).hexdigest()
        if impronta in presenti:
            messaggi.append(("info", f"{f.name}: era già presente, non l'ho aggiunto."))
            continue
        presenti.add(impronta)
        lista.append({"nome": f.name, "png": png})
    if saltati:
        messaggi.append(("warning", f"Limite di {MAX_SPONSOR} sponsor raggiunto: {saltati} file non aggiunti."))
    st.session_state[CHIAVE_MESSAGGI] = messaggi


def _carica_dalla_pubblicazione(token, repo, branch):
    """Porta in sessione gli sponsor oggi pubblicati. False se non è stato possibile."""
    try:
        pubblicati = leggi_sponsor_pubblicati(token, repo, branch)
    except PubblicazioneErrore as e:
        st.error(f"Non riesco a leggere gli sponsor da GitHub: {e}")
        return False
    lista = [{"nome": v["nome"], "png": v["png"]} for v in (pubblicati or [])]
    st.session_state[CHIAVE_LISTA] = lista
    st.session_state[CHIAVE_FIRMA_SALVATA] = _firma(lista)
    # nessun elenco su GitHub (None) -> il PDF userà la cartella locale di riserva
    st.session_state[CHIAVE_PER_PDF] = None if pubblicati is None else [s["png"] for s in lista]
    return True


def render_gestione_sponsor(token, repo, branch=None):
    with st.container():
        st.caption(f"Loghi degli sponsor per la pagina live e i PDF (massimo {MAX_SPONSOR}).")
        if not (token and repo):
            st.info("Servono GITHUB_TOKEN e GITHUB_REPO nei secrets per gestire gli sponsor.")
            return
        if CHIAVE_LISTA not in st.session_state and not _carica_dalla_pubblicazione(token, repo, branch):
            return

        for tipo, testo in st.session_state.pop(CHIAVE_MESSAGGI, []):
            getattr(st, tipo)(testo)

        lista = st.session_state[CHIAVE_LISTA]
        st.caption(
            "Carica i loghi anche tutti insieme, in qualsiasi formato e dimensione: li pulisco io "
            "(ritaglio dei margini bianchi, ridimensionamento) e li dispongo in righe equilibrate "
            "nella pagina e nel PDF. L'ordine è quello di caricamento; con le frecce lo puoi cambiare."
        )

        n = st.session_state.get(CHIAVE_UPLOADER, 0)
        spazio = MAX_SPONSOR - len(lista)
        caricati = st.file_uploader(
            f"Aggiungi loghi (PNG o JPG) — posti liberi: {spazio}",
            type=["png", "jpg", "jpeg"], accept_multiple_files=True,
            key=f"sponsor_up_{n}", disabled=spazio <= 0,
        )
        if caricati and st.button("➕ Aggiungi i loghi selezionati", key="sponsor_aggiungi"):
            _aggiungi(caricati)
            st.session_state[CHIAVE_UPLOADER] = n + 1  # svuota il selettore file
            st.rerun()

        if not lista:
            st.info("Nessuno sponsor. Il PDF e la pagina verranno pubblicati senza la fascia sponsor.")
        for inizio in range(0, len(lista), COLONNE_ANTEPRIMA):
            colonne = st.columns(COLONNE_ANTEPRIMA)
            for offset, colonna in enumerate(colonne):
                i = inizio + offset
                if i >= len(lista):
                    break
                with colonna:
                    st.image(lista[i]["png"], width=110)
                    st.caption(f"{i + 1}. {nome_leggibile(lista[i]['nome'])}")
                    b1, b2, b3 = st.columns(3)
                    b1.button("◀", key=f"sponsor_sx_{i}", disabled=i == 0,
                              on_click=_sposta, args=(i, -1), help="Sposta prima")
                    b2.button("▶", key=f"sponsor_dx_{i}", disabled=i == len(lista) - 1,
                              on_click=_sposta, args=(i, 1), help="Sposta dopo")
                    b3.button("🗑️", key=f"sponsor_del_{i}", on_click=_elimina, args=(i,), help="Elimina")

        modificato = _firma(lista) != st.session_state.get(CHIAVE_FIRMA_SALVATA)
        if modificato:
            st.warning("Ci sono modifiche non ancora pubblicate.")
        if st.button("💾 Salva e pubblica sponsor", type="primary", disabled=not modificato,
                     key="sponsor_salva", width="stretch"):
            with st.spinner("Pubblicazione degli sponsor su GitHub..."):
                try:
                    salva_sponsor(token, repo, lista, branch)
                except (PubblicazioneErrore, ValueError) as e:
                    st.error(f"❌ Sponsor non pubblicati: {e}")
                else:
                    st.session_state[CHIAVE_FIRMA_SALVATA] = _firma(lista)
                    st.session_state[CHIAVE_PER_PDF] = [s["png"] for s in lista]
                    # il PDF già generato non contiene gli sponsor nuovi: va rifatto con "Pubblica"
                    st.session_state.pop("pdf_interattivo_pronto", None)
                    st.session_state[CHIAVE_MESSAGGI] = [(
                        "success",
                        f"✅ {len(lista)} sponsor pubblicati. La pagina spettatori si aggiorna entro 1-2 minuti. "
                        "Il PDF già generato è stato scartato: premi di nuovo 'Pubblica su Web e Genera PDF' "
                        "per averlo con gli sponsor aggiornati.",
                    )]
                    st.rerun()
