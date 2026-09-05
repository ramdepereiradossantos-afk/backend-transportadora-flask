from models.clientes import ClienteUsuario
from models.recursos import Motorista


def obter_cliente_usuario(usuario_sistema):
    cliente_usuario = ClienteUsuario.query.filter_by(
        usuario_sistema_id=usuario_sistema.id,
        ativo=True
    ).first()

    if cliente_usuario:
        return cliente_usuario

    return ClienteUsuario.query.filter_by(
        email=usuario_sistema.email,
        ativo=True,
        usuario_sistema_id=None
    ).first()


def cliente_pode_acessar_viagem(usuario_sistema, viagem):
    cliente_usuario = obter_cliente_usuario(usuario_sistema)

    if not cliente_usuario or not viagem or not viagem.carga:
        return False

    if cliente_usuario.cliente_id:
        return viagem.carga.cliente_id == cliente_usuario.cliente_id

    return viagem.carga.cliente == cliente_usuario.empresa


def motorista_pode_acessar_viagem(usuario_sistema, viagem):
    motorista = Motorista.query.filter_by(
        usuario_sistema_id=usuario_sistema.id
    ).first()

    if not motorista:
        return False

    if str(motorista.status).strip().lower() == "inativo":
        return False

    return viagem and viagem.motorista_id == motorista.id
