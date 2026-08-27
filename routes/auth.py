from flask import Blueprint, request
from flask_jwt_extended import create_access_token

from models.usuarios import UsuarioSistema
from services.auditoria import registrar_log


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    dados = request.get_json(silent=True) or {}

    usuario_digitado = str(
        dados.get("usuario", "")
    ).strip()

    senha_digitada = str(
        dados.get("senha", "")
    ).strip()

    if not usuario_digitado or not senha_digitada:
        return {
            "erro": "Informe o usuário e a senha."
        }, 400

    usuario = UsuarioSistema.query.filter_by(
        usuario=usuario_digitado,
        senha=senha_digitada,
        ativo=True
    ).first()

    if not usuario:
        return {
            "erro": "Usuário ou senha inválidos."
        }, 401

    access_token = create_access_token(
        identity=str(usuario.id),
        additional_claims={
            "nome": usuario.nome,
            "perfil": usuario.perfil,
            "usuario": usuario.usuario,
        }
    )

    registrar_log(
        "Login no sistema",
        f"Usuário {usuario.nome} acessou o painel React.",
        usuario_id=usuario.id,
        usuario_nome=usuario.nome,
        perfil=usuario.perfil
    )

    return {
        "access_token": access_token,
        "usuario": {
            "id": usuario.id,
            "nome": usuario.nome,
            "usuario": usuario.usuario,
            "perfil": usuario.perfil,
        }
    }, 200
