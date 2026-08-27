
from flask import Flask, request, jsonify
from datetime import datetime
from werkzeug.utils import secure_filename
import os
import json
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity
)
from config import (
    ALLOWED_EXTENSIONS,
    CLIENTE_TESTE_EMAIL,
    CLIENTE_TESTE_SENHA,
    CORS_ALLOW_HEADERS,
    CORS_METHODS,
    CORS_RESOURCES,
    DB_PATH as db_path,
    JWT_ACCESS_TOKEN_EXPIRES,
    JWT_SECRET_KEY,
    SENHA_ADMIN,
    SQLALCHEMY_DATABASE_URI,
    SQLALCHEMY_TRACK_MODIFICATIONS,
    UPLOAD_FOLDER as upload_folder,
    USUARIO_ADMIN
)
from extensions import cors, db, jwt
from utils.datas import formatar_data_brasilia
from utils.valores import converter_valor_brasileiro

app = Flask(__name__)

app.config["JWT_SECRET_KEY"] = JWT_SECRET_KEY
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = JWT_ACCESS_TOKEN_EXPIRES
app.config["UPLOAD_FOLDER"] = upload_folder
app.config["ALLOWED_EXTENSIONS"] = ALLOWED_EXTENSIONS
app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = SQLALCHEMY_TRACK_MODIFICATIONS

os.makedirs(upload_folder, exist_ok=True)

db.init_app(app)
jwt.init_app(app)
cors.init_app(
    app,
    resources=CORS_RESOURCES,
    allow_headers=CORS_ALLOW_HEADERS,
    methods=CORS_METHODS
)

from models.usuarios import UsuarioSistema
from models.auditoria import LogAcao
from models.recursos import Motorista, Veiculo
from models.rotas import Rota

motorista_id = db.Column(
    db.Integer,
    db.ForeignKey("motorista.id"),
    nullable=True
)

motorista = db.relationship(
    "Motorista",
    backref="cargas"
)

data_criacao = db.Column(
    db.DateTime,
    default=datetime.utcnow
)
    
    

from models.operacao import Rastreamento, Viagem

from models.historicos import (
    HistoricoOperacao,
    HistoricoRastreamento,
    HistoricoViagem
)
from models.ocorrencias import OcorrenciaEntrega, OcorrenciaViagem
from models.comprovantes import ComprovanteEntrega, ArquivoComprovanteViagem
from models.localizacoes import LocalizacaoMotorista, LocalizacaoViagem
from utils.constantes import (
    STATUS_CARGA_ATIVOS_RECURSOS,
    STATUS_VIAGEM_ATIVOS_RECURSOS
)
from services.historicos import registrar_historico
from services.recursos import (
    motorista_possui_outra_carga_ativa,
    motorista_possui_outra_viagem_ativa,
    recalcular_disponibilidade_motorista,
    recalcular_status_veiculo,
    veiculo_possui_outra_carga_ativa,
    veiculo_possui_outra_viagem_ativa,
    veiculo_possui_status_especial
)
from services.compatibilidade_schema import (
    adicionar_colunas_auditoria,
    adicionar_colunas_operacionais
)
from routes.public import public_bp
from routes.auth import auth_bp
from routes.admin_clientes import admin_clientes_bp
from routes.admin_veiculos import admin_veiculos_bp
from routes.admin_motoristas import admin_motoristas_bp
from routes.admin_usuarios import admin_usuarios_bp
from routes.admin_dashboard import admin_dashboard_bp
from routes.admin_relatorios import admin_relatorios_bp
from routes.admin_cotacoes import admin_cotacoes_bp
from routes.portal_cliente import portal_cliente_bp

app.register_blueprint(public_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(admin_clientes_bp)
app.register_blueprint(admin_veiculos_bp)
app.register_blueprint(admin_motoristas_bp)
app.register_blueprint(admin_usuarios_bp)
app.register_blueprint(admin_dashboard_bp)
app.register_blueprint(admin_relatorios_bp)
app.register_blueprint(admin_cotacoes_bp)
app.register_blueprint(portal_cliente_bp)

with app.app_context():
    db.create_all()

    adicionar_colunas_operacionais()
    adicionar_colunas_auditoria()

    admin_padrao = UsuarioSistema.query.filter_by(
        usuario="admin"
    ).first()

    if not admin_padrao:
        admin_padrao = UsuarioSistema(
            nome="Administrador",
            usuario="admin",
            senha="ramos123",
            perfil="administrador",
            ativo=True
        )

        db.session.add(admin_padrao)
        db.session.commit()

@app.route("/api/admin/cargas", methods=["GET"])
@jwt_required()
def api_admin_cargas():
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar cargas."
        }), 403

    cargas = Rastreamento.query.order_by(
        Rastreamento.ultima_atualizacao.desc()
    ).all()

    lista = []

    for carga in cargas:
        lista.append({
            "id": carga.id,
            "codigo": carga.codigo,
            "cliente": carga.cliente,
            "status": carga.status,
            "local_atual": carga.local_atual,
            "destino": carga.destino,
            "motorista": carga.motorista_relacao.nome if carga.motorista_relacao else "",
            "veiculo": carga.veiculo_relacao.placa if carga.veiculo_relacao else "",
        })

    return lista

@app.route("/api/admin/cargas/<int:id>", methods=["GET"])
@jwt_required()
def api_admin_carga_detalhe(id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar cargas."
        }), 403

    carga = db.session.get(
        Rastreamento,
        id
    )

    if not carga:
        return jsonify({
            "erro": "Carga não encontrada."
        }), 404

    viagem = Viagem.query.filter_by(
        rastreamento_id=carga.id
    ).first()

    return jsonify({
        "id": carga.id,
        "codigo": carga.codigo,
        "cliente": carga.cliente,
        "local_atual": carga.local_atual,
        "destino": carga.destino,
        "motorista_id": carga.motorista_id,
        "motorista": (
            carga.motorista_relacao.nome
            if carga.motorista_relacao
            else ""
        ),
        "veiculo_id": carga.veiculo_id,
        "veiculo": (
            carga.veiculo_relacao.placa
            if carga.veiculo_relacao
            else ""
        ),
        "status": carga.status,
        "ultima_atualizacao": (
            carga.ultima_atualizacao.strftime("%d/%m/%Y %H:%M")
            if carga.ultima_atualizacao
            else ""
        ),
        "valor_frete": carga.valor_frete,
        "status_pagamento": carga.status_pagamento,
        "viagem_id": viagem.id if viagem else None,
    }), 200
    
@app.route("/api/admin/cargas", methods=["POST"])
@jwt_required()
def api_criar_carga():
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para criar cargas."
        }), 403

    dados = request.get_json()

    codigo = dados.get("codigo", "").strip().upper()
    cliente = dados.get("cliente", "").strip()
    status = dados.get("status", "").strip()
    local_atual = dados.get("local_atual", "").strip()
    destino = dados.get("destino", "").strip()

    if not all([codigo, cliente, status, local_atual, destino]):
        return {"erro": "Preencha todos os campos obrigatórios."}, 400

    existente = Rastreamento.query.filter_by(codigo=codigo).first()

    if existente:
        return {"erro": "Já existe uma carga com esse código."}, 400

    nova_carga = Rastreamento()
    nova_carga.codigo = codigo
    nova_carga.cliente = cliente
    nova_carga.status = status
    nova_carga.local_atual = local_atual
    nova_carga.destino = destino
    nova_carga.ultima_atualizacao = datetime.utcnow()
    nova_carga.valor_frete = converter_valor_brasileiro(
    dados.get("valor_frete")
)
    nova_carga.status_pagamento = dados.get("status_pagamento", "Pendente")

    db.session.add(nova_carga)
    db.session.flush()
    
    primeiro_evento = HistoricoRastreamento(
    rastreamento_id=nova_carga.id,
    status=nova_carga.status or "Carga criada",
    local=nova_carga.local_atual or "Origem não informada",
    observacao="Carga cadastrada no sistema."
    )

    db.session.add(primeiro_evento)
    db.session.commit()

    return {
        "mensagem": "Carga criada com sucesso!",
        "id": nova_carga.id
    }, 201
    
