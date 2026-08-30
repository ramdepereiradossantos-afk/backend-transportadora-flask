def extensao_arquivo_permitida(nome_arquivo, extensoes_permitidas):
    if not isinstance(nome_arquivo, str) or "." not in nome_arquivo:
        return False

    extensao = nome_arquivo.rsplit(".", 1)[1].lower()

    return bool(extensao) and extensao in extensoes_permitidas
