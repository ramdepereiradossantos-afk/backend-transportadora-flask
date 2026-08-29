import os
from datetime import timedelta


JWT_SECRET_KEY = os.environ.get(
    "JWT_SECRET_KEY",
    ""
).strip()

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY não configurada."
    )

if len(JWT_SECRET_KEY) < 32:
    raise RuntimeError(
        "JWT_SECRET_KEY deve possuir pelo menos 32 caracteres."
    )

JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)

CORS_RESOURCES = {
    r"/api/*": {
        "origins": [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174"
        ]
    }
}
CORS_ALLOW_HEADERS = [
    "Content-Type",
    "Authorization"
]
CORS_METHODS = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS"
]

ADMIN_BOOTSTRAP_NOME = os.environ.get(
    "ADMIN_BOOTSTRAP_NOME",
    ""
).strip()
ADMIN_BOOTSTRAP_USUARIO = os.environ.get(
    "ADMIN_BOOTSTRAP_USUARIO",
    ""
).strip()
ADMIN_BOOTSTRAP_EMAIL = os.environ.get(
    "ADMIN_BOOTSTRAP_EMAIL",
    ""
).strip()
ADMIN_BOOTSTRAP_SENHA = os.environ.get(
    "ADMIN_BOOTSTRAP_SENHA",
    ""
).strip()

CLIENTE_TESTE_EMAIL = os.environ.get(
    "CLIENTE_TESTE_EMAIL",
    "cliente@infinity.com"
)
CLIENTE_TESTE_SENHA = os.environ.get("CLIENTE_TESTE_SENHA", "123456")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

SQLALCHEMY_DATABASE_URI = "sqlite:///" + DB_PATH
SQLALCHEMY_TRACK_MODIFICATIONS = False