@app.route("/api/admin/cargas/<int:id>", methods=["PUT"])
@jwt_required()
def api_editar_carga(id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para editar cargas."
        }), 403

    carga = Rastreamento.query.get_or_404(id)
    dados = request.get_json() or {}

    # Guarda os dados anteriores antes de alterar
    local_anterior = carga.local_atual

    carga.codigo = dados.get("codigo", "").strip().upper()
    carga.cliente = dados.get("cliente", "").strip()
    carga.local_atual = dados.get("local_atual", "").strip()
    carga.destino = dados.get("destino", "").strip()
    carga.ultima_atualizacao = datetime.utcnow()

    if not all([
        carga.codigo,
        carga.cliente,
        carga.local_atual,
        carga.destino,
    ]):
        return {
            "erro": "Preencha todos os campos obrigatórios."
        }, 400

    carga.valor_frete = converter_valor_brasileiro(
        dados.get("valor_frete")
    )

    carga.status_pagamento = dados.get(
        "status_pagamento",
        "Pendente"
    )

    # Descobre se houve alteração relevante para a timeline
    local_mudou = local_anterior != carga.local_atual

    # Cria evento somente quando a localização mudar
    if local_mudou:
        evento = HistoricoRastreamento(
            rastreamento_id=carga.id,
            status=carga.status,
            local=carga.local_atual,
            observacao=(
                f"Local anterior: {local_anterior or '-'}"
            )
        )

        db.session.add(evento)

    db.session.commit()

    return {
        "mensagem": "Carga atualizada com sucesso!"
    }, 200
    
    
@app.route(
    "/api/admin/cargas/<int:id>",
    methods=["DELETE"]
)
@jwt_required()
def api_excluir_carga(id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() != "administrador":
        return jsonify({
            "erro": "Somente administradores podem excluir cargas."
        }), 403

    carga = db.session.get(
        Rastreamento,
        id
    )

    if not carga:
        return jsonify({
            "erro": "Carga não encontrada."
        }), 404

    status_bloqueados = [
        "Em coleta",
        "Carregando",
        "Em trânsito",
        "Parada operacional",
        "Saiu para entrega",
        "Entregue"
    ]

    if carga.status in status_bloqueados:
        return jsonify({
            "erro": (
                f"Não é possível excluir uma carga "
                f"com status '{carga.status}'."
            )
        }), 409

    viagem = Viagem.query.filter_by(
        rastreamento_id=carga.id
    ).first()

    if viagem:
        return jsonify({
            "erro": (
                "Não é possível excluir esta carga "
                "porque ela possui uma viagem vinculada."
            )
        }), 409

    historico = HistoricoRastreamento.query.filter_by(
        rastreamento_id=carga.id
    ).first()

    if historico:
        return jsonify({
            "erro": (
                "Não é possível excluir esta carga "
                "porque ela possui histórico de rastreamento."
            )
        }), 409

    try:
        db.session.delete(carga)
        db.session.commit()

        return jsonify({
            "mensagem": "Carga excluída com sucesso!"
        }), 200

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO EXCLUIR CARGA:",
            erro
        )

        return jsonify({
            "erro": (
                "Não foi possível excluir a carga "
                "porque existem registros vinculados a ela."
            )
        }), 409

@app.route("/api/admin/viagens", methods=["GET"])
@jwt_required()
def api_admin_viagens():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar viagens."
        }), 403

    viagens = Viagem.query.order_by(
        Viagem.data_criacao.desc()
    ).all()

    lista = []

    for viagem in viagens:
        lista.append({
            "id": viagem.id,
            "codigo_carga": viagem.carga.codigo if viagem.carga else "",
            "cliente": viagem.carga.cliente if viagem.carga else "",
            "motorista": viagem.motorista.nome if viagem.motorista else "",
            "veiculo": viagem.veiculo.placa if viagem.veiculo else "",
            "origem": viagem.origem,
            "destino": viagem.destino,
            "status": viagem.status,
            "data_criacao": formatar_data_brasilia(viagem.data_criacao),
            "data_criacao_iso": viagem.data_criacao.isoformat() if viagem.data_criacao else None,
        })

    return jsonify(lista), 200

@app.route("/api/admin/viagens", methods=["POST"])
@jwt_required()
def api_criar_viagem():
    # Endpoint legado mantido por compatibilidade.
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para criar viagens."
        }), 403

    dados = request.get_json(silent=True) or {}

    rastreamento_id = dados.get("rastreamento_id")
    motorista_id = dados.get("motorista_id")
    veiculo_id = dados.get("veiculo_id")

    carga = Rastreamento.query.get(rastreamento_id)

    if not carga:
        return {"erro": "Carga não encontrada."}, 404

    nova_viagem = Viagem(
        rastreamento_id=int(rastreamento_id),
        motorista_id=int(motorista_id) if motorista_id else None,
        veiculo_id=int(veiculo_id) if veiculo_id else None,
        origem=carga.local_atual,
        destino=carga.destino,
        status="Planejada"
    )

    db.session.add(nova_viagem)
    db.session.flush()
    
    historico = HistoricoViagem(
    viagem_id=nova_viagem.id,
    status="Planejada",
    observacao="Viagem criada pelo painel administrativo"
)

    db.session.add(historico)
    db.session.commit()

    return {"mensagem": "Viagem criada com sucesso!"}, 201

@app.route("/api/admin/viagens/<int:id>/historico", methods=["GET"])
@jwt_required()
def api_historico_viagem(id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para consultar históricos de viagens."
        }), 403

    historicos = HistoricoViagem.query.filter_by(
        viagem_id=id
    ).order_by(
        HistoricoViagem.data_evento.desc()
    ).all()

    lista = []

    for item in historicos:
        lista.append({
            "id": item.id,
            "status": item.status,
            "observacao": item.observacao,
            "data_evento": formatar_data_brasilia(item.data_evento)
        })

    return jsonify(lista), 200

@app.route(
    "/api/admin/viagens/<int:id>/status",
    methods=["POST"]
)
@jwt_required()
def api_atualizar_status_viagem(id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para alterar viagens."
        }), 403

    viagem = Viagem.query.get_or_404(id)

    status_atual = str(viagem.status).strip().lower()

    if status_atual == "cancelada":
        return jsonify({
            "erro": "Não é possível alterar o status de uma viagem cancelada."
        }), 409

    if status_atual == "entregue":
        return jsonify({
            "erro": "Não é possível alterar o status de uma viagem já entregue."
        }), 409

    dados = request.get_json() or {}

    novo_status = str(
        dados.get("status", "")
    ).strip()

    status_permitidos = [
        "Em coleta",
        "Carregando",
        "Em trânsito",
        "Parada operacional",
        "Saiu para entrega",
        "Cancelada"
    ]

    if novo_status not in status_permitidos:
        return jsonify({
            "erro": "Status inválido."
        }), 400

    motorista = db.session.get(
        Motorista,
        viagem.motorista_id
    )

    veiculo = db.session.get(
        Veiculo,
        viagem.veiculo_id
    )

    carga = db.session.get(
        Rastreamento,
        viagem.rastreamento_id
    )

    if (
        novo_status in STATUS_VIAGEM_ATIVOS_RECURSOS
        and veiculo
        and veiculo_possui_status_especial(veiculo)
    ):
        return jsonify({
            "erro": (
                "Não é possível iniciar uma operação com veículo "
                "inativo ou em manutenção."
            )
        }), 409

    try:
        viagem.status = novo_status

        # Mantém carga e viagem sincronizadas.
        if carga:
            carga.status = novo_status

            if hasattr(carga, "ultima_atualizacao"):
                carga.ultima_atualizacao = datetime.utcnow()

        # ------------------------------------------------
        # CANCELAMENTO
        # ------------------------------------------------
        if novo_status == "Cancelada":

            recalcular_disponibilidade_motorista(
                motorista,
                excluir_viagem_id=viagem.id,
                excluir_carga_id=(carga.id if carga else None)
            )

            recalcular_status_veiculo(
                veiculo,
                excluir_viagem_id=viagem.id,
                excluir_carga_id=(carga.id if carga else None)
            )

        # ------------------------------------------------
        # VIAGEM OPERACIONAL
        # ------------------------------------------------
        else:

            if motorista:
                motorista.disponibilidade = "Em viagem"

            if veiculo:
                veiculo.status = "Em viagem"

        historico = HistoricoViagem(
            viagem_id=viagem.id,
            status="STATUS",
            observacao=(
                f"Status alterado para {novo_status}."
            )
        )

        db.session.add(historico)

        if carga:
            historico_rastreamento = HistoricoRastreamento(
                rastreamento_id=carga.id,
                status=novo_status,
                local=carga.local_atual,
                observacao=(
                    f"Status da viagem alterado para {novo_status}."
                )
            )

            db.session.add(historico_rastreamento)

        db.session.commit()

        return jsonify({
            "mensagem": "Status atualizado com sucesso!",
            "status": viagem.status,
            "disponibilidade_motorista": (
                motorista.disponibilidade
                if motorista
                else None
            )
        }), 200

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO ATUALIZAR STATUS DA VIAGEM:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível atualizar o status."
        }), 500
    
