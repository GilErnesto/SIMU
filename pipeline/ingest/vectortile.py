import base64
import binascii
import struct

from pipeline.errors import ErroPipeline

EXTENT_PADRAO= 4096
MOVER= 1
LINHA= 2
FECHAR= 7


def _varint(dados: bytes, posicao: int) -> tuple[int, int]:
    valor= 0
    deslocamento= 0
    while True:
        if posicao >= len(dados):
            raise ErroPipeline("Geometria do Mapillary truncada")
        byte= dados[posicao]
        posicao+= 1
        valor|= (byte & 0x7F) << deslocamento
        if not byte & 0x80:
            return valor, posicao
        deslocamento+= 7
        if deslocamento > 63:
            raise ErroPipeline("Geometria do Mapillary inválida")


def _campos(dados: bytes):
    posicao= 0
    while posicao < len(dados):
        chave, posicao= _varint(dados, posicao)
        numero, tipo= chave >> 3, chave & 7
        if tipo == 0:
            valor, posicao= _varint(dados, posicao)
        elif tipo == 2:
            tamanho, posicao= _varint(dados, posicao)
            valor= dados[posicao : posicao + tamanho]
            if len(valor) != tamanho:
                raise ErroPipeline("Geometria do Mapillary truncada")
            posicao+= tamanho
        elif tipo == 5:
            valor= struct.unpack("<I", dados[posicao : posicao + 4])[0]
            posicao+= 4
        elif tipo == 1:
            valor= struct.unpack("<Q", dados[posicao : posicao + 8])[0]
            posicao+= 8
        else:
            raise ErroPipeline("Geometria do Mapillary com tipo desconhecido")
        yield numero, valor


def _inteiros(dados: bytes) -> list[int]:
    valores= []
    posicao= 0
    while posicao < len(dados):
        valor, posicao= _varint(dados, posicao)
        valores.append(valor)
    return valores


def _zigzag(valor: int) -> int:
    return (valor >> 1) ^ -(valor & 1)


def _aneis(comandos: list[int]) -> list[list[tuple[int, int]]]:
    aneis= []
    atual= []
    x= y= 0
    i= 0
    while i < len(comandos):
        comando, quantidade= comandos[i] & 7, comandos[i] >> 3
        i+= 1
        if comando == FECHAR:
            if atual:
                aneis.append(atual)
                atual= []
            continue
        for _ in range(quantidade):
            if i + 1 >= len(comandos):
                raise ErroPipeline("Geometria do Mapillary truncada")
            x+= _zigzag(comandos[i])
            y+= _zigzag(comandos[i + 1])
            i+= 2
            if comando == MOVER and atual:
                aneis.append(atual)
                atual= []
            atual.append((x, y))
    if atual:
        aneis.append(atual)
    return aneis


def descodificar(geometria_base64: str) -> list[tuple[list[list[tuple[int, int]]], int]]:
    try:
        dados= base64.b64decode(geometria_base64, validate=True)
    except (binascii.Error, ValueError) as erro:
        raise ErroPipeline("Geometria do Mapillary não é base64 válido") from erro
    resultado= []
    for numero, camada in _campos(dados):
        if numero != 3:
            continue
        extent= EXTENT_PADRAO
        caracteristicas= []
        for n, valor in _campos(camada):
            if n == 5:
                extent= valor
            elif n == 2:
                caracteristicas.append(valor)
        for caracteristica in caracteristicas:
            comandos= []
            for n, valor in _campos(caracteristica):
                if n == 4:
                    comandos= _inteiros(valor)
            resultado.append((_aneis(comandos), extent))
    return resultado


def caixa_normalizada(geometria_base64: str) -> tuple[float, float, float, float] | None:
    pontos= []
    extent= EXTENT_PADRAO
    for aneis, extent in descodificar(geometria_base64):
        pontos.extend(p for anel in aneis for p in anel)
    if not pontos:
        return None
    xs= [p[0] for p in pontos]
    ys= [p[1] for p in pontos]
    return min(xs) / extent, min(ys) / extent, max(xs) / extent, max(ys) / extent
