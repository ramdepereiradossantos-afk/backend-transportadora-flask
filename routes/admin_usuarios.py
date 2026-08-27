from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from extensions import db
from models.clientes import ClienteUsuario
from models.recursos import Motorista
from models.usuarios import UsuarioSistema
from services.auditoria import registrar_log


admin_usuarios_bp = Blueprint(
    "admin_usuarios",
    __name__
)


@admin_usuarios_bp.route(
    "/api/admin/usuarios/<int:id>/inativar",
    methods=["POST"]
)
@jwt_required()
def api_inativar_usuario(id):
    usuario_logado_id = int(get_jwt_identity())
    usuario_logado = db.session.get(
        UsuarioSistema,
        usuario_logado_id
    )

    if not usuario_logado or not usuario_logado.ativo:
        return jsonify({
            "erro": "Usuário autenticado não autorizado."
        }), 401

    if str(usuario_logado.perfil).strip().lower() != "administrador":
        return jsonify({
            "erro": "Apenas administradores podem inativar usuários."
        }), 403

    usuario = db.session.get(
        UsuarioSistema,
        id
    )

    if not usuario:
        return jsonify({
            "erro": "Usuário não encontrado."
        }), 404

    if usuario.id == usuario_logado.id:
        return jsonify({
            "erro": "Você não pode inativar o próprio usuário."
        }), 400

    if not usuario.ativo:
        return jsonify({
            "mensagem": "Este usuário já está inativo."
        }), 200

    try:
        dados_antes = {
            "ativo": usuario.ativo
        }

        usuario.ativo = False

        db.session.commit()

        registrar_log(
            acao="Inativação de usuário",
            detalhes=(
                f"O usuário {usuario_logado.nome} "
                f"inativou {usuario.nome}."
            ),
            modulo="Usuários",
            entidade="UsuarioSistema",
            entidade_id=usuario.id,
            antes=dados_antes,
            depois={
                "ativo": usuario.ativo
            },
            usuario_id=usuario_logado.id,
            usuario_nome=usuario_logado.nome,
            perfil=usuario_logado.perfil
        )

        return jsonify({
            "mensagem": "Usuário inativado com sucesso!"
        }), 200

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO INATIVAR USUÁRIO:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível inativar o usuário."
        }), 500


@admin_usuarios_bp.route(
    "/api/admin/usuarios/<int:id>",
    methods=["GET"]
)
@jwt_required()
def api_buscar_usuario(id):
    usuario_logado_id = int(get_jwt_identity())

    usuario_logado = db.session.get(
        UsuarioSistema,
        usuario_logado_id
    )

    if not usuario_logado or not usuario_logado.ativo:
        return jsonify({
            "erro": "Usuário autenticado não autorizado."
        }), 401

    if str(usuario_logado.perfil).strip().lower() != "administrador":
        return jsonify({
            "erro": "Apenas administradores podem gerenciar usuários."
        }), 403

    usuario = db.session.get(
        UsuarioSistema,
        id
    )

    if not usuario:
        return jsonify({
            "erro": "Usuário não encontrado."
        }), 404

    return jsonify({
        "id": usuario.id,
        "nome": usuario.nome,
        "usuario": usuario.usuario,
        "email": usuario.email or "",
        "perfil": usuario.perfil,
        "ativo": usuario.ativo,
    }), 200