@app.route(
    "/api/motorista/minhas-viagens/<int:id>/status",
    methods=["POST"]
)
@jwt_required()
def api_atualizar_status_viagem_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagem = Viagem.query.filter_by(
        id=id,
        motorista_id=motorista.id
    ).first()

    if not viagem:
        return jsonify({
            "erro": (
                "Viagem não encontrada ou não pertence "
                "a este motorista."
            )
        }), 404

    status_atual = str(viagem.status).strip().lower()

    if status_atual == "cancelada":
        return jsonify({
            "erro": "Não é possível alterar o status de uma viagem cancelada."
        }), 409

    if status_atual == "entregue":
        return jsonify({
            "erro": "Não é possível alterar o status de uma viagem já entregue."
        }), 409

    dados = request.get_json(silent=True) or {}

    novo_status = str(
        dados.get("status", "")
    ).strip()

    status_permitidos = [
        "Em coleta",
        "Carregando",
        "Em trânsito",
        "Parada operacional",
        "Saiu para entrega",
    ]

    if novo_status not in status_permitidos:
        return jsonify({
            "erro": (
                "Este status não pode ser definido "
                "pelo motorista."
            )
        }), 400

    carga = db.session.get(
        Rastreamento,
        viagem.rastreamento_id
    )

    veiculo = db.session.get(
        Veiculo,
        viagem.veiculo_id
    )

    if veiculo and veiculo_possui_status_especial(veiculo):
        return jsonify({
            "erro": (
                "Não é possível atualizar a operação com veículo "
                "inativo ou em manutenção."
            )
        }), 409

    try:
        viagem.status = novo_status

        # Status operacional = motorista em viagem.
        motorista.disponibilidade = "Em viagem"

        if veiculo:
            veiculo.status = "Em viagem"

        # Sincroniza também a carga.
        if carga:
            carga.status = novo_status

            if hasattr(carga, "ultima_atualizacao"):
                carga.ultima_atualizacao = datetime.utcnow()

        historico = HistoricoViagem(
            viagem_id=viagem.id,
            status="STATUS",
            observacao=(
                f"Status alterado para {novo_status} "
                "pelo motorista."
            )
        )

        db.session.add(historico)

        if carga:
            historico_rastreamento = HistoricoRastreamento(
                rastreamento_id=carga.id,
                status=novo_status,
                local=carga.local_atual,
                observacao=(
                    f"Status da viagem alterado para {novo_status} "
                    "pelo motorista."
                )
            )

            db.session.add(historico_rastreamento)

        db.session.commit()

        return jsonify({
            "mensagem": "Status atualizado com sucesso!",
            "status": viagem.status,
            "disponibilidade_motorista": (
                motorista.disponibilidade
            )
        }), 200

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO ATUALIZAR STATUS PELO MOTORISTA:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível atualizar o status."
        }), 500
        
@app.route("/api/admin/viagens/<int:id>", methods=["GET"])
@jwt_required()
def api_detalhe_viagem(id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para consultar viagens."
        }), 403

    viagem = Viagem.query.get_or_404(id)

    return {
        "id": viagem.id,
        "codigo_carga": viagem.carga.codigo if viagem.carga else "",
        "cliente": viagem.carga.cliente if viagem.carga else "",
        "motorista": viagem.motorista.nome if viagem.motorista else "",
        "veiculo": viagem.veiculo.placa if viagem.veiculo else "",
        "origem": viagem.origem,
        "destino": viagem.destino,
        "status": viagem.status,
        "data_criacao": formatar_data_brasilia(
    viagem.data_criacao
),
        "data_criacao_iso": viagem.data_criacao.isoformat() if viagem.data_criacao else None
    }
    
@app.route(
    "/api/admin/viagens/<int:id>/ocorrencias",
    methods=["GET"]
)
@jwt_required()
def api_ocorrencias_viagem(id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para consultar ocorrências."
        }), 403

    ocorrencias = OcorrenciaViagem.query.filter_by(
        viagem_id=id
    ).order_by(
        OcorrenciaViagem.data_criacao.desc()
    ).all()

    lista = []

    for item in ocorrencias:
        lista.append({
            "id": item.id,
            "descricao": item.descricao,
            "data": formatar_data_brasilia(item.data_criacao),
            "data_iso": item.data_criacao.isoformat() if item.data_criacao else None
        })

    return lista

@app.route(
    "/api/motorista/minhas-viagens/<int:id>/ocorrencias",
    methods=["GET"]
)
@jwt_required()
def api_ocorrencias_viagem_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagem = Viagem.query.filter_by(
        id=id,
        motorista_id=motorista.id
    ).first()

    if not viagem:
        return jsonify({
            "erro": (
                "Viagem não encontrada ou não pertence "
                "a este motorista."
            )
        }), 404

    ocorrencias = OcorrenciaViagem.query.filter_by(
        viagem_id=viagem.id
    ).order_by(
        OcorrenciaViagem.data_criacao.desc()
    ).all()

    lista = []

    for item in ocorrencias:
        lista.append({
            "id": item.id,
            "descricao": item.descricao,
            "data": (
                item.data_criacao.strftime(
                    "%d/%m/%Y %H:%M"
                )
                if item.data_criacao
                else ""
            ),
            "data_iso": (
                item.data_criacao.isoformat()
                if item.data_criacao
                else None
            )
        })

    return jsonify(lista), 200

@app.route(
    "/api/admin/viagens/<int:id>/ocorrencias",
    methods=["POST"]
)
@jwt_required()
def api_criar_ocorrencia(id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para registrar ocorrências."
        }), 403

    dados = request.get_json(silent=True) or {}

    ocorrencia = OcorrenciaViagem(
        viagem_id=id,
        descricao=str(dados.get("descricao", "")).strip()
    )

    db.session.add(ocorrencia)

    historico = HistoricoViagem(
        viagem_id=id,
        status="Ocorrência",
        observacao=str(dados.get("descricao", "")).strip()
    )

    db.session.add(historico)

    db.session.commit()

    return {
        "mensagem": "Ocorrência registrada!"
    }
    
@app.route(
    "/api/admin/viagens/<int:id>/comprovante",
    methods=["GET"]
)
@jwt_required()
def api_consultar_comprovante(id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para consultar comprovantes."
        }), 403


    comprovante = ComprovanteEntrega.query.filter_by(
        viagem_id=id
    ).first()

    if not comprovante:
        return {}

    return {
        "recebedor": comprovante.recebedor,
        "observacao": comprovante.observacao,
        "data_entrega":
            comprovante.data_entrega.strftime(
                "%d/%m/%Y %H:%M"
            )
    } 

@app.route(
    "/api/motorista/minhas-viagens/<int:id>/comprovante",
    methods=["GET"]
)
@jwt_required()
def api_consultar_comprovante_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagem = Viagem.query.filter_by(
        id=id,
        motorista_id=motorista.id
    ).first()

    if not viagem:
        return jsonify({
            "erro": (
                "Viagem não encontrada ou não pertence "
                "a este motorista."
            )
        }), 404

    comprovante = ComprovanteEntrega.query.filter_by(
        viagem_id=viagem.id
    ).first()

    if not comprovante:
        return jsonify({}), 200

    return jsonify({
        "id": comprovante.id,
        "viagem_id": comprovante.viagem_id,
        "recebedor": comprovante.recebedor,
        "observacao": comprovante.observacao or "",
        "data_entrega": (
            comprovante.data_entrega.strftime(
                "%d/%m/%Y %H:%M"
            )
            if comprovante.data_entrega
            else ""
        )
    }), 200
    
@app.route(
    "/api/admin/viagens/<int:id>/comprovante/arquivo",
    methods=["POST"]
)
@jwt_required()
def api_upload_arquivo_comprovante(id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para anexar comprovantes."
        }), 403

    viagem = db.session.get(Viagem, id)

    if not viagem:
        return jsonify({"erro": "Viagem não encontrada."}), 404

    carga = db.session.get(
        Rastreamento,
        viagem.rastreamento_id
    )

    if (
        str(viagem.status).strip().lower() == "cancelada"
        or (
            carga
            and str(carga.status).strip().lower() == "cancelada"
        )
    ):
        return jsonify({
            "erro": "Não é possível adicionar comprovante a uma viagem cancelada."
        }), 409

    arquivo = request.files.get("arquivo")

    if not arquivo:
        return {"erro": "Nenhum arquivo enviado."}, 400

    nome_seguro = secure_filename(arquivo.filename)

    nome_final = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{nome_seguro}"

    caminho = os.path.join(
        app.config["UPLOAD_FOLDER"],
        nome_final
    )

    arquivo.save(caminho)

    registro = ArquivoComprovanteViagem(
        viagem_id=id,
        nome_arquivo=nome_final
    )

    historico = HistoricoViagem(
        viagem_id=id,
        status="Comprovante anexado",
        observacao=f"Arquivo anexado: {nome_seguro}"
    )

    db.session.add(registro)
    db.session.add(historico)
    db.session.commit()

    return {
        "mensagem": "Arquivo do comprovante enviado com sucesso!"
    }, 201 
    
