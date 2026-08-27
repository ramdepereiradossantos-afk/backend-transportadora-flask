
from flask import Flask, request, jsonify
from datetime import datetime
from werkzeug.utils import secure_filename
import os
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from flask import send_file
import io
import json
from flask_jwt_extended import (
    create_access_token,
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

from models.cotacoes import Carga, Cotacao
from models.usuarios import UsuarioSistema
from models.clientes import Cliente, ClienteUsuario
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

@app.route("/")
def index():
    return {
        "mensagem": "Backend da Transportadora Ramos ativo.",
        "status": "online"
    }

@app.route("/api/login", methods=["POST"])
def api_login():
    dados = request.get_json(silent=True) or {}

    usuario_digitado = str(
        dados.get("usuario", "")
    ).strip()

    senha_digitada = str(
        dados.get("senha", "")
    ).strip()
    
    print("=" * 50)
    print("USUÁRIO RECEBIDO:", usuario_digitado)
    print("SENHA RECEBIDA:", senha_digitada)

    if not usuario_digitado or not senha_digitada:
        return {
            "erro": "Informe o usuário e a senha."
        }, 400
        
    usuarios = UsuarioSistema.query.all()

    for u in usuarios:
            print(
                u.id,
                 repr(u.usuario),
                repr(u.senha),
                u.ativo,
                repr(u.perfil)
            )

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


@app.route(
    "/api/admin/cotacoes/<int:id>/aprovar",
    methods=["POST"]
)
@jwt_required()
def aprovar_cotacao(id):
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para aprovar cotações."
        }), 403

    cotacao = db.session.get(Cotacao, id)

    if not cotacao:
        return jsonify({
            "erro": "Cotação não encontrada."
        }), 404

    carga_existente = Carga.query.filter_by(
        cotacao_id=cotacao.id
    ).first()

    if carga_existente:
        return jsonify({
            "erro": "Esta cotação já foi aprovada."
        }), 400

    try:
        carga = Carga(
            cotacao_id=cotacao.id,
            cliente=cotacao.cliente,
            whatsapp=cotacao.whatsapp,
            origem=cotacao.origem,
            destino=cotacao.destino,
            tipo_carga=cotacao.tipo_carga,
            observacoes=cotacao.observacoes
        )

        db.session.add(carga)
        db.session.flush()

        rastreamento = Rastreamento(
            codigo="TEMPORARIO",
            cliente=cotacao.cliente,
            status="Pendente",
            local_atual=cotacao.origem,
            destino=cotacao.destino,
            ultima_atualizacao=datetime.utcnow()
        )

        db.session.add(rastreamento)
        db.session.flush()

        rastreamento.codigo = (
            f"CG-{rastreamento.id:05d}"
        )

        db.session.commit()

        return jsonify({
            "mensagem": (
                "Cotação aprovada e carga criada "
                "com sucesso!"
            ),
            "cotacao_id": cotacao.id,
            "carga_id": carga.id,
            "rastreamento_id": rastreamento.id,
            "codigo_carga": rastreamento.codigo
        }), 201

    except Exception as erro:
        db.session.rollback()

        print(
            "ERRO AO APROVAR COTAÇÃO:",
            erro
        )

        return jsonify({
            "erro": "Não foi possível aprovar a cotação."
        }), 500
@app.route("/api/admin/cotacoes", methods=["POST"])
@jwt_required()
def api_criar_cotacao_admin():
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
            "erro": "Você não possui permissão para cadastrar cotações."
        }), 403

    dados = request.get_json(silent=True) or {}

    cliente = str(
        dados.get("cliente", "")
    ).strip()

    whatsapp = str(
        dados.get("whatsapp", "")
    ).strip()

    origem = str(
        dados.get("origem", "")
    ).strip()

    destino = str(
        dados.get("destino", "")
    ).strip()

    tipo_carga = str(
        dados.get("tipo_carga", "")
    ).strip()

    observacoes = str(
        dados.get("observacoes", "")
    ).strip()

    if not cliente:
        return jsonify({
            "erro": "Informe o cliente."
        }), 400

    if not whatsapp:
        return jsonify({
            "erro": "Informe o WhatsApp."
        }), 400

    if not origem:
        return jsonify({
            "erro": "Informe a origem."
        }), 400

    if not destino:
        return jsonify({
            "erro": "Informe o destino."
        }), 400

    if not tipo_carga:
        return jsonify({
            "erro": "Informe o tipo da carga."
        }), 400

    try:
        cotacao = Cotacao(
            cliente=cliente,
            whatsapp=whatsapp,
            origem=origem,
            destino=destino,
            tipo_carga=tipo_carga,
            observacoes=observacoes
        )

        db.session.add(cotacao)
        db.session.commit()

        return jsonify({
            "mensagem": "Cotação cadastrada com sucesso!",
            "cotacao": {
                "id": cotacao.id,
                "cliente": cotacao.cliente,
                "whatsapp": cotacao.whatsapp,
                "origem": cotacao.origem,
                "destino": cotacao.destino,
                "tipo_carga": cotacao.tipo_carga,
                "observacoes": cotacao.observacoes
            }
        }), 201

    except Exception as erro:
        db.session.rollback()

        print("ERRO AO CADASTRAR COTAÇÃO:", erro)

        return jsonify({
            "erro": "Não foi possível cadastrar a cotação."
        }), 500


def registrar_log(
    acao,
    detalhes="",
    modulo=None,
    entidade=None,
    entidade_id=None,
    antes=None,
    depois=None,
    usuario_id=None,
    usuario_nome=None,
    perfil=None
):
    log = LogAcao(
        usuario_id=usuario_id,
        usuario_nome=usuario_nome,
        perfil=perfil,
        modulo=modulo,
        acao=acao,
        entidade=entidade,
        entidade_id=entidade_id,
        detalhes=detalhes,
        antes=json.dumps(
            antes,
            ensure_ascii=False,
            default=str
        ) if antes is not None else None,
        depois=json.dumps(
            depois,
            ensure_ascii=False,
            default=str
        ) if depois is not None else None
    )

    db.session.add(log)
    db.session.commit()

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

@app.route("/api/cotacoes", methods=["POST"])
def api_criar_cotacao_publica():
    dados = request.get_json()

    cliente = dados.get("cliente", "").strip()
    whatsapp = dados.get("whatsapp", "").strip()
    origem = dados.get("origem", "").strip()
    destino = dados.get("destino", "").strip()
    tipo_carga = dados.get("tipoCarga", "").strip()
    observacoes = dados.get("observacoes", "").strip()

    if not all([cliente, whatsapp, origem, destino, tipo_carga]):
        return {"erro": "Preencha todos os campos obrigatórios."}, 400

    nova_cotacao = Cotacao(
        cliente=cliente,
        whatsapp=whatsapp,
        origem=origem,
        destino=destino,
        tipo_carga=tipo_carga,
        observacoes=observacoes
    )

    db.session.add(nova_cotacao)
    db.session.commit()

    return {
        "mensagem": "Orçamento enviado com sucesso!",
        "cotacao_id": nova_cotacao.id
    }, 201
    
