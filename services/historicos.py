from extensions import db
from models.historicos import HistoricoViagem


def registrar_historico(
    viagem_id,
    tipo,
    descricao
):
    historico = HistoricoViagem(
        viagem_id=viagem_id,
        status=tipo,
        observacao=descricao
    )

    db.session.add(historico)