@app.route(
    "/api/motorista/minhas-viagens/<int:id>/comprovante/arquivo",
    methods=["POST"]
)
@jwt_required()
def api_upload_arquivo_comprovante_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagem = Viagem.query.filter_by(
        id=id,
        motorista_id=motorista.id
    ).first()

    if not viagem:
        return jsonify({
            "erro": (
                "Viagem não encontrada ou não pertence "
                "a este motorista."
            )
        }), 404

    carga = db.session.get(
        Rastreamento,
        viagem.rastreamento_id
    )

    if (
        str(viagem.status).strip().lower() == "cancelada"
        or (
            carga
            and str(carga.status).strip().lower() == "cancelada"
        )
    ):
        return jsonify({
            "erro": "Não é possível adicionar comprovante a uma viagem cancelada."
        }), 409

    arquivo = request.files.get("arquivo")

    if not arquivo:
        return jsonify({
            "erro": "Nenhum arquivo enviado."
        }), 400

    nome_seguro = secure_filename(
        arquivo.filename
    )

    if not nome_seguro:
        return jsonify({
            "erro": "Arquivo inválido."
        }), 400

    nome_final = (
        f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_"
        f"{nome_seguro}"
    )

    caminho = os.path.join(
        app.config["UPLOAD_FOLDER"],
        nome_final
    )

    try:
        arquivo.save(caminho)

        registro = ArquivoComprovanteViagem(
            viagem_id=viagem.id,
            nome_arquivo=nome_final
        )

        historico = HistoricoViagem(
            viagem_id=viagem.id,
            status="Comprovante anexado",
            observacao=(
                f"Arquivo anexado pelo motorista: "
                f"{nome_seguro}"
            )
        )

        db.session.add(registro)
        db.session.add(historico)
        db.session.commit()

        return jsonify({
            "mensagem": (
                "Arquivo do comprovante enviado "
                "com sucesso!"
            )
        }), 201

    except Exception as erro:
        db.session.rollback()

        if os.path.exists(caminho):
            try:
                os.remove(caminho)
            except OSError:
                pass

        print(
            "ERRO AO ENVIAR COMPROVANTE PELO MOTORISTA:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível enviar o arquivo."
        }), 500
    
@app.route(
    "/api/admin/viagens/<int:id>/comprovantes/arquivos",
    methods=["GET"]
)
@jwt_required()
def api_listar_arquivos_comprovante(id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para consultar comprovantes."
        }), 403

    arquivos = ArquivoComprovanteViagem.query.filter_by(
        viagem_id=id
    ).order_by(
        ArquivoComprovanteViagem.data_upload.desc()
    ).all()

    lista = []

    for arquivo in arquivos:
        lista.append({
            "id": arquivo.id,
            "nome_arquivo": arquivo.nome_arquivo,
            "data_upload": formatar_data_brasilia(arquivo.data_upload),
            "url": f"http://127.0.0.1:5000/static/uploads/{arquivo.nome_arquivo}"
        })

    return lista   

@app.route(
    "/api/motorista/minhas-viagens/<int:id>/comprovantes/arquivos",
    methods=["GET"]
)
@jwt_required()
def api_listar_arquivos_comprovante_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagem = Viagem.query.filter_by(
        id=id,
        motorista_id=motorista.id
    ).first()

    if not viagem:
        return jsonify({
            "erro": (
                "Viagem não encontrada ou não pertence "
                "a este motorista."
            )
        }), 404

    arquivos = ArquivoComprovanteViagem.query.filter_by(
        viagem_id=viagem.id
    ).order_by(
        ArquivoComprovanteViagem.data_upload.desc()
    ).all()

    lista = []

    for arquivo in arquivos:
        lista.append({
            "id": arquivo.id,
            "nome_arquivo": arquivo.nome_arquivo,
            "data_upload": (
                arquivo.data_upload.strftime(
                    "%d/%m/%Y %H:%M"
                )
                if arquivo.data_upload
                else ""
            ),
            "url": (
                "http://127.0.0.1:5000/"
                f"static/uploads/{arquivo.nome_arquivo}"
            )
        })

    return jsonify(lista), 200 

@app.route("/api/admin/viagens/<int:id>/localizacoes", methods=["GET"])
@jwt_required()
def api_listar_localizacoes_viagem(id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para consultar localizações."
        }), 403

    localizacoes = LocalizacaoViagem.query.filter_by(
        viagem_id=id
    ).order_by(
        LocalizacaoViagem.data_registro.desc()
    ).all()

    lista = []

    for item in localizacoes:
            lista.append({
            "id": item.id,
            "localizacao": item.localizacao,
            "observacao": item.observacao,
            "data_registro": formatar_data_brasilia(item.data_registro)
        })

    return jsonify(lista), 200

@app.route("/api/admin/viagens/<int:id>/localizacoes", methods=["POST"])
@jwt_required()
def api_criar_localizacao_viagem(id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para registrar localizações."
        }), 403

    dados = request.get_json()

    localizacao = LocalizacaoViagem(
        viagem_id=id,
        localizacao=dados.get("localizacao"),
        observacao=dados.get("observacao")
    )

    db.session.add(localizacao)

    historico = HistoricoViagem(
        viagem_id=id,
        status="Localização atualizada",
        observacao=dados.get("localizacao")
    )

    db.session.add(historico)
    db.session.commit()

    return {
        "mensagem": "Localização registrada com sucesso!"
    }, 201  
    
@app.route(
    "/api/motorista/minhas-viagens/<int:id>/localizacoes",
    methods=["GET"]
)
@jwt_required()
def api_listar_localizacoes_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagem = Viagem.query.filter_by(
        id=id,
        motorista_id=motorista.id
    ).first()

    if not viagem:
        return jsonify({
            "erro": (
                "Viagem não encontrada ou não pertence "
                "a este motorista."
            )
        }), 404

    localizacoes = LocalizacaoViagem.query.filter_by(
        viagem_id=viagem.id
    ).order_by(
        LocalizacaoViagem.data_registro.desc()
    ).all()

    lista = []

    for item in localizacoes:
        lista.append({
            "id": item.id,
            "localizacao": item.localizacao,
            "observacao": item.observacao,
            "data_registro": formatar_data_brasilia(
    item.data_registro
)
        })

    return jsonify(lista), 200

@app.route(
    "/api/motorista/minhas-viagens/<int:id>/localizacoes",
    methods=["POST"]
)
@jwt_required()
def api_criar_localizacao_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagem = Viagem.query.filter_by(
        id=id,
        motorista_id=motorista.id
    ).first()

    if not viagem:
        return jsonify({
            "erro": (
                "Viagem não encontrada ou não pertence "
                "a este motorista."
            )
        }), 404

    dados = request.get_json(silent=True) or {}

    localizacao_texto = str(
        dados.get("localizacao", "")
    ).strip()

    observacao = str(
        dados.get("observacao", "")
    ).strip()

    if not localizacao_texto:
        return jsonify({
            "erro": "Informe a localização."
        }), 400

    try:
        localizacao = LocalizacaoViagem(
            viagem_id=viagem.id,
            localizacao=localizacao_texto,
            observacao=observacao
        )

        db.session.add(localizacao)

        historico = HistoricoViagem(
            viagem_id=viagem.id,
            status="Localização atualizada",
            observacao=localizacao_texto
        )

        db.session.add(historico)

        db.session.commit()

        return jsonify({
            "mensagem": "Localização registrada com sucesso!"
        }), 201

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO REGISTRAR LOCALIZAÇÃO DO MOTORISTA:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível registrar a localização."
        }), 500
    
@app.route(
    "/api/motorista/minhas-viagens/<int:id>",
    methods=["GET"]
)
@jwt_required()
def api_detalhe_viagem_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagem = Viagem.query.filter_by(
        id=id,
        motorista_id=motorista.id
    ).first()

    if not viagem:
        return jsonify({
            "erro": (
                "Viagem não encontrada ou não pertence "
                "a este motorista."
            )
        }), 404

    return jsonify({
        "id": viagem.id,
        "codigo_carga": (
            viagem.carga.codigo
            if viagem.carga
            else ""
        ),
        "cliente": (
            viagem.carga.cliente
            if viagem.carga
            else ""
        ),
        "motorista": (
            viagem.motorista.nome
            if viagem.motorista
            else ""
        ),
        "veiculo": (
            viagem.veiculo.placa
            if viagem.veiculo
            else ""
        ),
        "origem": viagem.origem,
        "destino": viagem.destino,
        "status": viagem.status,
        "data_criacao": (
            viagem.data_criacao.strftime(
                "%d/%m/%Y %H:%M"
            )
            if viagem.data_criacao
            else ""
        ),
        "data_criacao_iso": (
            viagem.data_criacao.isoformat()
            if viagem.data_criacao
            else None
        )
    }), 200
    
