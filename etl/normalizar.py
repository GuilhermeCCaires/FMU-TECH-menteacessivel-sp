"""Converte registros do CNES (API ou CSV) para um formato único."""


def pegar(registro, *chaves):
    """Primeiro valor não vazio entre várias chaves possíveis (ignora maiúsculas)."""
    minusculo = {str(k).lower(): v for k, v in registro.items()}
    for chave in chaves:
        valor = minusculo.get(chave.lower())
        if valor not in (None, "", "null", "NULL"):
            return valor
    return None


def numero(valor):
    if valor in (None, ""):
        return None
    try:
        return float(str(valor).replace(",", "."))
    except ValueError:
        return None


def inteiro(valor):
    try:
        return int(float(str(valor)))
    except (TypeError, ValueError):
        return None


def texto(valor):
    if valor is None:
        return None
    t = " ".join(str(valor).split())
    return t or None


def montar_endereco(logradouro, numero_end, complemento=None):
    partes = [texto(logradouro)]
    if texto(numero_end) and texto(numero_end) not in ("0", "S/N", "SN"):
        partes.append(texto(numero_end))
    elif texto(numero_end):
        partes.append("s/n")
    end = ", ".join(p for p in partes if p)
    if texto(complemento):
        end += f" - {texto(complemento)}"
    return end or None


def registro_api(r, competencia):
    """Registro do endpoint /cnes/estabelecimentos da API de dados abertos."""
    return {
        "cnes": str(pegar(r, "codigo_cnes", "cnes")).zfill(7),
        "nome": texto(pegar(r, "nome_fantasia", "nome_razao_social")),
        "tipo_unidade": inteiro(pegar(r, "codigo_tipo_unidade")),
        "endereco": montar_endereco(pegar(r, "endereco_estabelecimento"),
                                    pegar(r, "numero_estabelecimento")),
        "bairro": texto(pegar(r, "bairro_estabelecimento")),
        "cep": texto(pegar(r, "codigo_cep_estabelecimento")),
        "telefone": texto(pegar(r, "numero_telefone_estabelecimento")),
        "email": texto(pegar(r, "endereco_email_estabelecimento")),
        "uf": inteiro(pegar(r, "codigo_uf")),
        "municipio": inteiro(pegar(r, "codigo_municipio")),
        "lat": numero(pegar(r, "latitude_estabelecimento_decimo_grau", "latitude")),
        "lon": numero(pegar(r, "longitude_estabelecimento_decimo_grau", "longitude")),
        "turno": texto(pegar(r, "descricao_turno_atendimento")),
        "atende_sus": texto(pegar(r, "estabelecimento_faz_atendimento_ambulatorial_sus")),
        "desabilitado": pegar(r, "codigo_motivo_desabilitacao_estabelecimento"),
        "competencia": competencia,
    }


def registro_csv(r, turnos, competencia):
    """Registro do arquivo tbEstabelecimento da base completa do CNES."""
    cod_turno = texto(pegar(r, "CO_TURNO_ATENDIMENTO"))
    return {
        "cnes": str(pegar(r, "CO_CNES")).zfill(7),
        "nome": texto(pegar(r, "NO_FANTASIA", "NO_RAZAO_SOCIAL")),
        "tipo_unidade": inteiro(pegar(r, "TP_UNIDADE", "CO_TIPO_UNIDADE")),
        "endereco": montar_endereco(pegar(r, "NO_LOGRADOURO"), pegar(r, "NU_ENDERECO"),
                                    pegar(r, "NO_COMPLEMENTO")),
        "bairro": texto(pegar(r, "NO_BAIRRO")),
        "cep": texto(pegar(r, "CO_CEP")),
        "telefone": texto(pegar(r, "NU_TELEFONE")),
        "email": texto(pegar(r, "NO_EMAIL")),
        "uf": inteiro(pegar(r, "CO_ESTADO_GESTOR")),
        "municipio": inteiro(pegar(r, "CO_MUNICIPIO_GESTOR")),
        "lat": numero(pegar(r, "NU_LATITUDE")),
        "lon": numero(pegar(r, "NU_LONGITUDE")),
        "turno": turnos.get(cod_turno.lstrip("0") if cod_turno else None, cod_turno),
        "atende_sus": None,
        "desabilitado": pegar(r, "CO_MOTIVO_DESAB"),
        "competencia": competencia,
    }
