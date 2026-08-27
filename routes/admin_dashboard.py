from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from extensions import db
from models.cotacoes import Cotacao
from models.operacao import Rastreamento, Viagem
from models.recursos import Motorista, Veiculo
from models.usuarios import UsuarioSistema


admin_dashboard_bp = Blueprint(
    "admin_dashboard",
    __name__
)


@admin_dashboard_bp.route("/api/admin/resumo", methods=["GET"])
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


@admin_dashboard_bp.route("/api/admin/ranking-motoristas")
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


@admin_dashboard_bp.route("/api/admin/frota/resumo")
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


@admin_dashboard_bp.route("/api/admin/financeiro/resumo")
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


@admin_dashboard_bp.route("/api/admin/alertas")
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


@admin_dashboard_bp.route("/api/admin/indicadores")
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


@admin_dashboard_bp.route("/api/admin/busca")
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


@admin_dashboard_bp.route("/api/admin/top-rotas", methods=["GET"])
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