@app.route(
    "/api/motorista/minhas-viagens/<int:id>/historico",
    methods=["GET"]
)
@jwt_required()
def api_historico_viagem_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagem = Viagem.query.filter_by(
        id=id,
        motorista_id=motorista.id
    ).first()

    if not viagem:
        return jsonify({
            "erro": "Viagem não encontrada ou não pertence a este motorista."
        }), 404

    historicos = HistoricoViagem.query.filter_by(
        viagem_id=viagem.id
    ).order_by(
        HistoricoViagem.data_evento.desc()
    ).all()

    lista = []

    for item in historicos:
     lista.append({
        "id": item.id,
        "status": item.status,
        "observacao": item.observacao,
        "data_evento": formatar_data_brasilia(
            item.data_evento
        )
    })
    return jsonify(lista), 200

@app.route(
    "/api/motorista/minhas-viagens/<int:id>/ocorrencias",
    methods=["POST"]
)
@jwt_required()
def api_criar_ocorrencia_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagem = Viagem.query.filter_by(
        id=id,
        motorista_id=motorista.id
    ).first()

    if not viagem:
        return jsonify({
            "erro": (
                "Viagem não encontrada ou não pertence "
                "a este motorista."
            )
        }), 404

    dados = request.get_json(silent=True) or {}

    descricao = str(
        dados.get("descricao", "")
    ).strip()

    if not descricao:
        return jsonify({
            "erro": "Informe a descrição da ocorrência."
        }), 400

    try:
        ocorrencia = OcorrenciaViagem(
            viagem_id=viagem.id,
            descricao=descricao
        )

        db.session.add(ocorrencia)

        historico = HistoricoViagem(
            viagem_id=viagem.id,
            status="Ocorrência",
            observacao=descricao
        )

        db.session.add(historico)

        db.session.commit()

        return jsonify({
            "mensagem": "Ocorrência registrada!"
        }), 201

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO REGISTRAR OCORRÊNCIA DO MOTORISTA:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível registrar a ocorrência."
        }), 500


@app.route(
    "/api/motorista/minhas-viagens",
    methods=["GET"]
)
@jwt_required()
def api_motorista_minhas_viagens():
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagens = (
        Viagem.query
        .filter_by(
            motorista_id=motorista.id
        )
        .order_by(
            Viagem.data_criacao.desc()
        )
        .all()
    )

    lista = []

    for viagem in viagens:
        lista.append({
            "id": viagem.id,
            "codigo": viagem.codigo or "",
            "origem": viagem.origem,
            "destino": viagem.destino,
            "status": viagem.status,
            "data_saida": (
                viagem.data_saida.strftime(
                    "%d/%m/%Y %H:%M"
                )
                if viagem.data_saida
                else ""
            ),
            "previsao_entrega": (
                viagem.previsao_entrega.strftime(
                    "%d/%m/%Y %H:%M"
                )
                if viagem.previsao_entrega
                else ""
            ),
            "carga_codigo": (
                viagem.carga.codigo
                if viagem.carga
                else ""
            ),
            "veiculo": (
                viagem.veiculo.placa
                if viagem.veiculo
                else ""
            ),
        })

    return jsonify(lista), 200
    
@app.route(
    "/api/admin/cargas/<int:id>/criar-viagem",
    methods=["POST"]
)
@jwt_required()
def criar_viagem_para_carga(id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para criar viagens para cargas."
        }), 403

    carga = Rastreamento.query.get(id)

    if not carga:
        return {
            "mensagem": "Carga não encontrada."
        }, 404

    viagem_existente = Viagem.query.filter_by(
        rastreamento_id=carga.id
    ).first()

    if viagem_existente:
        return {
            "mensagem": "Esta carga já possui uma viagem.",
            "viagem_id": viagem_existente.id
        }, 200

    if not carga.motorista_id:
        return {
            "mensagem": "Atribua um motorista antes de criar a viagem."
        }, 400

    if not carga.veiculo_id:
        return {
            "mensagem": "Atribua um veículo antes de criar a viagem."
        }, 400

    if not carga.local_atual:
        return {
            "mensagem": "A carga não possui uma origem definida."
        }, 400

    if not carga.destino:
        return {
            "mensagem": "A carga não possui um destino definido."
        }, 400

    nova_viagem = Viagem(
        rastreamento_id=carga.id,
        motorista_id=carga.motorista_id,
        veiculo_id=carga.veiculo_id,
        origem=carga.local_atual,
        destino=carga.destino,
        status="Planejada"
    )

    db.session.add(nova_viagem)

    db.session.flush()

    registrar_historico(
        nova_viagem.id,
        "PLANEJAMENTO",
        "Viagem criada para a carga pelo painel administrativo."
    )

    historico_rastreamento = HistoricoRastreamento(
        rastreamento_id=carga.id,
        status=carga.status,
        local=carga.local_atual,
        observacao="Viagem planejada para a carga."
    )

    db.session.add(historico_rastreamento)
    db.session.commit()

    return {
        "mensagem": "Viagem criada com sucesso!",
        "viagem_id": nova_viagem.id
    }, 201
    
@app.route(
    "/api/admin/viagens/<int:viagem_id>/finalizar",
    methods=["POST"]
)

@jwt_required()
def api_finalizar_viagem(viagem_id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para finalizar entregas."
        }), 403

    viagem = db.session.get(
        Viagem,
        viagem_id
    )

    if not viagem:
        return jsonify({
            "erro": "Viagem não encontrada."
        }), 404

    status_atual = str(viagem.status).strip().lower()

    if status_atual == "entregue":
        return jsonify({
            "erro": "Esta viagem já foi finalizada."
        }), 409

    if status_atual == "cancelada":
        return jsonify({
            "erro": "Não é possível finalizar uma viagem cancelada."
        }), 409

    dados = request.get_json() or {}

    recebedor = str(
        dados.get("recebedor", "")
    ).strip()

    observacao = str(
        dados.get("observacao", "")
    ).strip()

    if not recebedor:
        return jsonify({
            "erro": "Informe o nome do recebedor."
        }), 400

    carga = db.session.get(
        Rastreamento,
        viagem.rastreamento_id
    )

    motorista = db.session.get(
        Motorista,
        viagem.motorista_id
    )

    veiculo = db.session.get(
        Veiculo,
        viagem.veiculo_id
    )

    if not carga:
        return jsonify({
            "erro": "A carga vinculada à viagem não foi encontrada."
        }), 404

    if str(carga.status).strip().lower() == "cancelada":
        return jsonify({
            "erro": "Não é possível finalizar uma viagem cancelada."
        }), 409

    try:
        comprovante_existente = (
            ComprovanteEntrega.query
            .filter_by(viagem_id=viagem.id)
            .first()
        )

        if comprovante_existente:
            return jsonify({
                "erro": "Esta viagem já possui um comprovante de entrega."
            }), 409

        comprovante = ComprovanteEntrega(
            viagem_id=viagem.id,
            recebedor=recebedor,
            observacao=observacao,
            data_entrega=datetime.utcnow()
        )

        db.session.add(comprovante)

        viagem.status = "Entregue"
        carga.status = "Entregue"

        if hasattr(carga, "ultima_atualizacao"):
            carga.ultima_atualizacao = datetime.utcnow()

        recalcular_disponibilidade_motorista(
            motorista,
            excluir_viagem_id=viagem.id,
            excluir_carga_id=carga.id
        )

        recalcular_status_veiculo(
            veiculo,
            excluir_viagem_id=viagem.id,
            excluir_carga_id=carga.id
        )

        historico_rastreamento = HistoricoRastreamento(
            rastreamento_id=carga.id,
            status="Entregue",
            local=viagem.destino,
            observacao=(
                f"Entrega finalizada. Recebido por {recebedor}."
                + (
                    f" Observação: {observacao}"
                    if observacao
                    else ""
                )
            )
        )

        db.session.add(historico_rastreamento)

        registrar_historico(
            viagem.id,
            "ENTREGA",
            (
                f"Entrega finalizada. Recebedor: {recebedor}."
                + (
                    f" Observação: {observacao}"
                    if observacao
                    else ""
                )
            )
        )
        
        

        db.session.commit()

        return jsonify({
            "mensagem": "Entrega finalizada com sucesso!",
            "comprovante": {
                "id": comprovante.id,
                "viagem_id": viagem.id,
                "recebedor": comprovante.recebedor,
                "observacao": comprovante.observacao or "",
                "data_entrega": formatar_data_brasilia(
                    comprovante.data_entrega
                )
            }
        }), 201

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO FINALIZAR ENTREGA:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível finalizar a entrega."
        }), 500
        
