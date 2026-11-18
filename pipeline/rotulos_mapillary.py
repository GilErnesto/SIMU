OBRIGACAO_PREFIXOS= (
    "keep-",
    "turn-",
    "go-straight",
    "roundabout",
    "pass-on-",
    "dual-path",
    "shared-path",
    "minimum-speed",
    "mandatory-",
)
PROIBICAO_LIMITES= ("weight-limit", "height-limit", "width-limit", "length-limit", "axle-weight")
SINAIS_GENERICOS= (
    "object--traffic-sign--front",
    "object--traffic-sign--direction-front",
    "object--traffic-sign--information-parking",
    "other-sign",
)
SINAIS_COSTAS= ("object--traffic-sign--back", "object--traffic-sign--direction-back")
OBJETOS= {
    "object--street-light": ("iluminacao", "luz"),
    "object--trash-can": ("residuos", "papeleira"),
}


def _regulamentar(nome: str) -> str:
    if nome == "stop":
        return "stop"
    if nome == "yield":
        return "cedencia"
    if nome.startswith("maximum-speed-limit"):
        return "limite_velocidade"
    if nome.startswith("no-") or nome.startswith(PROIBICAO_LIMITES):
        return "proibicao"
    if nome.startswith("one-way"):
        return "informacao"
    if nome.endswith("-only") or nome.startswith(OBRIGACAO_PREFIXOS):
        return "obrigacao"
    return "outro"


def classificar(valor: str, incluir_costas: bool= False) -> tuple[str, str] | None:
    if valor in OBJETOS:
        return OBJETOS[valor]
    if valor in SINAIS_GENERICOS or (incluir_costas and valor in SINAIS_COSTAS):
        return "sinal", "outro"
    if valor.startswith("object--traffic-light"):
        return "sinal", "semaforo"
    partes= valor.split("--")
    if len(partes) < 2:
        return None
    grupo, nome= partes[0], partes[1]
    if grupo == "regulatory":
        return "sinal", _regulamentar(nome)
    if grupo == "warning":
        return "sinal", "perigo"
    if grupo == "information":
        return "sinal", "informacao"
    return None
