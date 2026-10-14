"""La giornata di campionato a cui si riferisce la partita ("5ª giornata")."""
import re


def normalizza_giornata(testo):
    """Il numero della giornata come testo ("5"), da "5", "5ª", "Giornata 5", "G.5", "5° turno"; "" se manca."""
    numeri = re.findall(r"\d+", str(testo or ""))
    if not numeri:
        return ""
    numero = int(numeri[0])
    return str(numero) if 1 <= numero <= 60 else ""


def etichetta_giornata(testo):
    numero = normalizza_giornata(testo)
    return f"{numero}ª giornata" if numero else ""


def campionato_e_giornata(campionato, giornata):
    """"Prima Categoria girone E · 5ª giornata", per PDF ed elenchi."""
    return " · ".join(x for x in (str(campionato or "").strip(), etichetta_giornata(giornata)) if x)