@app.route("/api/rastreamento/<codigo>", methods=["GET"])
def api_buscar_rastreamento(codigo):
    codigo = codigo.strip().upper()

    carga = Rastreamento.query.filter_by(codigo=codigo).first()

    if not carga:
        return {"erro": "Código de rastreamento não encontrado."}, 404

    ultima_atualizacao = ""
    if carga.ultima_atualizacao:
        ultima_atualizacao = formatar_data_brasilia(carga.ultima_atualizacao)

    return {
        "id": carga.id,
        "codigo": carga.codigo,
        "cliente": carga.cliente,
        "status": carga.status,
        "local_atual": carga.local_atual,
        "destino": carga.destino,
        "ultima_atualizacao": ultima_atualizacao
    }, 200
    
@app.route("/api/admin/resumo", methods=["GET"])
@jwt_required()
def api_admin_resumo():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar o resumo administrativo."
        }), 403

    total_cargas = Rastreamento.query.count()
    em_coleta = Rastreamento.query.filter_by(status="Em coleta").count()
    em_transito = Rastreamento.query.filter_by(status="Em trânsito").count()
    saiu_entrega = Rastreamento.query.filter_by(status="Saiu para entrega").count()
    entregues = Rastreamento.query.filter_by(status="Entregue").count()
    total_cotacoes = Cotacao.query.count()

    agora = datetime.utcnow()

    atrasadas = Rastreamento.query.filter(
        Rastreamento.previsao_entrega != None,
        Rastreamento.previsao_entrega < agora,
        Rastreamento.status != "Entregue"
    ).count()

    return {
        "total_cargas": total_cargas,
        "em_coleta": em_coleta,
        "em_transito": em_transito,
        "saiu_entrega": saiu_entrega,
        "entregues": entregues,
        "atrasadas": atrasadas,
        "total_cotacoes": total_cotacoes
    }
    
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

@app.route(
    "/api/admin/cotacoes",
    methods=["GET"]
)
@jwt_required()
def api_admin_cotacoes():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para consultar cotações."
        }), 403

    cotacoes = (
        Cotacao.query
        .outerjoin(
            Carga,
            Carga.cotacao_id == Cotacao.id
        )
        .filter(
            Carga.id.is_(None)
        )
        .order_by(
            Cotacao.data_criacao.desc()
        )
        .all()
    )

    lista = []

    for cotacao in cotacoes:
        lista.append({
            "id": cotacao.id,
            "cliente": cotacao.cliente,
            "whatsapp": cotacao.whatsapp,
            "origem": cotacao.origem,
            "destino": cotacao.destino,
            "tipo_carga": cotacao.tipo_carga,
            "observacoes": cotacao.observacoes,
            "status": cotacao.status or "Pendente",
            "data_criacao": (
                cotacao.data_criacao.strftime(
                    "%d/%m/%Y %H:%M"
                )
                if cotacao.data_criacao
                else ""
            )
        })

    return jsonify(lista), 200

@app.route("/api/admin/clientes", methods=["GET"])
@jwt_required()
def api_admin_clientes():
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
            "erro": "Você não possui permissão para acessar clientes."
        }), 403

    clientes = Cliente.query.order_by(
        Cliente.data_criacao.desc()
    ).all()

    lista = []

    for cliente in clientes:
        lista.append({
            "id": cliente.id,
            "razao_social": cliente.razao_social,
            "nome_fantasia": cliente.nome_fantasia,
            "documento": cliente.documento,
            "responsavel": cliente.responsavel,
            "email": cliente.email,
            "telefone": cliente.telefone,
            "cidade": cliente.cidade,
            "estado": cliente.estado,
            "ativo": cliente.ativo
        })

    return jsonify(lista), 200

@app.route("/api/admin/clientes", methods=["POST"])
@jwt_required()
def api_criar_cliente():
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
            "erro": "Você não possui permissão para criar clientes."
        }), 403

    dados = request.get_json()

    novo_cliente = Cliente(
        razao_social=dados.get("razao_social"),
        nome_fantasia=dados.get("nome_fantasia"),
        documento=dados.get("documento"),
        responsavel=dados.get("responsavel"),
        email=dados.get("email"),
        telefone=dados.get("telefone"),
        cidade=dados.get("cidade"),
        estado=dados.get("estado"),
        ativo=True
    )

    db.session.add(novo_cliente)
    db.session.commit()

    return {
        "mensagem": "Cliente criado com sucesso!"
    }, 201
    
@app.route("/api/admin/motoristas", methods=["GET"])
@jwt_required()
def api_admin_motoristas():
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
            "erro": (
                "Você não possui permissão "
                "para acessar motoristas."
            )
        }), 403

    motoristas = Motorista.query.order_by(
        Motorista.data_criacao.desc()
    ).all()

    return jsonify([
        {
            "id": motorista.id,
            "nome": motorista.nome,
            "cpf": motorista.cpf or "",
            "cnh": motorista.cnh or "",
            "categoria_cnh": (
                motorista.categoria_cnh or ""
            ),
            "validade_cnh": (
                motorista.validade_cnh or ""
            ),
            "telefone": motorista.telefone or "",
            "email": motorista.email or "",
            "status": motorista.status or "Ativo",
            "disponibilidade": (
                motorista.disponibilidade
                or "Disponível"
            )
        }
        for motorista in motoristas
    ]), 200