@app.route(
    "/api/motorista/minhas-viagens/<int:viagem_id>/finalizar",
    methods=["POST"]
)
@jwt_required()
def api_finalizar_viagem_motorista(viagem_id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() != "motorista":
        return jsonify({
            "erro": "Acesso permitido somente para motoristas."
        }), 403

    motorista_logado = Motorista.query.filter_by(
        usuario_sistema_id=usuario.id
    ).first()

    if not motorista_logado:
        return jsonify({
            "erro": "O usuário não está vinculado a um motorista."
        }), 404

    if str(motorista_logado.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "Este motorista está inativo."
        }), 403

    viagem = Viagem.query.filter_by(
        id=viagem_id,
        motorista_id=motorista_logado.id
    ).first()

    if not viagem:
        return jsonify({
            "erro": (
                "Viagem não encontrada ou não pertence "
                "a este motorista."
            )
        }), 404

    status_atual = str(viagem.status).strip().lower()

    if status_atual == "cancelada":
        return jsonify({
            "erro": "Não é possível finalizar uma viagem cancelada."
        }), 409

    if status_atual == "entregue":
        return jsonify({
            "erro": "Esta viagem já foi finalizada."
        }), 409

    dados = request.get_json(silent=True) or {}

    recebedor = str(
        dados.get("recebedor", "")
    ).strip()

    observacao = str(
        dados.get("observacao", "")
    ).strip()

    if not recebedor:
        return jsonify({
            "erro": "Informe o nome do recebedor."
        }), 400

    carga = db.session.get(
        Rastreamento,
        viagem.rastreamento_id
    )

    veiculo = db.session.get(
        Veiculo,
        viagem.veiculo_id
    )

    if not carga:
        return jsonify({
            "erro": (
                "A carga vinculada à viagem "
                "não foi encontrada."
            )
        }), 404

    if str(carga.status).strip().lower() == "cancelada":
        return jsonify({
            "erro": "Não é possível finalizar uma viagem cancelada."
        }), 409

    try:
        comprovante_existente = (
            ComprovanteEntrega.query
            .filter_by(
                viagem_id=viagem.id
            )
            .first()
        )

        if comprovante_existente:
            return jsonify({
                "erro": (
                    "Esta viagem já possui um "
                    "comprovante de entrega."
                )
            }), 409

        comprovante = ComprovanteEntrega(
            viagem_id=viagem.id,
            recebedor=recebedor,
            observacao=observacao,
            data_entrega=datetime.utcnow()
        )

        db.session.add(comprovante)

        # Finaliza viagem e carga
        viagem.status = "Entregue"
        carga.status = "Entregue"

        if hasattr(carga, "ultima_atualizacao"):
            carga.ultima_atualizacao = datetime.utcnow()

        recalcular_disponibilidade_motorista(
            motorista_logado,
            excluir_viagem_id=viagem.id,
            excluir_carga_id=carga.id
        )

        recalcular_status_veiculo(
            veiculo,
            excluir_viagem_id=viagem.id,
            excluir_carga_id=carga.id
        )

        historico_rastreamento = HistoricoRastreamento(
            rastreamento_id=carga.id,
            status="Entregue",
            local=viagem.destino,
            observacao=(
                f"Entrega finalizada. Recebido por {recebedor}."
                + (
                    f" Observação: {observacao}"
                    if observacao
                    else ""
                )
            )
        )

        db.session.add(historico_rastreamento)

        registrar_historico(
            viagem.id,
            "ENTREGA",
            (
                f"Entrega finalizada pelo motorista. "
                f"Recebedor: {recebedor}."
                + (
                    f" Observação: {observacao}"
                    if observacao
                    else ""
                )
            )
        )

        # ... históricos ...

        print(
            "ANTES DO COMMIT:",
            motorista_logado.id,
            motorista_logado.nome,
            motorista_logado.status,
            motorista_logado.disponibilidade
        )

        db.session.commit()

        db.session.refresh(motorista_logado)

        print(
            "DEPOIS DO COMMIT:",
            motorista_logado.id,
            motorista_logado.nome,
            motorista_logado.status,
            motorista_logado.disponibilidade
        )

        return jsonify({
            "mensagem": "Entrega finalizada com sucesso!",
            "comprovante": {
                "id": comprovante.id,
                "viagem_id": viagem.id,
                "recebedor": comprovante.recebedor,
                "observacao": comprovante.observacao or "",
                "data_entrega": formatar_data_brasilia(
                    comprovante.data_entrega
                )
            }
        }), 201

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO FINALIZAR ENTREGA PELO MOTORISTA:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível finalizar a entrega."
        }), 500
    
@app.route(
    "/api/admin/cargas/<int:id>/atribuir-motorista",
    methods=["PUT"]
)
@jwt_required()
def atribuir_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para atribuir motoristas."
        }), 403

    dados = request.get_json() or {}

    motorista_id = dados.get("motorista_id")

    if not motorista_id:
        return jsonify({
            "erro": "motorista_id é obrigatório."
        }), 400

    carga = db.session.get(
        Rastreamento,
        id
    )

    if not carga:
        return jsonify({
            "erro": "Carga não encontrada."
        }), 404

    # Viagem vinculada a esta carga, caso exista.
    viagem_atual = Viagem.query.filter_by(
        rastreamento_id=carga.id
    ).first()

    status_carga = str(
        carga.status or ""
    ).strip().lower()

    status_viagem = str(
        viagem_atual.status if viagem_atual else ""
    ).strip().lower()

    if (
        status_carga in ["entregue", "cancelada"]
        or status_viagem in ["entregue", "cancelada"]
    ):
        return jsonify({
            "erro": (
                "Não é possível alterar o motorista de uma "
                "carga com operação finalizada."
            )
        }), 409

    motorista = db.session.get(
        Motorista,
        int(motorista_id)
    )

    if not motorista:
        return jsonify({
            "erro": "Motorista não encontrado."
        }), 404

    if str(motorista.status).strip().lower() == "inativo":
        return jsonify({
            "erro": "O motorista selecionado está inativo."
        }), 400

    status_viagem_ativos = STATUS_VIAGEM_ATIVOS_RECURSOS

    # Verifica se o NOVO motorista
    # já possui outra viagem ativa.
    consulta_viagem = Viagem.query.filter(
        Viagem.motorista_id == motorista.id,
        Viagem.status.in_(status_viagem_ativos)
    )

    if viagem_atual:
        consulta_viagem = consulta_viagem.filter(
            Viagem.id != viagem_atual.id
        )

    viagem_conflitante = consulta_viagem.first()

    if viagem_conflitante:
        return jsonify({
            "erro": (
                "Este motorista já está vinculado "
                "a outra viagem ativa."
            )
        }), 409

    status_carga_ativos = STATUS_CARGA_ATIVOS_RECURSOS

    # Verifica se o NOVO motorista
    # já possui outra carga ativa.
    carga_conflitante = Rastreamento.query.filter(
        Rastreamento.motorista_id == motorista.id,
        Rastreamento.id != carga.id,
        Rastreamento.status.in_(status_carga_ativos)
    ).first()

    if carga_conflitante:
        return jsonify({
            "erro": (
                "Este motorista já está vinculado "
                f"à carga {carga_conflitante.codigo}."
            )
        }), 409

    try:
        # Guarda o motorista anterior
        # ANTES de fazer a troca.
        motorista_anterior_id = carga.motorista_id

        motorista_anterior = None

        if motorista_anterior_id:
            motorista_anterior = db.session.get(
                Motorista,
                motorista_anterior_id
            )

        # Atualiza motorista da carga.
        carga.motorista_id = motorista.id

        # Se a carga já possui viagem,
        # sincroniza o motorista da viagem.
        if viagem_atual:
            viagem_atual.motorista_id = motorista.id

            # Se a viagem está ativa,
            # o novo motorista fica Em viagem.
            operacao_atual_ativa = (
                viagem_atual.status in status_viagem_ativos
                or carga.status in status_carga_ativos
            )

            if operacao_atual_ativa:
                motorista.disponibilidade = "Em viagem"
            else:
                motorista.disponibilidade = "Disponível"

            # Só registra histórico
            # quando realmente houve troca.
            if motorista_anterior_id != motorista.id:
                nome_anterior = (
                    motorista_anterior.nome
                    if motorista_anterior
                    else "Não definido"
                )

                registrar_historico(
                    viagem_atual.id,
                    "MOTORISTA",
                    (
                        f"Motorista alterado de "
                        f"{nome_anterior} para {motorista.nome}."
                    )
                )

        else:
            # Ainda não existe viagem.
            motorista.disponibilidade = (
                "Em viagem"
                if carga.status in status_carga_ativos
                else "Disponível"
            )

        if motorista_anterior_id != motorista.id:
            nome_anterior = (
                motorista_anterior.nome
                if motorista_anterior
                else "Não definido"
            )

            historico_rastreamento = HistoricoRastreamento(
                rastreamento_id=carga.id,
                status=carga.status,
                local=carga.local_atual,
                observacao=(
                    f"Motorista alterado de {nome_anterior} "
                    f"para {motorista.nome}."
                )
            )

            db.session.add(historico_rastreamento)

        # -------------------------------------------------
        # LIBERA O MOTORISTA ANTERIOR
        # -------------------------------------------------

        if (
            motorista_anterior
            and motorista_anterior.id != motorista.id
        ):
            recalcular_disponibilidade_motorista(
                motorista_anterior,
                excluir_viagem_id=(
                    viagem_atual.id
                    if viagem_atual
                    else None
                ),
                excluir_carga_id=carga.id
            )

        db.session.commit()

        return jsonify({
            "mensagem": "Motorista atribuído com sucesso!",
            "carga_id": carga.id,
            "motorista_id": motorista.id,
            "motorista_nome": motorista.nome,
            "disponibilidade": motorista.disponibilidade,
            "viagem_id": (
                viagem_atual.id
                if viagem_atual
                else None
            )
        }), 200

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO ATRIBUIR MOTORISTA:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível atribuir o motorista."
        }), 500
    
