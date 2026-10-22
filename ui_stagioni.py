"""⚙️ Opzioni → 🏆 Campionati: anno sportivo in corso, gruppi squadra e loro competizioni."""
import streamlit as st

from anagrafica import rinomina_gruppo
from presenze import rinomina_gruppo as rinomina_gruppo_presenze
from rose import rinomina_rosa
from utenti import rinomina_gruppo_allenatori
from stagioni import impostazioni_stagioni, salva_stagioni, stagione_di_oggi

NUOVO_GRUPPO = "➕ Nuovo gruppo squadra"
NUOVA_COMPETIZIONE = "➕ Nuova competizione"


def _successiva(stagione):
    inizio = int(stagione[:4]) + 1
    return f"{inizio}/{(inizio + 1) % 100:02d}"


def render_opzioni_campionati():
    st.subheader("🏆 Anno sportivo, squadre e competizioni")
    st.caption("Tre passi: l'anno sportivo, poi i gruppi squadra (una rosa ciascuno), poi le competizioni di ogni "
               "gruppo (campionato, coppa...). Nella Distinta si sceglie la competizione; archivio e statistiche "
               "si filtrano per gruppo o per singola competizione.")
    for tipo, testo in st.session_state.pop("stagioni_messaggi", []):
        getattr(st, tipo)(testo)
    # Dopo un salvataggio: i menu puntano a ciò che si è appena creato o rinominato, i campi tornano vuoti
    for chiave, valore in st.session_state.pop("stagioni_seleziona", {}).items():
        if valore is None:
            st.session_state.pop(chiave, None)
        else:
            st.session_state[chiave] = valore
    imp = impostazioni_stagioni()
    oggi = stagione_di_oggi()
    anni = sorted(set(imp["stagioni"]) | {imp["corrente"], oggi, _successiva(oggi)}, reverse=True)
    corrente = st.selectbox("1️⃣ 📅 Anno sportivo in corso", anni, index=anni.index(imp["corrente"]), key="opz_stagione",
                            help="Vale per le nuove distinte; le partite già giocate restano nel loro anno")
    if corrente != imp["corrente"]:
        salva_stagioni(corrente, imp["stagioni"])
        st.session_state["stagioni_messaggi"] = [("success", f"Anno sportivo in corso: {corrente}.")]
        st.rerun()

    gruppi = imp["stagioni"].get(corrente, [])
    precedenti = [a for a in sorted(imp["stagioni"], reverse=True) if a < corrente and imp["stagioni"][a]]
    if not gruppi and precedenti and st.button(f"📋 Copia squadre e competizioni del {precedenti[0]}", width="stretch"):
        _salva(imp, corrente, imp["stagioni"][precedenti[0]], f"Copiate squadre e competizioni del {precedenti[0]}.")

    # 2️⃣ Gruppo squadra
    nomi = [g["gruppo"] for g in gruppi]
    gruppo = st.selectbox("2️⃣ 👥 Gruppo squadra", nomi + [NUOVO_GRUPPO], key=f"opz_gruppo_{corrente}",
                          help="La squadra (es. Prima Squadra, Under 17): una sola rosa per tutte le sue competizioni")
    if gruppo == NUOVO_GRUPPO:
        c1, c2 = st.columns(2)
        nome = _pulito(c1.text_input("Nome del gruppo squadra", key="opz_nuovo_gruppo", placeholder="es. Prima Squadra"))
        prima = _pulito(c2.text_input("Prima competizione", key="opz_nuova_prima", placeholder="es. Prima Categoria girone E"))
        if st.button("➕ Aggiungi il gruppo", width="stretch", disabled=not (nome and prima)):
            if nome.lower() in (n.lower() for n in nomi):
                st.error(f"«{nome}» c'è già.")
            elif prima.lower() in (c.lower() for g in gruppi for c in g["competizioni"]):
                st.error(f"«{prima}» è già in un altro gruppo.")
            else:
                _salva(imp, corrente, gruppi + [{"gruppo": nome, "competizioni": [prima]}],
                       f"Gruppo «{nome}» aggiunto: altre competizioni (coppa...) si aggiungono dal terzo menu.",
                       {f"opz_gruppo_{corrente}": nome, "opz_nuovo_gruppo": None, "opz_nuova_prima": None})
        _riepilogo(gruppi)
        return
    with st.popover("✏️ Rinomina o elimina il gruppo", width="stretch"):
        nuovo = _pulito(st.text_input("Nuovo nome", value=gruppo, key=f"opz_rinomina_gruppo_{gruppo}"))
        if st.button("💾 Rinomina", key="opz_rinomina_gruppo_ok", disabled=not nuovo or nuovo == gruppo):
            if nuovo.lower() in (n.lower() for n in nomi if n != gruppo):
                st.error(f"«{nuovo}» c'è già.")
            else:
                rinomina_rosa(corrente, gruppo, nuovo)
                rinomina_gruppo(corrente, gruppo, nuovo)  # i ragazzi dell'anagrafica
                rinomina_gruppo_presenze(corrente, gruppo, nuovo)
                rinomina_gruppo_allenatori(gruppo, nuovo)
                _salva(imp, corrente, [{**g, "gruppo": nuovo} if g["gruppo"] == gruppo else g for g in gruppi],
                       f"Gruppo rinominato in «{nuovo}» (la rosa resta).", {f"opz_gruppo_{corrente}": nuovo})
        if st.button(f"🗑️ Elimina «{gruppo}» e le sue competizioni", key="opz_elimina_gruppo"):
            _salva(imp, corrente, [g for g in gruppi if g["gruppo"] != gruppo], f"Gruppo «{gruppo}» eliminato.",
                   {f"opz_gruppo_{corrente}": None})

    # 3️⃣ Competizioni del gruppo
    competizioni = next(g["competizioni"] for g in gruppi if g["gruppo"] == gruppo)
    tutte = [c.lower() for g in gruppi for c in g["competizioni"]]
    scelta = st.selectbox(f"3️⃣ 🏆 Competizioni di {gruppo}", competizioni + [NUOVA_COMPETIZIONE],
                          key=f"opz_competizione_{corrente}_{gruppo}", help="Campionato, coppa, torneo...")

    def con_competizioni(nuove):
        return [{**g, "competizioni": nuove} if g["gruppo"] == gruppo else g for g in gruppi]

    if scelta == NUOVA_COMPETIZIONE:
        nome = _pulito(st.text_input("Nome della nuova competizione", key="opz_nuova_competizione",
                                     placeholder="es. Coppa Veneto"))
        if st.button("➕ Aggiungi la competizione", width="stretch", disabled=not nome):
            if nome.lower() in tutte:
                st.error(f"«{nome}» c'è già.")
            else:
                _salva(imp, corrente, con_competizioni(competizioni + [nome]), f"«{nome}» aggiunta a {gruppo}.",
                       {f"opz_competizione_{corrente}_{gruppo}": nome, "opz_nuova_competizione": None})
    else:
        with st.popover("✏️ Rinomina o elimina la competizione", width="stretch"):
            nuovo = _pulito(st.text_input("Nuovo nome", value=scelta, key=f"opz_rinomina_comp_{scelta}",
                                          help="Le partite già salvate tengono il nome di prima"))
            if st.button("💾 Rinomina", key="opz_rinomina_comp_ok", disabled=not nuovo or nuovo == scelta):
                if nuovo.lower() in tutte and nuovo.lower() != scelta.lower():
                    st.error(f"«{nuovo}» c'è già.")
                else:
                    _salva(imp, corrente, con_competizioni([nuovo if c == scelta else c for c in competizioni]),
                           f"Competizione rinominata in «{nuovo}».", {f"opz_competizione_{corrente}_{gruppo}": nuovo})
            if len(competizioni) == 1:
                st.caption("È l'unica competizione del gruppo: per toglierla elimina il gruppo.")
            elif st.button(f"🗑️ Elimina «{scelta}»", key="opz_elimina_comp"):
                _salva(imp, corrente, con_competizioni([c for c in competizioni if c != scelta]), f"«{scelta}» eliminata.",
                       {f"opz_competizione_{corrente}_{gruppo}": None})
    _riepilogo(gruppi)


def _pulito(testo):
    return " ".join(str(testo or "").split())


def _salva(imp, corrente, gruppi, messaggio, seleziona=None):
    salva_stagioni(corrente, {**imp["stagioni"], corrente: gruppi})
    st.session_state["stagioni_messaggi"] = [("success", messaggio)]
    st.session_state["stagioni_seleziona"] = seleziona or {}
    st.rerun()


def _riepilogo(gruppi):
    if gruppi:
        st.caption("Impostati: " + " · ".join(f"**{g['gruppo']}** ({', '.join(g['competizioni'])})" for g in gruppi))