@app.route("/api/admin/motoristas", methods=["POST"])
@jwt_required()
def api_criar_motorista():
    usuario_id = int(get_jwt_identity())

    usuario_autenticado = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_autenticado or not usuario_autenticado.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    perfil_usuario = str(
        usuario_autenticado.perfil
    ).strip().lower()

    if perfil_usuario not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para criar motoristas."
        }), 403

    dados = request.get_json(silent=True) or {}

    nome = str(dados.get("nome", "")).strip()
    usuario = str(dados.get("usuario", "")).strip()
    email = str(dados.get("email", "")).strip()
    senha = str(dados.get("senha", "")).strip()

    if not nome:
        return {"erro": "Informe o nome do motorista."}, 400

    if not usuario:
        return {"erro": "Informe o usuário do motorista."}, 400

    if UsuarioSistema.query.filter_by(usuario=usuario).first():
        return {
            "erro": "Já existe um usuário com este nome de acesso."
        }, 409

    status_inicial = str(
        dados.get("status", "Ativo")
    ).strip()

    if perfil_usuario == "operador":
        status_inicial = "Ativo"

    motorista = Motorista(
        nome=nome,
        cpf=str(dados.get("cpf", "")).strip(),
        cnh=str(dados.get("cnh", "")).strip(),
        categoria_cnh=str(
            dados.get("categoria_cnh", "")
        ).strip(),
        validade_cnh=str(
            dados.get("validade_cnh", "")
        ).strip(),
        telefone=str(dados.get("telefone", "")).strip(),
        email=email,
        usuario=usuario,
        senha=senha,
        status=status_inicial,
        disponibilidade="Disponível",
        observacoes=str(
            dados.get("observacoes", "")
        ).strip()
    )

    usuario_sistema = UsuarioSistema(
        nome=nome,
        usuario=usuario,
        email=email,
        senha=senha,
        perfil="motorista",
        ativo=True
    )

    try:
        db.session.add(motorista)
        db.session.add(usuario_sistema)
        db.session.commit()

        return {
            "mensagem": "Motorista cadastrado com sucesso!"
        }, 201

    except Exception as erro:
        db.session.rollback()

        print("ERRO AO CADASTRAR MOTORISTA:", erro)

        return {
            "erro": "Não foi possível cadastrar o motorista."
        }, 500

@app.route("/api/admin/veiculos", methods=["GET"])
@jwt_required()
def api_admin_veiculos():
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
            "erro": "Você não possui permissão para acessar veículos."
        }), 403

    veiculos = Veiculo.query.order_by(
        Veiculo.data_criacao.desc()
    ).all()

    lista = []

    for veiculo in veiculos:
        lista.append({
            "id": veiculo.id,
            "placa": veiculo.placa,
            "modelo": veiculo.modelo,
            "marca": veiculo.marca,
            "tipo": veiculo.tipo,
            "ano": veiculo.ano,
            "capacidade": veiculo.capacidade,
            "status": veiculo.status
        })

    return jsonify(lista), 200

@app.route("/api/admin/veiculos", methods=["POST"])
@jwt_required()
def api_criar_veiculo():
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    perfil_usuario = str(usuario.perfil).strip().lower()

    if perfil_usuario not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para criar veículos."
        }), 403

    dados = request.get_json(silent=True) or {}

    placa = str(dados.get("placa", "")).strip().upper()

    if not placa:
        return {"erro": "Informe a placa."}, 400

    status = str(dados.get("status", "Disponível")).strip()

    if (
        perfil_usuario == "operador"
        and status.lower() == "inativo"
    ):
        return jsonify({
            "erro": "Você não possui permissão para inativar veículos."
        }), 403

    veiculo = Veiculo(
        placa=placa,
        modelo=str(dados.get("modelo", "")).strip(),
        marca=str(dados.get("marca", "")).strip(),
        tipo=str(dados.get("tipo", "")).strip(),
        ano=str(dados.get("ano", "")).strip(),
        capacidade=str(dados.get("capacidade", "")).strip(),
        status=status
    )

    db.session.add(veiculo)
    db.session.commit()

    return {"mensagem": "Veículo cadastrado com sucesso!"}, 201

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
        usuario=usuario_sistema.usuario
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
        usuario=usuario_sistema.usuario
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
    
@app.route("/api/admin/ranking-motoristas")
@jwt_required()
def api_ranking_motoristas():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar o ranking de motoristas."
        }), 403

    ranking = db.session.execute(
        db.text("""
            SELECT
                m.nome,
                COUNT(v.id) as total_viagens
            FROM motorista m
            LEFT JOIN viagem v
                ON v.motorista_id = m.id
            GROUP BY m.id
            ORDER BY total_viagens DESC
            LIMIT 5
        """)
    )

    lista = []

    for item in ranking:
        lista.append({
            "nome": item.nome,
            "total_viagens": item.total_viagens
        })

    return lista

@app.route("/api/admin/frota/resumo")
@jwt_required()
def api_resumo_frota():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar o resumo da frota."
        }), 403

    disponiveis = Veiculo.query.filter_by(
        status="Disponível"
    ).count()

    em_viagem = Veiculo.query.filter_by(
        status="Em viagem"
    ).count()

    manutencao = Veiculo.query.filter_by(
        status="Manutenção"
    ).count()

    return {
        "disponiveis": disponiveis,
        "em_viagem": em_viagem,
        "manutencao": manutencao
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
        usuario=usuario_sistema.usuario
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
        usuario=usuario_sistema.usuario
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
        usuario=usuario_sistema.usuario
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

@app.route("/api/admin/relatorios/viagens")
@jwt_required()
def api_relatorio_viagens():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar relatórios de viagens."
        }), 403

    viagens = Viagem.query.all()

    lista = []

    for viagem in viagens:
        lista.append({
            "codigo": viagem.carga.codigo if viagem.carga else "",
            "cliente": viagem.carga.cliente if viagem.carga else "",
            "origem": viagem.origem,
            "destino": viagem.destino,
            "status": viagem.status
        })

    return lista 

@app.route("/api/admin/relatorios/viagens/pdf")
@jwt_required()
def api_relatorio_viagens_pdf():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar relatórios de viagens."
        }), 403

    buffer = io.BytesIO()

    pdf = canvas.Canvas(buffer, pagesize=A4)

    pdf.setTitle("Relatório de Viagens")

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(
        50,
        800,
        "TRANSPORTADORA RAMOS"
    )

    pdf.setFont("Helvetica", 12)
    pdf.drawString(
        50,
        780,
        "Relatório de Viagens"
    )

    y = 740

    viagens = Viagem.query.all()

    for viagem in viagens:

        codigo = (
            viagem.carga.codigo
            if viagem.carga
            else "Sem código"
        )

        cliente = (
            viagem.carga.cliente
            if viagem.carga
            else "Sem cliente"
        )

        pdf.drawString(
            50,
            y,
            f"Código: {codigo}"
        )

        pdf.drawString(
            220,
            y,
            f"Cliente: {cliente}"
        )

        y -= 20

        pdf.drawString(
            50,
            y,
            f"Origem: {viagem.origem}"
        )

        y -= 20

        pdf.drawString(
            50,
            y,
            f"Destino: {viagem.destino}"
        )

        y -= 20

        pdf.drawString(
            50,
            y,
            f"Status: {viagem.status}"
        )

        y -= 35

        if y < 80:
            pdf.showPage()
            y = 800

    pdf.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="relatorio_viagens.pdf",
        mimetype="application/pdf"
    )
    
