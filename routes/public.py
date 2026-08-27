from flask import Blueprint

from models.operacao import Rastreamento
from utils.datas import formatar_data_brasilia


public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def index():
    return {
        "mensagem": "Backend da Transportadora Ramos ativo.",
        "status": "online"
    }


@public_bp.route("/api/rastreamento/<codigo>", methods=["GET"])
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