@admin_usuarios_bp.route(
   "/api/admin/usuarios",
    methods=["GET", "POST"]
)
@jwt_required()
def api_admin_usuarios():
    usuario_logado_id = int(get_jwt_identity())

    usuario_logado = db.session.get(
        UsuarioSistema,
        usuario_logado_id
    )

    if not usuario_logado or not usuario_logado.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_logado.perfil).strip().lower() != "administrador":
        return jsonify({
            "erro": "Apenas administradores podem gerenciar usuários."
        }), 403

    if request.method == "GET":
        usuarios = UsuarioSistema.query.order_by(
            UsuarioSistema.data_criacao.desc()
        ).all()

        lista = []

        for usuario in usuarios:
            lista.append({
                "id": usuario.id,
                "nome": usuario.nome,
                "email": usuario.email or "",
                "usuario": usuario.usuario,
                "perfil": usuario.perfil,
                "ativo": usuario.ativo,
                "data_criacao": (
                    usuario.data_criacao.strftime(
                        "%d/%m/%Y %H:%M"
                    )
                    if usuario.data_criacao
                    else ""
                )
            })

        return jsonify(lista), 200

    dados = request.get_json(silent=True) or {}

    nome = str(dados.get("nome", "")).strip()
    email = str(dados.get("email", "")).strip().lower()
    nome_usuario = str(
        dados.get("usuario", "")
    ).strip()
    senha = str(dados.get("senha", "")).strip()
    perfil = str(
        dados.get("perfil", "operador")
    ).strip().lower()

    if not nome or not nome_usuario or not senha:
        return jsonify({
            "erro": "Nome, usuário e senha são obrigatórios."
        }), 400

    if len(senha) < 6:
        return jsonify({
            "erro": "A senha deve ter pelo menos 6 caracteres."
        }), 400

    perfis_permitidos = [
        "administrador",
        "operador",
        "motorista",
        "cliente"
    ]

    if perfil not in perfis_permitidos:
        return jsonify({
            "erro": "Perfil inválido."
        }), 400

    usuario_existente = UsuarioSistema.query.filter_by(
        usuario=nome_usuario
    ).first()

    if usuario_existente:
        return jsonify({
            "erro": "Este nome de usuário já está cadastrado."
        }), 409

    if email:
        email_existente = UsuarioSistema.query.filter_by(
            email=email
        ).first()

        if email_existente:
            return jsonify({
                "erro": "Este e-mail já está cadastrado no sistema."
            }), 409

        if perfil == "cliente":
            cliente_existente = ClienteUsuario.query.filter_by(
                email=email
            ).first()

            if cliente_existente:
                return jsonify({
                    "erro": (
                        "Já existe um cliente cadastrado "
                        "com este e-mail."
                    )
                }), 409

    try:
        novo_usuario = UsuarioSistema(
            nome=nome,
            email=email,
            usuario=nome_usuario,
            senha=senha,
            perfil=perfil,
            ativo=True
        )

        db.session.add(novo_usuario)
        db.session.flush()

        if perfil == "cliente":
            cliente_login = ClienteUsuario(
                nome=nome,
                empresa=nome,
                email=email,
                senha=senha,
                ativo=True
            )

            db.session.add(cliente_login)

        if perfil == "motorista":
            motorista_existente = Motorista.query.filter_by(
                usuario=nome_usuario
            ).first()

            if motorista_existente:
                db.session.rollback()

                return jsonify({
                    "erro": (
                        "Já existe um motorista com "
                        "este nome de usuário."
                    )
                }), 409

            motorista = Motorista(
                nome=nome,
                email=email,
                usuario=nome_usuario,
                senha=senha,
                status="Ativo"
            )

            motorista.usuario_sistema = novo_usuario

            db.session.add(motorista)

        db.session.commit()

        return jsonify({
            "mensagem": "Usuário criado com sucesso!"
        }), 201

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO CRIAR USUÁRIO:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível criar o usuário."
        }), 500