@app.route("/api/admin/financeiro/resumo")
@jwt_required()
def api_resumo_financeiro():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() != "administrador":
        return jsonify({
            "erro": "Você não possui permissão para acessar informações financeiras."
        }), 403

    cargas = Rastreamento.query.all()

    faturamento_total = 0
    total_pago = 0
    total_pendente = 0

    for carga in cargas:

        valor = carga.valor_frete or 0

        faturamento_total += valor

        if carga.status_pagamento == "Pago":
            total_pago += valor
        else:
            total_pendente += valor

    return {
        "faturamento_total": faturamento_total,
        "total_pago": total_pago,
        "total_pendente": total_pendente
    }
    
@app.route("/api/admin/alertas")
@jwt_required()
def api_admin_alertas():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar alertas administrativos."
        }), 403

    alertas = []

    cargas_atrasadas = Rastreamento.query.filter_by(
        status="Atrasada"
    ).count()

    if cargas_atrasadas > 0:
        alertas.append({
            "tipo": "Carga atrasada",
            "mensagem": f"{cargas_atrasadas} carga(s) atrasada(s).",
            "nivel": "perigo"
        })

    veiculos_manutencao = Veiculo.query.filter_by(
        status="Manutenção"
    ).count()

    if veiculos_manutencao > 0:
        alertas.append({
            "tipo": "Veículo em manutenção",
            "mensagem": f"{veiculos_manutencao} veículo(s) em manutenção.",
            "nivel": "alerta"
        })

    viagens_em_transito = Viagem.query.filter_by(
        status="Em trânsito"
    ).count()

    if viagens_em_transito > 0:
        alertas.append({
            "tipo": "Viagens em andamento",
            "mensagem": f"{viagens_em_transito} viagem(ns) em trânsito.",
            "nivel": "info"
        })

    return alertas   

@app.route("/api/admin/indicadores")
@jwt_required()
def api_indicadores():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() != "administrador":
        return jsonify({
            "erro": "Você não possui permissão para acessar indicadores financeiros."
        }), 403

    cargas = Rastreamento.query.all()

    total_cargas = len(cargas)

    entregues = len([
        c for c in cargas
        if c.status == "Entregue"
    ])

    percentual_entregues = 0

    if total_cargas > 0:
        percentual_entregues = round(
            (entregues / total_cargas) * 100,
            1
        )

    faturamento = sum(
        c.valor_frete or 0
        for c in cargas
    )

    ticket_medio = 0

    if total_cargas > 0:
        ticket_medio = round(
            faturamento / total_cargas,
            2
        )

    total_veiculos = Veiculo.query.count()

    veiculos_ativos = Veiculo.query.filter_by(
        status="Em viagem"
    ).count()

    percentual_frota_ativa = 0

    if total_veiculos > 0:
        percentual_frota_ativa = round(
            (veiculos_ativos / total_veiculos) * 100,
            1
        )

    return {
        "ticket_medio": ticket_medio,
        "percentual_entregues": percentual_entregues,
        "percentual_frota_ativa": percentual_frota_ativa
    }
    
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
        usuario=usuario_sistema.usuario
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
        usuario=usuario_sistema.usuario
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
    
@app.route("/api/admin/relatorios/financeiro/pdf")
@jwt_required()
def api_relatorio_financeiro_pdf():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() != "administrador":
        return jsonify({
            "erro": "Você não possui permissão para acessar relatórios financeiros."
        }), 403

    buffer = io.BytesIO()

    pdf = canvas.Canvas(
        buffer,
        pagesize=A4
    )

    pdf.setTitle(
        "Relatório Financeiro"
    )

    pdf.setFont(
        "Helvetica-Bold",
        16
    )

    pdf.drawString(
        50,
        800,
        "TRANSPORTADORA RAMOS"
    )

    pdf.setFont(
        "Helvetica",
        12
    )

    pdf.drawString(
        50,
        780,
        "Relatório Financeiro"
    )

    cargas = Rastreamento.query.all()

    faturamento_total = 0
    total_pago = 0
    total_pendente = 0

    for carga in cargas:

        valor = carga.valor_frete or 0

        faturamento_total += valor

        if carga.status_pagamento == "Pago":
            total_pago += valor
        else:
            total_pendente += valor

    ticket_medio = 0

    if len(cargas) > 0:
        ticket_medio = (
            faturamento_total /
            len(cargas)
        )

    y = 720

    pdf.drawString(
        50,
        y,
        f"Faturamento Total: R$ {faturamento_total:,.2f}"
    )

    y -= 30

    pdf.drawString(
        50,
        y,
        f"Total Pago: R$ {total_pago:,.2f}"
    )

    y -= 30

    pdf.drawString(
        50,
        y,
        f"Total Pendente: R$ {total_pendente:,.2f}"
    )

    y -= 30

    pdf.drawString(
        50,
        y,
        f"Ticket Médio: R$ {ticket_medio:,.2f}"
    )

    pdf.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="relatorio_financeiro.pdf",
        mimetype="application/pdf"
    )  
    
@app.route("/api/admin/busca")
@jwt_required()
def api_busca_global():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para realizar buscas administrativas."
        }), 403

    termo = request.args.get("q", "").strip()

    if not termo:
        return {
            "cargas": [],
            "motoristas": [],
            "veiculos": []
        }

    cargas = Rastreamento.query.filter(
        db.or_(
            Rastreamento.codigo.ilike(f"%{termo}%"),
            Rastreamento.cliente.ilike(f"%{termo}%")
        )
    ).all()

    motoristas = Motorista.query.filter(
        Motorista.nome.ilike(f"%{termo}%")
    ).all()

    veiculos = Veiculo.query.filter(
        db.or_(
            Veiculo.placa.ilike(f"%{termo}%"),
            Veiculo.modelo.ilike(f"%{termo}%")
        )
    ).all()

    return {
        "cargas": [
            {
                "id": c.id,
                "codigo": c.codigo,
                "cliente": c.cliente,
                "status": c.status
            }
            for c in cargas
        ],

        "motoristas": [
            {
                "id": m.id,
                "nome": m.nome
            }
            for m in motoristas
        ],

        "veiculos": [
            {
                "id": v.id,
                "placa": v.placa,
                "modelo": v.modelo
            }
            for v in veiculos
        ]
    } 
    
@app.route("/api/admin/clientes/top-cargas", methods=["GET"])
@jwt_required()
def api_top_clientes_cargas():
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
            "erro": "Você não possui permissão para acessar indicadores de clientes."
        }), 403

    resultados = db.session.query(
        Rastreamento.cliente,
        db.func.count(Rastreamento.id)
    ).group_by(
        Rastreamento.cliente
    ).order_by(
        db.func.count(Rastreamento.id).desc()
    ).limit(5).all()

    lista = []

    for cliente, total in resultados:
        lista.append({
            "cliente": cliente,
            "total": total
        })

    return lista  

