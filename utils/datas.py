from zoneinfo import ZoneInfo


def formatar_data_brasilia(data):
    if not data:
        return ""

    data_utc = data.replace(
        tzinfo=ZoneInfo("UTC")
    )

    data_brasilia = data_utc.astimezone(
        ZoneInfo("America/Sao_Paulo")
    )

    return data_brasilia.strftime(
        "%d/%m/%Y %H:%M"
    )
