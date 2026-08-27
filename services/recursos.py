from models.operacao import Rastreamento, Viagem
from utils.constantes import (
    STATUS_CARGA_ATIVOS_RECURSOS,
    STATUS_VIAGEM_ATIVOS_RECURSOS
)


def motorista_possui_outra_viagem_ativa(
    motorista_id,
    excluir_viagem_id=None
):
    consulta = Viagem.query.filter(
        Viagem.motorista_id == motorista_id,
        Viagem.status.in_(STATUS_VIAGEM_ATIVOS_RECURSOS)
    )

    if excluir_viagem_id is not None:
        consulta = consulta.filter(
            Viagem.id != excluir_viagem_id
        )

    return consulta.first() is not None


def motorista_possui_outra_carga_ativa(
    motorista_id,
    excluir_carga_id=None
):
    consulta = Rastreamento.query.filter(
        Rastreamento.motorista_id == motorista_id,
        Rastreamento.status.in_(STATUS_CARGA_ATIVOS_RECURSOS)
    )

    if excluir_carga_id is not None:
        consulta = consulta.filter(
            Rastreamento.id != excluir_carga_id
        )

    return consulta.first() is not None


def veiculo_possui_outra_viagem_ativa(
    veiculo_id,
    excluir_viagem_id=None
):
    consulta = Viagem.query.filter(
        Viagem.veiculo_id == veiculo_id,
        Viagem.status.in_(STATUS_VIAGEM_ATIVOS_RECURSOS)
    )

    if excluir_viagem_id is not None:
        consulta = consulta.filter(
            Viagem.id != excluir_viagem_id
        )

    return consulta.first() is not None


def veiculo_possui_outra_carga_ativa(
    veiculo_id,
    excluir_carga_id=None
):
    consulta = Rastreamento.query.filter(
        Rastreamento.veiculo_id == veiculo_id,
        Rastreamento.status.in_(STATUS_CARGA_ATIVOS_RECURSOS)
    )

    if excluir_carga_id is not None:
        consulta = consulta.filter(
            Rastreamento.id != excluir_carga_id
        )

    return consulta.first() is not None


def recalcular_disponibilidade_motorista(
    motorista,
    excluir_viagem_id=None,
    excluir_carga_id=None
):
    if not motorista:
        return

    possui_operacao_ativa = (
        motorista_possui_outra_viagem_ativa(
            motorista.id,
            excluir_viagem_id
        )
        or motorista_possui_outra_carga_ativa(
            motorista.id,
            excluir_carga_id
        )
    )

    motorista.disponibilidade = (
        "Em viagem"
        if possui_operacao_ativa
        else "Disponível"
    )


def veiculo_possui_status_especial(veiculo):
    status = str(veiculo.status or "").strip().lower()

    return status in [
        "inativo",
        "manutenção",
        "em manutenção"
    ]


def recalcular_status_veiculo(
    veiculo,
    excluir_viagem_id=None,
    excluir_carga_id=None
):
    if not veiculo or veiculo_possui_status_especial(veiculo):
        return

    possui_operacao_ativa = (
        veiculo_possui_outra_viagem_ativa(
            veiculo.id,
            excluir_viagem_id
        )
        or veiculo_possui_outra_carga_ativa(
            veiculo.id,
            excluir_carga_id
        )
    )

    veiculo.status = (
        "Em viagem"
        if possui_operacao_ativa
        else "Disponível"
    )