@app.route("/api/admin/viagens/evolucao", methods=["GET"])
@jwt_required()
def api_evolucao_viagens():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar indicadores de viagens."
        }), 403

    viagens = Viagem.query.all()

    meses = {}

    nomes_meses = [
        "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
        "Jul", "Ago", "Set", "Out", "Nov", "Dez"
    ]

    for viagem in viagens:
        if viagem.data_criacao:
            mes = nomes_meses[viagem.data_criacao.month - 1]

            if mes not in meses:
                meses[mes] = 0

            meses[mes] += 1

    lista = []

    for mes, total in meses.items():
        lista.append({
            "mes": mes,
            "total": total
        })

    return lista   

@app.route("/api/admin/top-rotas", methods=["GET"])
@jwt_required()
def api_top_rotas():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar indicadores de rotas."
        }), 403

    resultados = db.session.query(
        Viagem.origem,
        Viagem.destino,
        db.func.count(Viagem.id)
    ).group_by(
        Viagem.origem,
        Viagem.destino
    ).order_by(
        db.func.count(Viagem.id).desc()
    ).limit(5).all()

    lista = []

    for origem, destino, total in resultados:
        lista.append({
            "rota": f"{origem} → {destino}",
            "total": total
        })

    return lista  

@app.route(
    "/api/admin/motoristas/<int:motorista_id>/ativar",
    methods=["PUT"]
)
@jwt_required()
def api_ativar_motorista(motorista_id):
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
            "erro": "Somente administradores podem ativar motoristas."
        }), 403

    motorista = db.session.get(
        Motorista,
        motorista_id
    )

    if not motorista:
        return jsonify({
            "erro": "Motorista não encontrado."
        }), 404

    motorista.status = "Ativo"

    db.session.commit()

    return jsonify({
        "mensagem": "Motorista ativado com sucesso!",
        "motorista": {
            "id": motorista.id,
            "nome": motorista.nome,
            "status": motorista.status
        }
    }), 200

@app.route(
    "/api/admin/motoristas/<int:motorista_id>/inativar",
    methods=["PUT"]
)
@jwt_required()
def api_inativar_motorista(motorista_id):
    usuario_id = int(get_jwt_identity())

    usuario = UsuarioSistema.query.get(usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario.perfil).strip().lower() != "administrador":
        return jsonify({
            "erro": "Somente administradores podem inativar motoristas."
        }), 403

    motorista = Motorista.query.get(motorista_id)

    if not motorista:
        return jsonify({
            "erro": "Motorista não encontrado."
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

    status_carga_ativos = [
        "Pendente",
        "Programada",
        "Em preparação",
        "Carregando",
        "Em coleta",
        "Em trânsito",
        "Parada operacional",
        "Saiu para entrega"
    ]

    viagem_ativa = Viagem.query.filter(
        Viagem.motorista_id == motorista.id,
        Viagem.status.in_(status_viagem_ativos)
    ).first()

    carga_ativa = Rastreamento.query.filter(
        Rastreamento.motorista_id == motorista.id,
        Rastreamento.status.in_(status_carga_ativos)
    ).first()

    motorista_em_viagem = (
        str(motorista.disponibilidade).strip().lower()
        == "em viagem"
    )

    if viagem_ativa or carga_ativa or motorista_em_viagem:
        return jsonify({
            "erro": (
                "Não é possível inativar este motorista enquanto "
                "houver viagem ou carga ativa."
            )
        }), 409

    motorista.status = "Inativo"

    db.session.commit()

    return jsonify({
        "mensagem": "Motorista inativado com sucesso!"
    }), 200

@app.route("/api/admin/motoristas/<int:id>", methods=["GET"])
@jwt_required()
def api_detalhe_motorista(id):
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
            "erro": "Você não possui permissão para consultar motoristas."
        }), 403

    motorista = Motorista.query.get_or_404(id)

    return {
        "id": motorista.id,
        "nome": motorista.nome,
        "cpf": motorista.cpf,
        "cnh": motorista.cnh,
        "categoria_cnh": getattr(motorista, "categoria_cnh", ""),
        "telefone": motorista.telefone,
        "email": motorista.email,
        "status": motorista.status,
    }
    
@app.route("/api/admin/motoristas/<int:id>", methods=["PUT"])
@jwt_required()
def api_editar_motorista(id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    perfil_usuario = str(usuario.perfil).strip().lower()

    if perfil_usuario not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para editar motoristas."
        }), 403

    motorista = Motorista.query.get_or_404(id)

    dados = request.get_json(silent=True) or {}

    novo_status = str(
        dados.get("status", motorista.status)
    ).strip()

    if (
        perfil_usuario == "administrador"
        and novo_status.lower() == "inativo"
        and str(motorista.status).strip().lower() != "inativo"
    ):
        status_viagem_ativos = [
            "Planejada",
            "Em andamento",
            "Em coleta",
            "Carregando",
            "Em trânsito",
            "Parada operacional",
            "Saiu para entrega"
        ]

        status_carga_ativos = [
            "Pendente",
            "Programada",
            "Em preparação",
            "Carregando",
            "Em coleta",
            "Em trânsito",
            "Parada operacional",
            "Saiu para entrega"
        ]

        viagem_ativa = Viagem.query.filter(
            Viagem.motorista_id == motorista.id,
            Viagem.status.in_(status_viagem_ativos)
        ).first()

        carga_ativa = Rastreamento.query.filter(
            Rastreamento.motorista_id == motorista.id,
            Rastreamento.status.in_(status_carga_ativos)
        ).first()

        motorista_em_viagem = (
            str(motorista.disponibilidade).strip().lower()
            == "em viagem"
        )

        if viagem_ativa or carga_ativa or motorista_em_viagem:
            return jsonify({
                "erro": (
                    "Não é possível inativar este motorista enquanto "
                    "houver viagem ou carga ativa."
                )
            }), 409

    motorista.nome = dados.get("nome", motorista.nome)
    motorista.cpf = dados.get("cpf", motorista.cpf)
    motorista.cnh = dados.get("cnh", motorista.cnh)
    if hasattr(motorista, "categoria_cnh"):
     motorista.categoria_cnh = dados.get("categoria_cnh", motorista.categoria_cnh)
    motorista.telefone = dados.get(
        "telefone",
        motorista.telefone
    )
    motorista.email = dados.get(
        "email",
        motorista.email
    )
    if perfil_usuario == "administrador":
        motorista.status = novo_status

    db.session.commit()

    return {
        "mensagem": "Motorista atualizado com sucesso!"
    }
    
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
        usuario=usuario_sistema.usuario
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
        usuario=usuario_sistema.usuario
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
        usuario=usuario_sistema.usuario
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