@app.route(
    "/api/admin/cargas/<int:id>/atribuir-veiculo",
    methods=["PUT"]
)
@jwt_required()
def atribuir_veiculo(id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para atribuir veículos."
        }), 403

    dados = request.get_json() or {}

    veiculo_id = dados.get("veiculo_id")

    if not veiculo_id:
        return jsonify({
            "erro": "veiculo_id é obrigatório."
        }), 400

    carga = db.session.get(
        Rastreamento,
        id
    )

    if not carga:
        return jsonify({
            "erro": "Carga não encontrada."
        }), 404

    # Busca a viagem vinculada à carga antes de qualquer alteração.
    viagem_atual = Viagem.query.filter_by(
        rastreamento_id=carga.id
    ).first()

    status_carga = str(
        carga.status or ""
    ).strip().lower()

    status_viagem = str(
        viagem_atual.status if viagem_atual else ""
    ).strip().lower()

    if (
        status_carga in ["entregue", "cancelada"]
        or status_viagem in ["entregue", "cancelada"]
    ):
        return jsonify({
            "erro": (
                "Não é possível alterar o veículo de uma "
                "carga com operação finalizada."
            )
        }), 409

    try:
        veiculo_id = int(veiculo_id)
    except (TypeError, ValueError):
        return jsonify({
            "erro": "veiculo_id inválido."
        }), 400

    veiculo = db.session.get(
        Veiculo,
        veiculo_id
    )

    if not veiculo:
        return jsonify({
            "erro": "Veículo não encontrado."
        }), 404

    status_veiculo = str(
        veiculo.status or ""
    ).strip().lower()

    if status_veiculo in [
        "inativo",
        "manutenção",
        "em manutenção"
    ]:
        return jsonify({
            "erro": (
                "O veículo selecionado não está "
                "disponível para operação."
            )
        }), 400

    status_viagem_ativos = STATUS_VIAGEM_ATIVOS_RECURSOS

    # Procura o mesmo veículo em outra viagem ativa.
    consulta_viagem = Viagem.query.filter(
        Viagem.veiculo_id == veiculo.id,
        Viagem.status.in_(status_viagem_ativos)
    )

    if viagem_atual:
        consulta_viagem = consulta_viagem.filter(
            Viagem.id != viagem_atual.id
        )

    viagem_conflitante = consulta_viagem.first()

    if viagem_conflitante:
        return jsonify({
            "erro": (
                "Este veículo já está vinculado "
                "a outra viagem ativa."
            )
        }), 409

    status_carga_ativos = STATUS_CARGA_ATIVOS_RECURSOS

    # Procura o veículo em outra carga ativa,
    # mesmo que essa carga ainda não tenha viagem.
    carga_conflitante = Rastreamento.query.filter(
        Rastreamento.veiculo_id == veiculo.id,
        Rastreamento.id != carga.id,
        Rastreamento.status.in_(status_carga_ativos)
    ).first()

    if carga_conflitante:
        return jsonify({
            "erro": (
                "Este veículo já está vinculado "
                f"à carga {carga_conflitante.codigo}."
            )
        }), 409

    try:
        veiculo_anterior_id = carga.veiculo_id

        veiculo_anterior = None

        if veiculo_anterior_id:
            veiculo_anterior = db.session.get(
                Veiculo,
                veiculo_anterior_id
            )

        carga.veiculo_id = veiculo.id

        # Se já existe viagem, sincroniza o veículo.
        if viagem_atual:
            veiculo_anterior_viagem_id = (
                viagem_atual.veiculo_id
            )

            viagem_atual.veiculo_id = veiculo.id

            operacao_atual_ativa = (
                viagem_atual.status in status_viagem_ativos
                or carga.status in status_carga_ativos
            )

            if operacao_atual_ativa:
                veiculo.status = "Em viagem"
            else:
                recalcular_status_veiculo(
                    veiculo,
                    excluir_viagem_id=viagem_atual.id,
                    excluir_carga_id=carga.id
                )

            # Evita repetir o mesmo evento na Timeline.
            if (
                veiculo_anterior_viagem_id
                != veiculo.id
            ):
                placa_anterior = (
                    veiculo_anterior.placa
                    if veiculo_anterior
                    else "Não definido"
                )

                registrar_historico(
                    viagem_atual.id,
                    "VEÍCULO",
                    (
                        f"Veículo alterado de {placa_anterior} "
                        f"para {veiculo.placa}."
                    )
                )

        else:
            if carga.status in status_carga_ativos:
                veiculo.status = "Em viagem"
            else:
                recalcular_status_veiculo(
                    veiculo,
                    excluir_carga_id=carga.id
                )

        if veiculo_anterior_id != veiculo.id:
            placa_anterior = (
                veiculo_anterior.placa
                if veiculo_anterior
                else "Não definido"
            )

            historico_rastreamento = HistoricoRastreamento(
                rastreamento_id=carga.id,
                status=carga.status,
                local=carga.local_atual,
                observacao=(
                    f"Veículo alterado de {placa_anterior} "
                    f"para {veiculo.placa}."
                )
            )

            db.session.add(historico_rastreamento)

        if (
            veiculo_anterior
            and veiculo_anterior.id != veiculo.id
        ):
            recalcular_status_veiculo(
                veiculo_anterior,
                excluir_viagem_id=(
                    viagem_atual.id
                    if viagem_atual
                    else None
                ),
                excluir_carga_id=carga.id
            )

        db.session.commit()

        return jsonify({
            "mensagem": "Veículo atribuído com sucesso!",
            "carga_id": carga.id,
            "veiculo_id": veiculo.id,
            "veiculo_placa": veiculo.placa,
            "veiculo_alterado": (
                veiculo_anterior_id != veiculo.id
            ),
            "viagem_id": (
                viagem_atual.id
                if viagem_atual
                else None
            )
        }), 200

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO ATRIBUIR VEÍCULO:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível atribuir o veículo."
        }), 500
    
    
@app.route(
    "/api/admin/cargas/<int:id>/status",
    methods=["PUT"]
)
@jwt_required()
def atualizar_status_carga(id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para alterar o status de cargas."
        }), 403

    dados = request.get_json() or {}

    novo_status = dados.get("status")

    if not novo_status:
        return jsonify({
            "erro": "O status é obrigatório."
        }), 400

    status_permitidos = [
        "Pendente",
        "Programada",
        "Em preparação",
        "Carregando"
        ]

    if novo_status not in status_permitidos:
     return jsonify({
            "erro": "Status inválido."
        }), 400

    carga = Rastreamento.query.get(id)

    if not carga:
        return jsonify({
            "erro": "Carga não encontrada."
        }), 404

    viagem = Viagem.query.filter_by(
        rastreamento_id=carga.id
    ).first()

    if viagem:
        status_viagem = str(viagem.status).strip().lower()

        if status_viagem == "cancelada":
            return jsonify({
                "erro": "Não é possível alterar o status de uma viagem cancelada."
            }), 409

        if status_viagem == "entregue":
            return jsonify({
                "erro": "Não é possível alterar o status de uma viagem já entregue."
            }), 409

    status_anterior = carga.status

    carga.status = novo_status
    carga.ultima_atualizacao = datetime.utcnow()

    if viagem:
        viagem.status = novo_status
        
        registrar_historico(
    viagem.id,
    "STATUS",
        f"Status alterado para {novo_status}."
)

    historico_rastreamento = HistoricoRastreamento(
        rastreamento_id=carga.id,
        status=novo_status,
        local=carga.local_atual,
        observacao=(
            f"Status alterado de {status_anterior} para {novo_status}."
        )
    )

    db.session.add(historico_rastreamento)

    db.session.commit()

    return jsonify({
        "mensagem": "Status atualizado com sucesso!",
        "carga_id": carga.id,
        "status": carga.status,
        "viagem_id": viagem.id if viagem else None,
        "viagem_status": viagem.status if viagem else None,
    }), 200

    
