"""Datos comunes a los tests de eventos."""

from datetime import UTC, datetime, timedelta


def fecha_futura(dias: int = 30) -> str:
    """Fecha ISO `dias` despues de ahora. Relativa a proposito: con una fecha
    fija, los tests empezarian a fallar solos el dia que esa fecha pase (el
    evento se informaria finalizado y no se podria publicar)."""
    return (datetime.now(UTC) + timedelta(days=dias)).isoformat()


def datos_evento(recinto_id: int, **cambios) -> dict:
    """Cuerpo valido de POST /eventos; `cambios` pisa o agrega campos."""
    return {
        "nombre": "Recital",
        "fecha": fecha_futura(),
        "recinto_id": recinto_id,
        "tipo": "recital",
        "organizador": "DF Entertainment",
        **cambios,
    }