@app.route("/api/admin/veiculos/<int:id>/inativar", methods=["PUT"])
@jwt_required()
def api_inativar_veiculo(id):
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
            "erro": "Somente administradores podem inativar veículos."
        }), 403

    veiculo = Veiculo.query.get_or_404(id)

    veiculo.status = "Inativo"

    db.session.commit()

    return {"mensagem": "Veículo inativado com sucesso!"}

@app.route("/api/admin/clientes/<int:id>/inativar", methods=["PUT"])
@jwt_required()
def api_inativar_cliente(id):
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
            "erro": "Somente administradores podem inativar clientes."
        }), 403

    cliente = Cliente.query.get_or_404(id)

    cliente.ativo = False

    db.session.commit()

    return {"mensagem": "Cliente inativado com sucesso!"}

@app.route("/api/admin/veiculos/<int:id>", methods=["GET"])
@jwt_required()
def api_detalhe_veiculo(id):
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
            "erro": "Você não possui permissão para consultar veículos."
        }), 403

    veiculo = Veiculo.query.get_or_404(id)

    return {
        "id": veiculo.id,
        "placa": veiculo.placa,
        "modelo": veiculo.modelo,
        "marca": veiculo.marca,
        "tipo": veiculo.tipo,
        "ano": veiculo.ano,
        "capacidade": veiculo.capacidade,
        "status": veiculo.status
    }
    
@app.route("/api/admin/veiculos/<int:id>", methods=["PUT"])
@jwt_required()
def api_editar_veiculo(id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    perfil_usuario = str(usuario.perfil).strip().lower()

    if perfil_usuario not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para editar veículos."
        }), 403

    veiculo = Veiculo.query.get_or_404(id)
    dados = request.get_json()

    status_atual = str(veiculo.status or "").strip()
    novo_status = str(
        dados.get("status", veiculo.status) or ""
    ).strip()

    if (
        perfil_usuario == "operador"
        and novo_status.lower() != status_atual.lower()
        and (
            novo_status.lower() == "inativo"
            or status_atual.lower() == "inativo"
        )
    ):
        return jsonify({
            "erro": (
                "Você não possui permissão para ativar "
                "ou inativar veículos."
            )
        }), 403

    veiculo.placa = dados.get("placa", veiculo.placa)
    veiculo.modelo = dados.get("modelo", veiculo.modelo)
    veiculo.marca = dados.get("marca", veiculo.marca)
    veiculo.tipo = dados.get("tipo", veiculo.tipo)
    veiculo.ano = dados.get("ano", veiculo.ano)
    veiculo.capacidade = dados.get("capacidade", veiculo.capacidade)
    veiculo.status = novo_status

    db.session.commit()

    return {"mensagem": "Veículo atualizado com sucesso!"}

@app.route("/api/admin/clientes/<int:id>", methods=["GET"])
@jwt_required()
def api_detalhe_cliente(id):
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
            "erro": "Você não possui permissão para consultar clientes."
        }), 403

    cliente = Cliente.query.get_or_404(id)

    return {
        "id": cliente.id,
        "razao_social": cliente.razao_social,
        "nome_fantasia": cliente.nome_fantasia,
        "documento": cliente.documento,
        "responsavel": cliente.responsavel,
         "email": cliente.email,
        "telefone": cliente.telefone,
        "cidade": cliente.cidade,
        "estado": cliente.estado,
        "ativo": cliente.ativo,
    }
    
@app.route("/api/admin/clientes/<int:id>", methods=["PUT"])
@jwt_required()
def api_editar_cliente(id):
    usuario_id = int(get_jwt_identity())

    usuario = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario or not usuario.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    perfil_usuario = str(usuario.perfil).strip().lower()

    if perfil_usuario not in [
        "administrador",
        "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para editar clientes."
        }), 403

    cliente = Cliente.query.get_or_404(id)
    dados = request.get_json()

    cliente.razao_social = dados.get("razao_social", cliente.razao_social)
    cliente.nome_fantasia = dados.get("nome_fantasia", cliente.nome_fantasia)
    cliente.documento = dados.get("documento", cliente.documento)
    cliente.responsavel = dados.get("responsavel", cliente.responsavel)
    cliente.email = dados.get("email", cliente.email)
    cliente.telefone = dados.get("telefone", cliente.telefone)
    cliente.cidade = dados.get("cidade", cliente.cidade)
    cliente.estado = dados.get("estado", cliente.estado)

    if perfil_usuario == "administrador":
        cliente.ativo = dados.get("ativo", cliente.ativo)

    db.session.commit()

    return {"mensagem": "Cliente atualizado com sucesso!"}

@app.route("/api/admin/relatorios/resumo", methods=["GET"])
@jwt_required()
def api_relatorios_resumo():
    usuario_id = int(get_jwt_identity())
    usuario = db.session.get(UsuarioSistema, usuario_id)

    if not usuario or not usuario.ativo:
        return jsonify({"erro": "Usuário não autorizado."}), 401

    if str(usuario.perfil).strip().lower() not in [
        "administrador", "operador"
    ]:
        return jsonify({
            "erro": "Você não possui permissão para acessar relatórios administrativos."
        }), 403

    total_clientes = Cliente.query.count()
    clientes_ativos = Cliente.query.filter_by(ativo=True).count()
    clientes_inativos = Cliente.query.filter_by(ativo=False).count()

    total_motoristas = Motorista.query.count()
    motoristas_ativos = Motorista.query.filter_by(status="Ativo").count()
    motoristas_inativos = Motorista.query.filter_by(status="Inativo").count()

    total_veiculos = Veiculo.query.count()
    veiculos_disponiveis = Veiculo.query.filter_by(status="Disponível").count()
    veiculos_manutencao = Veiculo.query.filter_by(status="Manutenção").count()
    veiculos_inativos = Veiculo.query.filter_by(status="Inativo").count()

    total_viagens = Viagem.query.count()
    viagens_planejadas = Viagem.query.filter_by(status="Planejada").count()
    viagens_transito = Viagem.query.filter_by(status="Em trânsito").count()
    viagens_entregues = Viagem.query.filter_by(status="Entregue").count()

    return {
        "clientes": {
            "total": total_clientes,
            "ativos": clientes_ativos,
            "inativos": clientes_inativos
        },
        "motoristas": {
            "total": total_motoristas,
            "ativos": motoristas_ativos,
            "inativos": motoristas_inativos
        },
        "veiculos": {
            "total": total_veiculos,
            "disponiveis": veiculos_disponiveis,
            "manutencao": veiculos_manutencao,
            "inativos": veiculos_inativos
        },
        "viagens": {
            "total": total_viagens,
            "planejadas": viagens_planejadas,
            "em_transito": viagens_transito,
            "entregues": viagens_entregues
        }
    }
    
    
