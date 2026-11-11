"""Politica de contrasenias (design, decision 5).

- entre 10 y 128 caracteres;
- no es una contrasenia comun (ni su palabra base: "password123" -> "password");
- distinta del email;
- SIN reglas de composicion forzadas (mayuscula, numero, simbolo).
"""

import re
from functools import lru_cache
from pathlib import Path

MINIMO = 10
MAXIMO = 128

_ARCHIVO = Path(__file__).parent / "data" / "contrasenias_comunes.txt"
# Numeros y simbolos al final que se agregan a una palabra comun ("dragon2024!").
_SUFIJO = re.compile(r"[\d\W_]+$")


@lru_cache
def _comunes() -> frozenset[str]:
    lineas = _ARCHIVO.read_text(encoding="utf-8").splitlines()
    return frozenset(l.strip().lower() for l in lineas if l.strip() and not l.startswith("#"))


def problemas(contrasenia: str, email: str | None = None) -> list[str]:
    """Lista de motivos por los que la contrasenia no cumple la politica (vacia si cumple)."""
    if len(contrasenia) < MINIMO:
        return [f"La contraseña debe tener al menos {MINIMO} caracteres."]
    if len(contrasenia) > MAXIMO:
        return [f"La contraseña puede tener como máximo {MAXIMO} caracteres."]

    motivos = []
    minuscula = contrasenia.lower()
    base = _SUFIJO.sub("", minuscula)
    if minuscula in _comunes() or (base and base in _comunes()):
        motivos.append("La contraseña es demasiado común. Elegí otra.")
    if email and minuscula == email.strip().lower():
        motivos.append("La contraseña no puede ser igual al email.")
    return motivos
