"""1.2 Configuracion nueva de auth por variables de entorno."""

from app.config import Settings


def test_variables_de_email_redis_y_frontend(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("SMTP_HOST", "smtp.proveedor.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "usuario")
    monkeypatch.setenv("SMTP_PASSWORD", "secreto")
    monkeypatch.setenv("SMTP_TLS", "true")
    monkeypatch.setenv("EMAIL_FROM", "hola@ticketera.com")
    monkeypatch.setenv("FRONTEND_URL", "https://ticketera.com")
    s = Settings(database_url="x", jwt_secret="x")
    assert (s.smtp_host, s.smtp_port, s.smtp_user, s.smtp_password, s.smtp_tls) == (
        "smtp.proveedor.com", 587, "usuario", "secreto", True)
    assert (s.redis_url, s.email_from, s.frontend_url) == (
        "redis://redis:6379/0", "hola@ticketera.com", "https://ticketera.com")


def test_valores_por_defecto_apuntan_a_mailpit(monkeypatch):
    for v in ("SMTP_HOST", "SMTP_PORT", "SMTP_TLS", "REDIS_URL"):
        monkeypatch.delenv(v, raising=False)
    s = Settings(database_url="x", jwt_secret="x")
    assert (s.smtp_host, s.smtp_port, s.smtp_tls) == ("mailpit", 1025, False)
    assert (s.intentos_maximos, s.verificacion_ttl_horas, s.restablecimiento_ttl_minutos) == (5, 24, 30)
