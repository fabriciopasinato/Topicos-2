"""3.1 Politica de contrasenias."""

import pytest

from app.contrasenias import problemas


@pytest.mark.parametrize("contrasenia", ["a" * 9, "corta1234"])
def test_menos_de_10_caracteres(contrasenia):
    assert "al menos 10" in problemas(contrasenia)[0]


def test_10_caracteres_no_comunes_se_aceptan():
    assert problemas("tortuga-azul") == []
    assert problemas("zxcvbqwmnt") == []


def test_128_caracteres_se_aceptan_y_129_no():
    assert problemas("abcdefghij" * 12 + "klmnopqr") == []
    assert "como máximo 128" in problemas("x" * 129)[0]


@pytest.mark.parametrize("contrasenia", ["password123", "1234567890", "PASSWORD123", "qwertyuiop", "dragon2024!!"])
def test_contrasenias_comunes_o_su_palabra_base(contrasenia):
    assert any("común" in m for m in problemas(contrasenia))


def test_igual_al_email_sin_distinguir_mayusculas():
    assert any("email" in m for m in problemas("ana@example.com", "Ana@Example.com"))


def test_frase_larga_sin_simbolos_ni_mayusculas_se_acepta():
    assert problemas("caballocorrectobateria", "ana@example.com") == []


def test_palabra_rara_con_numeros_se_acepta():
    assert problemas("monkeybusiness99") == []