@admin_usuarios_bp.route(
    "/api/admin/usuarios/<int:id>",
    methods=["PUT"]
)
@jwt_required()
def api_editar_usuario(id):
    usuario_logado_id = int(get_jwt_identity())

    usuario_logado = db.session.get(
        UsuarioSistema,
        usuario_logado_id
    )

    if not usuario_logado or not usuario_logado.ativo:
        return jsonify({
            "erro": "Usuário autenticado não autorizado."
        }), 401

    if str(usuario_logado.perfil).strip().lower() != "administrador":
        return jsonify({
            "erro": "Apenas administradores podem editar usuários."
        }), 403

    usuario = db.session.get(
        UsuarioSistema,
        id
    )

    if not usuario:
        return jsonify({
            "erro": "Usuário não encontrado."
        }), 404

    dados = request.get_json(silent=True) or {}

    nome = str(
        dados.get("nome", usuario.nome)
    ).strip()

    nome_usuario = str(
        dados.get("usuario", usuario.usuario)
    ).strip()

    email = str(
        dados.get("email", usuario.email or "")
    ).strip()

    perfil = str(
        dados.get("perfil", usuario.perfil)
    ).strip().lower()

    ativo = dados.get(
        "ativo",
        usuario.ativo
    )

    if not nome:
        return jsonify({
            "erro": "Informe o nome."
        }), 400

    if not nome_usuario:
        return jsonify({
            "erro": "Informe o usuário."
        }), 400

    perfis_permitidos = [
        "administrador",
        "operador",
        "motorista",
        "cliente"
    ]

    if perfil not in perfis_permitidos:
        return jsonify({
            "erro": "Perfil inválido."
        }), 400

    usuario_duplicado = UsuarioSistema.query.filter(
        UsuarioSistema.usuario == nome_usuario,
        UsuarioSistema.id != usuario.id
    ).first()

    if usuario_duplicado:
        return jsonify({
            "erro": "Este nome de usuário já está cadastrado."
        }), 409

    if email:
        email_duplicado = UsuarioSistema.query.filter(
            UsuarioSistema.email == email,
            UsuarioSistema.id != usuario.id
        ).first()

        if email_duplicado:
            return jsonify({
                "erro": "Este e-mail já está cadastrado no sistema."
            }), 409

        cliente_email_duplicado = ClienteUsuario.query.filter(
            ClienteUsuario.email == email
        ).first()

        if (
            cliente_email_duplicado
            and cliente_email_duplicado.email
            != (usuario.email or "")
        ):
            return jsonify({
                "erro": (
                    "Este e-mail já está vinculado "
                    "a outro cliente."
                )
            }), 409

    redefinir_senha = bool(
        dados.get("redefinir_senha", False)
    )

    nova_senha = str(
        dados.get("nova_senha", "")
    ).strip()

    if redefinir_senha and len(nova_senha) < 6:
        return jsonify({
            "erro": (
                "A nova senha deve ter "
                "pelo menos 6 caracteres."
            )
        }), 400

    dados_antes = {
        "nome": usuario.nome,
        "usuario": usuario.usuario,
        "email": usuario.email or "",
        "perfil": usuario.perfil,
        "ativo": usuario.ativo,
    }

    try:
        usuario.nome = nome
        usuario.usuario = nome_usuario
        usuario.email = email
        usuario.perfil = perfil
        usuario.ativo = bool(ativo)

        if redefinir_senha:
            usuario.senha = nova_senha

        dados_depois = {
            "nome": usuario.nome,
            "usuario": usuario.usuario,
            "email": usuario.email or "",
            "perfil": usuario.perfil,
            "ativo": usuario.ativo,
            "senha_redefinida": redefinir_senha,
        }

        db.session.commit()

        registrar_log(
            acao="Edição de usuário",
            detalhes=(
                f"O usuário {usuario_logado.nome} "
                f"alterou o cadastro de {usuario.nome}."
            ),
            modulo="Usuários",
            entidade="UsuarioSistema",
            entidade_id=usuario.id,
            antes=dados_antes,
            depois=dados_depois,
            usuario_id=usuario_logado.id,
            usuario_nome=usuario_logado.nome,
            perfil=usuario_logado.perfil
        )

        return jsonify({
            "mensagem": "Usuário atualizado com sucesso!"
        }), 200

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO EDITAR USUÁRIO:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível atualizar o usuário."
        }), 500