@app.route("/api/admin/viagens/despachar", methods=["POST"])
@jwt_required()
def api_despachar_viagem():
    usuario_id = int(get_jwt_identity())

    usuario = UsuarioSistema.query.get(usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para despachar viagens."
        }), 403

    dados = request.get_json() or {}

    rastreamento_id = dados.get("rastreamento_id")
    motorista_id = dados.get("motorista_id")
    veiculo_id = dados.get("veiculo_id")

    origem = str(dados.get("origem", "")).strip()
    destino = str(dados.get("destino", "")).strip()

    data_saida_texto = dados.get("data_saida")
    previsao_entrega_texto = dados.get("previsao_entrega")

    if not rastreamento_id:
        return jsonify({
            "erro": "Selecione uma carga."
        }), 400
        

    if not motorista_id:
        return jsonify({
            "erro": "Selecione um motorista."
        }), 400

    if not veiculo_id:
        return jsonify({
            "erro": "Selecione um veículo."
        }), 400

    if not origem:
        return jsonify({
            "erro": "Informe a origem da viagem."
        }), 400

    if not destino:
        return jsonify({
            "erro": "Informe o destino da viagem."
        }), 400

    carga = db.session.get(
        Rastreamento,
        int(rastreamento_id)
    )

    if not carga:
        return jsonify({
            "erro": "Carga não encontrada."
        }), 404

    motorista = db.session.get(
        Motorista,
        int(motorista_id)
    )

    if not motorista:
        return jsonify({
            "erro": "Motorista não encontrado."
        }), 404

    veiculo = db.session.get(
        Veiculo,
        int(veiculo_id)
    )

    if not veiculo:
        return jsonify({
            "erro": "Veículo não encontrado."
        }), 404
        
    status_viagem_ativos = [
    "Planejada",
    "Em andamento",
    "Em coleta",
    "Carregando",
    "Em trânsito",
    "Parada operacional",
    "Saiu para entrega"
]

    viagem_aberta_carga = Viagem.query.filter(
        Viagem.rastreamento_id == carga.id,
        Viagem.status.in_(status_viagem_ativos)
    ).first()

    if viagem_aberta_carga:
        return jsonify({
            "erro": "Esta carga já possui uma viagem aberta."
        }), 409

    viagem_aberta_motorista = Viagem.query.filter(
        Viagem.motorista_id == motorista.id,
        Viagem.status.in_(status_viagem_ativos)
    ).first()

    if viagem_aberta_motorista:
        return jsonify({
            "erro": "Este motorista já está vinculado a outra viagem."
        }), 409

    viagem_aberta_veiculo = Viagem.query.filter(
        Viagem.veiculo_id == veiculo.id,
        Viagem.status.in_(status_viagem_ativos)
    ).first()

    if viagem_aberta_veiculo:
        return jsonify({
            "erro": "Este veículo já está vinculado a outra viagem."
        }), 409

    if str(motorista.status).lower() == "inativo":
        return jsonify({
            "erro": "Não é possível selecionar um motorista inativo."
        }), 400

    if str(motorista.disponibilidade).strip().lower() == "em viagem":
        return jsonify({
        "erro": "Este motorista já está em viagem."
    }), 409
        
    if str(veiculo.status).lower() in [
        "inativo",
        "manutenção",
        "em manutenção"
    ]:
        return jsonify({
            "erro": "Este veículo não está disponível."
        }), 400

    if str(veiculo.status).lower() == "em viagem":
        return jsonify({
            "erro": "Este veículo já está em viagem."
        }), 409

    try:
        data_saida = (
            datetime.fromisoformat(data_saida_texto)
            if data_saida_texto
            else datetime.utcnow()
        )

        previsao_entrega = (
            datetime.fromisoformat(previsao_entrega_texto)
            if previsao_entrega_texto
            else None
        )

    except ValueError:
        return jsonify({
            "erro": "Uma das datas informadas é inválida."
        }), 400

    if previsao_entrega and previsao_entrega < data_saida:
        return jsonify({
            "erro": "A previsão de entrega não pode ser anterior à saída."
        }), 400

    try:
        viagem = Viagem(
            rastreamento_id=carga.id,
            motorista_id=motorista.id,
            veiculo_id=veiculo.id,
            origem=origem,
            destino=destino,
            status="Em andamento",
            data_saida=data_saida,
            previsao_entrega=previsao_entrega
        )

        db.session.add(viagem)

        db.session.flush()

        registrar_historico(
            viagem.id,
            "DESPACHO",
            (
                f"Viagem despachada com o motorista {motorista.nome} "
                f"e o veículo {veiculo.placa}."
            )
        )

        carga.motorista_id = motorista.id
        carga.veiculo_id = veiculo.id
        carga.status = "Em trânsito"
        carga.local_atual = origem
        carga.destino = destino
        carga.previsao_entrega = previsao_entrega
        carga.ultima_atualizacao = datetime.utcnow()

        motorista.disponibilidade = "Em viagem"
        veiculo.status = "Em viagem"

        historico = HistoricoRastreamento(
            rastreamento_id=carga.id,
            status="Em trânsito",
            local=origem,
            observacao=(
                f"Viagem iniciada com o motorista "
                f"{motorista.nome} e o veículo "
                f"{veiculo.placa}."
            )
        )

        db.session.add(historico)
        db.session.commit()

        return jsonify({
            "mensagem": "Viagem despachada com sucesso!",
            "viagem": {
                "id": viagem.id,
                "carga_id": carga.id,
                "codigo_carga": carga.codigo,
                "motorista_id": motorista.id,
                "motorista": motorista.nome,
                "veiculo_id": veiculo.id,
                "veiculo": veiculo.placa,
                "origem": viagem.origem,
                "destino": viagem.destino,
                "status": viagem.status,
                "data_saida": (
                    viagem.data_saida.isoformat()
                    if viagem.data_saida
                    else None
                ),
                "previsao_entrega": (
                    viagem.previsao_entrega.isoformat()
                    if viagem.previsao_entrega
                    else None
                )
            }
        }), 201

    except Exception as erro:
        db.session.rollback()

        print("ERRO AO DESPACHAR VIAGEM:", erro)

        return jsonify({
            "erro": "Não foi possível despachar a viagem."
        }), 500
        
@app.route("/api/admin/viagens/opcoes", methods=["GET"])
@jwt_required()
def api_opcoes_despacho_viagem():
    usuario_id = int(get_jwt_identity())

    usuario = UsuarioSistema.query.get(usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar viagens."
        }), 403

    status_viagem_ativos = [
        "Planejada",
        "Em andamento",
        "Em coleta",
        "Carregando",
        "Em trânsito",
        "Parada operacional",
        "Saiu para entrega"
    ]

    cargas_ocupadas = db.session.query(
        Viagem.rastreamento_id
    ).filter(
        Viagem.status.in_(status_viagem_ativos)
    )

    motoristas_ocupados = db.session.query(
        Viagem.motorista_id
    ).filter(
        Viagem.status.in_(status_viagem_ativos)
    )

    veiculos_ocupados = db.session.query(
        Viagem.veiculo_id
    ).filter(
        Viagem.status.in_(status_viagem_ativos)
    )

    cargas = Rastreamento.query.filter(
        ~Rastreamento.id.in_(cargas_ocupadas),
        ~Rastreamento.status.in_([
            "Entregue",
            "Cancelada"
        ])
    ).order_by(
        Rastreamento.id.desc()
    ).all()

    motoristas = Motorista.query.filter(
        ~Motorista.id.in_(motoristas_ocupados),
        Motorista.status == "Ativo"
    ).order_by(
        Motorista.nome.asc()
    ).all()

    veiculos = Veiculo.query.filter(
        ~Veiculo.id.in_(veiculos_ocupados),
        ~Veiculo.status.in_([
            "Inativo",
            "Manutenção",
            "Em manutenção",
            "Em viagem"
        ])
    ).order_by(
        Veiculo.placa.asc()
    ).all()

    return jsonify({
        "cargas": [
            {
                "id": carga.id,
                "codigo": carga.codigo,
                "cliente": carga.cliente,
                "local_atual": carga.local_atual,
                "destino": carga.destino
            }
            for carga in cargas
        ],

        "motoristas": [
            {
                "id": motorista.id,
                "nome": motorista.nome,
                "status": motorista.status,
                "disponibilidade": motorista.disponibilidade
            }
            for motorista in motoristas
        ],

        "veiculos": [
            {
                "id": veiculo.id,
                "placa": veiculo.placa,
                "modelo": veiculo.modelo,
                "status": veiculo.status
            }
            for veiculo in veiculos
        ]
    }), 200

    
    
if __name__ == "__main__":
    app.run(debug=True)
