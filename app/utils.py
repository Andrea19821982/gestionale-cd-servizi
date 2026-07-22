from fastapi import HTTPException
from sqlalchemy.orm import Session


def ottieni_o_404(db: Session, modello, id_valore):
    """Recupera un record per chiave primaria o solleva 404 invece di
    lasciare che un AttributeError su None finisca in un 500 non gestito
    (es. link/form rimasti aperti su un record nel frattempo eliminato)."""
    oggetto = db.get(modello, id_valore)
    if oggetto is None:
        raise HTTPException(status_code=404, detail=f"{modello.__name__} non trovato.")
    return oggetto


def checkbox_a_bool(valore: str | None) -> bool:
    """Un checkbox HTML non spuntato non compare affatto nel form inviato:
    il valore arriva come None, non come stringa vuota o 'off'."""
    return valore == "on"


def fk_opzionale_o_400(db: Session, modello, valore: str) -> int | None:
    """Converte il valore testuale di una <select> in un id valido, o solleva
    400 se non è un intero o non corrisponde a nessun record esistente.
    Stringa vuota -> None (campo facoltativo lasciato vuoto)."""
    if not valore:
        return None
    try:
        id_valore = int(valore)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Valore non valido per {modello.__name__}.")
    if db.get(modello, id_valore) is None:
        raise HTTPException(
            status_code=400, detail=f"{modello.__name__} con id {id_valore} non trovato."
        )
    return id_valore
