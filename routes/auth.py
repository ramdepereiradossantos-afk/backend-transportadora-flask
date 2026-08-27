from flask import Blueprint, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required
)

from extensions import db
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


@auth_bp.route("/api/usuarios/<int:id>/alterar-senha", methods=["POST"])
@jwt_required()
def api_alterar_senha(id):
    usuario_id = int(get_jwt_identity())

    if usuario_id != id:
        return {
            "erro": "Você só pode alterar a sua própria senha."
        }, 403

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return {
            "erro": "Usuário não autorizado."
        }, 401

    dados = request.get_json() or {}

    senha_atual = dados.get("senha_atual", "").strip()
    nova_senha = dados.get("nova_senha", "").strip()

    if not senha_atual or not nova_senha:
        return {
            "erro": "Informe a senha atual e a nova senha."
        }, 400

    if usuario.senha != senha_atual:
        return {
            "erro": "Senha atual incorreta."
        }, 400

    if len(nova_senha) < 6:
        return {
            "erro": "A nova senha deve ter pelo menos 6 caracteres."
        }, 400

    if nova_senha == usuario.senha:
        return {
            "erro": "A nova senha deve ser diferente da senha atual."
        }, 400

    usuario.senha = nova_senha
    db.session.commit()

    return {
        "mensagem": "Senha alterada com sucesso!"
    }, 200
