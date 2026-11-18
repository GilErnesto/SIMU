from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor

JANELA_LEITURA= 8


def ler_adiante(
    funcao: Callable, itens: Iterable, trabalhadores: int, janela: int= JANELA_LEITURA
) -> Iterator[tuple]:
    fim= object()
    iterador= iter(itens)
    with ThreadPoolExecutor(trabalhadores) as executor:
        pendentes= deque()
        for item in iterador:
            pendentes.append((item, executor.submit(funcao, item)))
            if len(pendentes) >= janela:
                break
        while pendentes:
            item, futuro= pendentes.popleft()
            resultado= futuro.result()
            seguinte= next(iterador, fim)
            if seguinte is not fim:
                pendentes.append((seguinte, executor.submit(funcao, seguinte)))
            yield item, resultado