@app.route(
    "/api/admin/usuarios/<int:id>/inativar",
    methods=["POST"]
)
@jwt_required()
def api_inativar_usuario(id):
    usuario = db.session.get(
        UsuarioSistema,
        id
    )

    if not usuario:
        return jsonify({
            "erro": "Usuário não encontrado."
        }), 404

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


@app.route(
    "/api/admin/usuarios/<int:id>",
    methods=["GET"]
)
@jwt_required()
def api_buscar_usuario(id):
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
    
@app.route(
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


@app.route(
    "/api/admin/usuarios/<int:id>",
    methods=["PUT"]
)
@jwt_required()
def api_editar_usuario(id):
    usuario = db.session.get(
        UsuarioSistema,
        id
    )

    if not usuario:
        return jsonify({
            "erro": "Usuário não encontrado."
        }), 404

    dados = request.get_json(silent=True) or {}

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
    
    
@app.route("/api/usuarios/<int:id>/alterar-senha", methods=["POST"])
@jwt_required()
def api_alterar_senha(id):
    usuario = UsuarioSistema.query.get_or_404(id)
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
    
@app.route(
    "/api/cliente/minhas-cargas",
    methods=["GET"]
)
@jwt_required()
def api_cliente_minhas_cargas():
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "cliente":
        return jsonify({
            "erro": "Acesso permitido somente para clientes."
        }), 403

    cliente_usuario = ClienteUsuario.query.filter_by(
        email=usuario_sistema.email,
        ativo=True
    ).first()

    if not cliente_usuario:
        return jsonify({
            "erro": "O usuário não está vinculado a um cliente."
        }), 404

    if cliente_usuario.cliente_id:
        cargas = (
            Rastreamento.query
            .filter_by(
                cliente_id=cliente_usuario.cliente_id
            )
            .order_by(
                Rastreamento.ultima_atualizacao.desc()
            )
            .all()
        )
    else:
        cargas = (
            Rastreamento.query
            .filter_by(
                cliente=cliente_usuario.empresa
            )
            .order_by(
                Rastreamento.ultima_atualizacao.desc()
            )
            .all()
        )

    lista = []

    for carga in cargas:
        lista.append({
            "id": carga.id,
            "codigo": carga.codigo,
            "cliente": carga.cliente,
            "status": carga.status,
            "origem": getattr(
                carga,
                "origem",
                carga.local_atual or ""
            ),
            "local_atual": carga.local_atual or "",
            "destino": carga.destino or "",
            "previsao_entrega": (
                carga.previsao_entrega.strftime(
                    "%d/%m/%Y %H:%M"
                )
                if getattr(carga, "previsao_entrega", None)
                else ""
            ),
            "ultima_atualizacao": (
                carga.ultima_atualizacao.strftime(
                    "%d/%m/%Y %H:%M"
                )
                if carga.ultima_atualizacao
                else ""
            )
        })

    return jsonify(lista), 200
    
    
@app.route("/api/cliente/minhas-cargas/<int:carga_id>", methods=["GET"])
@jwt_required()
def api_detalhe_carga_cliente_logado(carga_id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = UsuarioSistema.query.get_or_404(usuario_id)

    if usuario_sistema.perfil.lower() != "cliente":
        return {
            "erro": "Acesso permitido somente para clientes."
        }, 403

    cliente_usuario = ClienteUsuario.query.filter_by(
        email=usuario_sistema.email,
        ativo=True
    ).first()

    if not cliente_usuario:
        return {
            "erro": "O usuário não está vinculado a um cliente."
        }, 404

    consulta = Rastreamento.query.filter_by(id=carga_id)

    if cliente_usuario.cliente_id:
        consulta = consulta.filter_by(
            cliente_id=cliente_usuario.cliente_id
        )
    else:
        consulta = consulta.filter_by(
            cliente=cliente_usuario.empresa
        )

    carga = consulta.first()

    if not carga:
        return {
            "erro": "Carga não encontrada ou não pertence a este cliente."
        }, 404
        
        
    historico = HistoricoRastreamento.query.filter_by(
        rastreamento_id=carga.id
        ).order_by(
            HistoricoRastreamento.data_evento.asc()
        ).all()

    return jsonify({
    "id": carga.id,
    "codigo": carga.codigo,
    "cliente": carga.cliente,
    "status": carga.status,
    "local_atual": carga.local_atual,
    "destino": carga.destino,
    "ultima_atualizacao": formatar_data_brasilia(
        carga.ultima_atualizacao
    ),
    "historico": [
        {
            "id": evento.id,
            "status": evento.status,
            "local": evento.local,
            "observacao": evento.observacao or "",
            "data_evento": formatar_data_brasilia(
                evento.data_evento
            )
        }
        for evento in historico
    ]
 }), 200
    
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
        usuario=usuario_sistema.usuario
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
        usuario=usuario.usuario
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
    "/api/cliente/minhas-cargas/<int:carga_id>/ocorrencias",
    methods=["GET"]
)
@jwt_required()
def api_listar_ocorrencias_cliente(carga_id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = UsuarioSistema.query.get_or_404(usuario_id)

    if usuario_sistema.perfil.lower() != "cliente":
        return {
            "erro": "Acesso permitido somente para clientes."
        }, 403

    cliente_usuario = ClienteUsuario.query.filter_by(
        email=usuario_sistema.email,
        ativo=True
    ).first()

    if not cliente_usuario:
        return {
            "erro": "O usuário não está vinculado a um cliente."
        }, 404

    consulta = Rastreamento.query.filter_by(id=carga_id)

    if cliente_usuario.cliente_id:
        consulta = consulta.filter_by(
            cliente_id=cliente_usuario.cliente_id
        )
    else:
        consulta = consulta.filter_by(
            cliente=cliente_usuario.empresa
        )

    carga = consulta.first()

    if not carga:
        return {
            "erro": "Carga não encontrada ou não pertence a este cliente."
        }, 404

    ocorrencias = OcorrenciaEntrega.query.filter_by(
        rastreamento_id=carga.id
    ).order_by(
        OcorrenciaEntrega.data_ocorrencia.desc()
    ).all()

    return jsonify([
        {
            "id": ocorrencia.id,
            "titulo": ocorrencia.titulo,
            "descricao": ocorrencia.descricao,
            "data_ocorrencia": (
                formatar_data_brasilia(ocorrencia.data_ocorrencia)
                if ocorrencia.data_ocorrencia
                else ""
            )
        }
        for ocorrencia in ocorrencias
    ]), 200
    
@app.route(
    "/api/cliente/minhas-cargas/<int:carga_id>/ocorrencias",
    methods=["POST"]
)
@jwt_required()
def api_criar_ocorrencia_cliente(carga_id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = UsuarioSistema.query.get_or_404(usuario_id)

    if usuario_sistema.perfil.lower() != "cliente":
        return {
            "erro": "Acesso permitido somente para clientes."
        }, 403

    cliente_usuario = ClienteUsuario.query.filter_by(
        email=usuario_sistema.email,
        ativo=True
    ).first()

    if not cliente_usuario:
        return {
            "erro": "O usuário não está vinculado a um cliente."
        }, 404

    consulta = Rastreamento.query.filter_by(id=carga_id)

    if cliente_usuario.cliente_id:
        consulta = consulta.filter_by(
            cliente_id=cliente_usuario.cliente_id
        )
    else:
        consulta = consulta.filter_by(
            cliente=cliente_usuario.empresa
        )

    carga = consulta.first()

    if not carga:
        return {
            "erro": "Carga não encontrada ou não pertence a este cliente."
        }, 404

    dados = request.get_json() or {}

    titulo = dados.get("titulo", "").strip()
    descricao = dados.get("descricao", "").strip()

    if not titulo or not descricao:
        return {
            "erro": "Informe o título e a descrição da ocorrência."
        }, 400

    ocorrencia = OcorrenciaEntrega(
        rastreamento_id=carga.id,
        titulo=titulo,
        descricao=descricao
    )

    db.session.add(ocorrencia)
    db.session.commit()

    return jsonify({
        "mensagem": "Ocorrência registrada com sucesso!",
        "ocorrencia": {
            "id": ocorrencia.id,
            "titulo": ocorrencia.titulo,
            "descricao": ocorrencia.descricao,
            "data_ocorrencia": formatar_data_brasilia(
    ocorrencia.data_ocorrencia
)
        }
    }), 201
    
@app.route(
    "/api/cliente/minhas-cargas/<int:carga_id>/comprovantes",
    methods=["GET"]
)
@jwt_required()
def api_comprovantes_carga_cliente(carga_id):
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema or not usuario_sistema.ativo:
        return jsonify({
            "erro": "Usuário não autorizado."
        }), 401

    if str(usuario_sistema.perfil).strip().lower() != "cliente":
        return {
            "erro": "Acesso permitido somente para clientes."
        }, 403

    cliente_usuario = ClienteUsuario.query.filter_by(
        email=usuario_sistema.email,
        ativo=True
    ).first()

    if not cliente_usuario:
        return {
            "erro": "O usuário não está vinculado a um cliente."
        }, 404

    consulta = Rastreamento.query.filter_by(id=carga_id)

    if cliente_usuario.cliente_id:
        consulta = consulta.filter_by(
            cliente_id=cliente_usuario.cliente_id
        )
    else:
        consulta = consulta.filter_by(
            cliente=cliente_usuario.empresa
        )

    carga = consulta.first()

    if not carga:
        return {
            "erro": "Carga não encontrada ou não pertence a este cliente."
        }, 404

    viagem = Viagem.query.filter_by(
        rastreamento_id=carga.id
    ).first()

    if not viagem:
        return jsonify({
            "comprovantes": [],
            "arquivos": []
        }), 200

    comprovantes = ComprovanteEntrega.query.filter_by(
        viagem_id=viagem.id
    ).order_by(
        ComprovanteEntrega.data_entrega.desc()
    ).all()

    arquivos = ArquivoComprovanteViagem.query.filter_by(
        viagem_id=viagem.id
    ).order_by(
        ArquivoComprovanteViagem.data_upload.desc()
    ).all()

    return jsonify({
        "comprovantes": [
            {
                "id": comprovante.id,
                "viagem_id": comprovante.viagem_id,
                "recebedor": comprovante.recebedor,
                "observacao": comprovante.observacao or "",
                "data_entrega": (
                    formatar_data_brasilia(comprovante.data_entrega)
                    if comprovante.data_entrega
                    else ""
                )
            }
            for comprovante in comprovantes
        ],
        "arquivos": [
            {
                "id": arquivo.id,
                "nome_arquivo": arquivo.nome_arquivo,
                "data_upload": formatar_data_brasilia(
                    arquivo.data_upload
                ),
                "url": (
                    "http://127.0.0.1:5000/"
                    f"static/uploads/{arquivo.nome_arquivo}"
                )
            }
            for arquivo in arquivos
        ]
    }), 200
    
@app.route(
    "/api/cliente/perfil",
    methods=["GET"]
)
@jwt_required()
def api_perfil_cliente():
    usuario_id = int(get_jwt_identity())

    usuario_sistema = db.session.get(
        UsuarioSistema,
        usuario_id
    )

    if not usuario_sistema:
        return jsonify({
            "erro": "Usuário não encontrado."
        }), 404

    if str(usuario_sistema.perfil).strip().lower() != "cliente":
        return jsonify({
            "erro": "Acesso permitido somente para clientes."
        }), 403

    cliente_usuario = ClienteUsuario.query.filter_by(
        email=usuario_sistema.email,
        ativo=True
    ).first()

    if not cliente_usuario:
        return jsonify({
            "erro": "Cliente não vinculado ao usuário."
        }), 404

    cliente = None

    if cliente_usuario.cliente_id:
        cliente = db.session.get(
            Cliente,
            cliente_usuario.cliente_id
        )

    return jsonify({
        "nome": cliente_usuario.nome or usuario_sistema.nome,
        "empresa": (
            cliente.razao_social
            if cliente
            else cliente_usuario.empresa
        ),
        "nome_fantasia": (
            cliente.nome_fantasia
            if cliente
            else ""
        ),
        "responsavel": (
            cliente.responsavel
            if cliente
            else cliente_usuario.nome
        ),
        "email": (
            cliente.email
            if cliente and cliente.email
            else cliente_usuario.email
        ),
        "telefone": (
            cliente.telefone
            if cliente
            else ""
        ),
        "documento": (
            cliente.documento
            if cliente
            else ""
        ),
        "endereco": (
            cliente.endereco
            if cliente
            else ""
        ),
        "cidade": (
            cliente.cidade
            if cliente
            else ""
        ),
        "estado": (
            cliente.estado
            if cliente
            else ""
        )
    }), 200
    
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
