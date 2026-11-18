"""Classificação das unidades da RAPS e compatibilidade com cada perfil de busca."""
import re
import unicodedata

# Tipos de unidade do CNES usados no app
TIPO_CAPS = 70                 # Centro de Atenção Psicossocial
TIPO_PRONTO_ATENDIMENTO = 73   # Pronto atendimento (inclui UPA 24h)
TIPO_POSTO = 1                 # Posto de saúde
TIPO_UBS = 2                   # Centro de saúde / Unidade básica
TIPOS_COLETADOS = (TIPO_CAPS, TIPO_PRONTO_ATENDIMENTO, TIPO_UBS, TIPO_POSTO)

MODALIDADES = {
    "CAPS_I": "CAPS I",
    "CAPS_II": "CAPS II",
    "CAPS_III": "CAPS III (24h)",
    "CAPS_AD": "CAPS Álcool e Drogas",
    "CAPS_AD_III": "CAPS Álcool e Drogas III (24h)",
    "CAPS_AD_IV": "CAPS Álcool e Drogas IV (24h)",
    "CAPS_IJ": "CAPS Infantojuvenil",
    "CAPS_NI": "CAPS (modalidade não identificada)",
    "UPA": "Pronto atendimento / UPA",
    "UBS": "Unidade Básica de Saúde",
}

DESCRICAO_SIMPLES = {
    "CAPS_I": "Atende adultos, crianças e adolescentes com sofrimento psíquico intenso, em municípios menores.",
    "CAPS_II": "Atende adultos com sofrimento psíquico intenso e persistente, durante o dia.",
    "CAPS_III": "Atende adultos em sofrimento psíquico intenso, 24 horas, inclusive acolhimento noturno.",
    "CAPS_AD": "Atende pessoas com problemas pelo uso de álcool e outras drogas.",
    "CAPS_AD_III": "Atende pessoas com problemas pelo uso de álcool e outras drogas, 24 horas.",
    "CAPS_AD_IV": "Atende pessoas com uso de álcool e drogas em grandes cidades, 24 horas.",
    "CAPS_IJ": "Atende crianças e adolescentes em sofrimento psíquico.",
    "CAPS_NI": "Centro de Atenção Psicossocial. Confirme por telefone o público atendido.",
    "UPA": "Atendimento de urgência e emergência, inclusive crises.",
    "UBS": "Porta de entrada do SUS: acolhe, cuida de casos leves e encaminha ao CAPS quando preciso.",
}

# Peso no indicador CAPS/100 mil hab. (Ministério da Saúde):
# CAPS I cobre 50 mil hab. (0,5); CAPS III e AD III, 150 mil (1,5); demais, 100 mil (1).
PESO_COBERTURA = {
    "CAPS_I": 0.5, "CAPS_II": 1.0, "CAPS_III": 1.5, "CAPS_AD": 1.0,
    "CAPS_AD_III": 1.5, "CAPS_AD_IV": 1.5, "CAPS_IJ": 1.0, "CAPS_NI": 1.0,
}

MODALIDADES_24H = {"CAPS_III", "CAPS_AD_III", "CAPS_AD_IV", "UPA"}

PERFIS = {
    "todos": "Qualquer serviço",
    "adulto": "Adulto em sofrimento psíquico",
    "infantojuvenil": "Criança ou adolescente",
    "alcool_drogas": "Álcool e outras drogas",
    "crise": "Crise agora (24 horas)",
}

# Compatibilidade de cada modalidade com cada perfil (0 = não indicado)
COMPATIBILIDADE = {
    "todos": {"CAPS_I": 1, "CAPS_II": 1, "CAPS_III": 1, "CAPS_AD": 1, "CAPS_AD_III": 1,
              "CAPS_AD_IV": 1, "CAPS_IJ": 1, "CAPS_NI": 1, "UBS": 0.5, "UPA": 0.5},
    "adulto": {"CAPS_I": 1, "CAPS_II": 1, "CAPS_III": 1, "CAPS_NI": 0.8, "UBS": 0.5, "UPA": 0.3},
    "infantojuvenil": {"CAPS_IJ": 1, "CAPS_I": 0.6, "CAPS_NI": 0.4, "UBS": 0.5, "UPA": 0.3},
    "alcool_drogas": {"CAPS_AD": 1, "CAPS_AD_III": 1, "CAPS_AD_IV": 1, "CAPS_I": 0.6,
                      "CAPS_NI": 0.4, "UBS": 0.4, "UPA": 0.3},
    # Em crise só entram serviços 24h (checado também por funciona_24h)
    "crise": {"CAPS_III": 1, "CAPS_AD_III": 1, "CAPS_AD_IV": 1, "UPA": 0.9, "CAPS_IJ": 1,
              "CAPS_NI": 0.8},
}


def normalizar(texto):
    """Maiúsculas, sem acentos e com espaços simples."""
    if texto is None:
        return ""
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().upper()


def eh_24h(turno):
    t = normalizar(turno)
    return "24 HORAS" in t or "24H" in t.replace(" ", "") or "CONTINUO" in t


def inferir_modalidade_caps(nome, turno=""):
    """Deduz a modalidade do CAPS pelo nome cadastrado no CNES.

    Os nomes seguem padrões como "CAPS AD III", "CAPS IJ II", "CAPS ADULTO II".
    Quando o nome não diz, usa o turno (24h indica CAPS III) ou CAPS_NI.
    """
    n = " " + re.sub(r"[^A-Z0-9 ]", " ", normalizar(nome)) + " "
    n = re.sub(r"\s+", " ", n)
    vinte_quatro = eh_24h(turno)

    infantil = re.search(r"INFANT|JUVENIL| IJ |CAPSIJ| CAPS I J |CRIANCA|ADOLESC| INF ", n)
    alcool = re.search(r" AD |CAPSAD| AD$|ALCOOL|DROGA", n)

    if infantil and not alcool:
        return "CAPS_IJ"
    if alcool:
        if re.search(r" (IV|4) ", n):
            return "CAPS_AD_IV"
        if re.search(r" (III|3) ", n) or vinte_quatro:
            return "CAPS_AD_III"
        return "CAPS_AD"
    if re.search(r" (III|3) ", n):
        return "CAPS_III"
    if re.search(r" (II|2) ", n):
        return "CAPS_II"
    if re.search(r" CAPS (I|1) ", n) or re.search(r" (I|1) $", n):
        return "CAPS_I"
    if vinte_quatro:
        return "CAPS_III"
    return "CAPS_NI"


def classificar(tipo_unidade, nome, turno=""):
    """Retorna (categoria, modalidade, funciona_24h) ou None se não for da RAPS."""
    try:
        tipo = int(tipo_unidade)
    except (TypeError, ValueError):
        return None
    if tipo == TIPO_CAPS:
        mod = inferir_modalidade_caps(nome, turno)
        return "CAPS", mod, mod in MODALIDADES_24H or eh_24h(turno)
    if tipo == TIPO_PRONTO_ATENDIMENTO:
        return "URGENCIA", "UPA", eh_24h(turno) or "UPA" in normalizar(nome)
    if tipo in (TIPO_UBS, TIPO_POSTO):
        return "ATENCAO_BASICA", "UBS", eh_24h(turno)
    return None


def compatibilidade(perfil, modalidade, funciona_24h):
    tabela = COMPATIBILIDADE.get(perfil, COMPATIBILIDADE["todos"])
    valor = tabela.get(modalidade, 0)
    if perfil == "crise" and not funciona_24h:
        return 0
    return valor
