# Avaliação

Estado: sem resultados. Ainda não existe uma referência anotada nem uma corrida do pipeline em imagens reais da zona piloto. As tabelas abaixo ficam por preencher com medições, não com estimativas.

## Métricas

Por classe:

- Verdadeiro positivo: elemento do catálogo da mesma classe a menos da tolerância de um elemento da referência. O emparelhamento é um para um, pelos pares mais próximos primeiro.
- Falso positivo: elemento do catálogo sem par na referência.
- Falso negativo: elemento da referência sem par no catálogo.
- Precisão: verdadeiros a dividir por verdadeiros mais falsos positivos.
- Recall: verdadeiros a dividir por verdadeiros mais falsos negativos.
- Erro de posição: distância em metros entre elementos emparelhados (média e mediana), calculada no CRS métrico de `config/municipio.yaml`.

Elementos com estado `rejeitado` não contam como previsões, a menos que se passe `--incluir-rejeitados`.

## Referências

| Referência | Serve para | Limitação |
|---|---|---|
| Rua anotada à mão | Precisão, recall e erro de posição | Só cobre a rua anotada |
| OpenStreetMap | Precisão aproximada | Parcial: não serve para medir recall |
| Map features do Mapillary | Comparação cruzada | Cobertura variável |
| Inventário da Câmara Municipal | Referência completa | Só se for cedido |

Para STOP e cedência no OpenStreetMap, usar uma tolerância de 10 a 20 m, porque os pontos ficam no eixo da via.

## Como medir

1. Anotar à mão uma rua da zona piloto num GeoJSON de pontos. Cada ponto tem a propriedade `classe` (um identificador de `config/classes.yaml`).
2. Correr o pipeline na mesma zona e exportar o catálogo: `GET /export.geojson` (ou, depois de rever, `?estado=validado`).
3. Comparar:

```bash
python -m pipeline.evaluate \
  --municipio config/municipio.yaml \
  --previsto catalogo.geojson \
  --referencia rua_anotada.geojson \
  --tolerancia 15
```

4. Copiar a tabela impressa para a secção seguinte, com a data, a zona, o detetor usado e o número de imagens.

## Resultados

Por medir.

| Data | Zona | Detetor | Referência | Tolerância |
|---|---|---|---|---|
| | | | | |
