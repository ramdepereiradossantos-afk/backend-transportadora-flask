import os

from flask import Blueprint, current_app, jsonify, send_from_directory
from flask_jwt_extended import get_jwt_identity, jwt_required

from extensions import db
from models.comprovantes import ArquivoComprovanteViagem
from models.usuarios import UsuarioSistema
from services.autorizacao_comprovantes import (
    cliente_pode_acessar_viagem,
    motorista_pode_acessar_viagem,
)


comprovantes_bp = Blueprint("comprovantes", __name__)


@comprovantes_bp.route(
    "/api/comprovantes/arquivos/<int:arquivo_id>/download",
    methods=["GET"]
)
@jwt_required()
def api_download_arquivo_comprovante(arquivo_id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    arquivo = db.session.get(ArquivoComprovanteViagem, arquivo_id)

    if not arquivo or not arquivo.viagem:
        return jsonify({"erro": "Arquivo não encontrado."}), 404

    perfil = str(usuario.perfil).strip().lower()

    if perfil in ["administrador", "operador"]:
        autorizado = True
    elif perfil == "motorista":
        autorizado = motorista_pode_acessar_viagem(
            usuario,
            arquivo.viagem
        )
    elif perfil == "cliente":
        autorizado = cliente_pode_acessar_viagem(
            usuario,
            arquivo.viagem
        )
    else:
        autorizado = False

    if not autorizado:
        return jsonify({"erro": "Acesso não autorizado ao arquivo."}), 403

    nome_arquivo = str(arquivo.nome_arquivo or "").strip()

    if (
        not nome_arquivo
        or os.path.isabs(nome_arquivo)
        or os.path.basename(nome_arquivo) != nome_arquivo
    ):
        return jsonify({"erro": "Arquivo não encontrado."}), 404

    upload_folder = os.path.abspath(current_app.config["UPLOAD_FOLDER"])
    caminho_arquivo = os.path.abspath(
        os.path.join(upload_folder, nome_arquivo)
    )

    if (
        os.path.commonpath([upload_folder, caminho_arquivo]) != upload_folder
        or not os.path.isfile(caminho_arquivo)
    ):
        return jsonify({"erro": "Arquivo não encontrado."}), 404

    return send_from_directory(
        upload_folder,
        nome_arquivo,
        as_attachment=False,
        download_name=nome_arquivo
    )
