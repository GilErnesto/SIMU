# Avaliação

Estado: primeiras medições feitas contra uma referência automática do Mapillary. Ainda não há referência anotada à mão. Os números abaixo são medições, não estimativas.

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

## Referência automática

Sem anotação manual, a referência vem das map features do Mapillary (`python -m pipeline.referencia`), que traduz cada tipo do Mapillary para a nossa taxonomia (`pipeline/rotulos_mapillary.py`).

Limitações, a ter em conta ao ler os números:

- É obtida por um modelo do Mapillary, não por pessoas. Um elemento real que o Mapillary não viu conta como falso positivo nosso, por isso a precisão está subestimada.
- Sinais vistos só de costas ficam de fora (`--incluir-costas` conta-os).
- Só se compara onde há imagens: referência e previsão contam apenas a menos de 30 m de uma imagem usada (`--cobertura`).
- Sinais genéricos (`outro`) são absorvidos por um sinal com tipo a menos de 3 m.

## Zonas

| Zona | Ficheiro | Uso | Referência |
|---|---|---|---|
| Rua da Pega | `config/municipio.yaml` | piloto | 160 elementos |
| Rossio | `config/avaliacao/rossio.yaml` | afinar limiares | 621 elementos |
| Av. Lourenço Peixinho | `config/avaliacao/lourenco_peixinho.yaml` | teste, nunca para afinar | 747 elementos |

## Resultados

Detetor: OWLv2 (limiar 0,2) + CLIP (`openai/clip-vit-large-patch14`, limiar de tipo 0,5). Emparelhamento a 15 m, por categoria. Imagens: amostra regular de 300 (Rossio) e 400 (Lourenço Peixinho) do Mapillary, metade panoramas.

Limiares de deteção por categoria escolhidos só no Rossio (0,3 em todas, que dão F de 0,67 em sinal, 0,55 em iluminação e 0,58 em resíduos) e medidos uma única vez na zona de teste:

| Categoria | Precisão | Recall | F | Zona |
|---|---|---|---|---|
| Sinal | 0,68 | 0,66 | 0,67 | Rossio (afinação) |
| Iluminação | 0,61 | 0,50 | 0,55 | Rossio (afinação) |
| Resíduos | 0,60 | 0,57 | 0,58 | Rossio (afinação) |
| Sinal | 0,44 | 0,56 | 0,50 | Lourenço Peixinho (teste) |
| Iluminação | 0,40 | 0,65 | 0,49 | Lourenço Peixinho (teste) |
| Resíduos | 0,32 | 0,48 | 0,39 | Lourenço Peixinho (teste) |

A diferença entre as duas zonas mostra o quanto os números dependem da rua: o Rossio é mais fácil que uma avenida densa.

### Tipo de sinal

O ponto fraco. Entre os sinais emparelhados com um sinal de referência de tipo conhecido, o tipo previsto coincide em **19%** dos casos na zona de teste (28% no Rossio). O CLIP zero-shot escolhe "cedência" para uma parte grande dos sinais (155 de cerca de 480 previstos na zona de teste).

Experiências no Rossio: somar as probabilidades de todos os textos de um tipo (o que o pipeline faz) dá 28% de tipo certo; fazer a média dos logits dá 13%. Mantém-se a soma.

Conclusão: sem dados com o tipo anotado, o CLIP zero-shot não chega para o tipo de sinal. O MTSD resolveria; a alternativa é treinar com as deteções por imagem da API do Mapillary, que trazem o tipo.

### Classificador do tipo de sinal (cabeça sobre o CLIP)

Treinado com as deteções por imagem da API do Mapillary (`training/datasets/tipos_mapillary.py`, `training/tipos.py`): 4559 sinais em 2073 imagens de Aveiro, fora das zonas piloto, de afinação e de teste. Ficaram 3256 recortes com pelo menos 24 px, anonimizados antes de gravar, divididos por imagem (80% treino, 20% validação). O modelo é uma regressão logística sobre as características de imagem do CLIP. As etiquetas vêm de um modelo do Mapillary, por isso têm ruído.

Exatidão do tipo nos 564 recortes de validação (caixas limpas):

| Tipo | Exemplos | CLIP zero-shot (recall) | Cabeça (recall) |
|---|---|---|---|
| Cedência | 47 | 0,96 | 0,98 |
| Informação | 151 | 0,44 | 0,81 |
| Limite de velocidade | 17 | 1,00 | 1,00 |
| Obrigação | 74 | 0,46 | 0,95 |
| Perigo | 43 | 0,02 | 0,93 |
| Proibição | 94 | 0,36 | 0,85 |
| Semáforo | 12 | 0,83 | 1,00 |
| Stop | 19 | 1,00 | 0,95 |
| **Total** | 564 | **0,40** | **0,79** |

Atenção: o mesmo sinal pode aparecer em fotografias vizinhas do treino e da validação, por isso os 79% são optimistas. O número que conta é o de ponta a ponta, medido na zona de teste.

Ponta a ponta (tipo certo entre os sinais emparelhados a 15 m, sem 'outro'), com panoramas recortados na imagem esticada, no Rossio (zona de afinação):

| Limiar do tipo | CLIP zero-shot | Cabeça |
|---|---|---|
| 0,3 | 25% a 28% | 35% a 38% |
| 0,5 | 22% a 25% | 31% a 35% |

O ganho de ponta a ponta é bem menor do que nos recortes limpos. Duas causas prováveis: o emparelhamento por posição troca sinais diferentes no mesmo poste (a métrica penaliza o que o classificador acertou), e as caixas do OWLv2 não são tão limpas como as do treino.

### Detetor YOLO e comparação na zona de teste

YOLO11s treinado a 1024 px com o Open Images V7 (8096 imagens de treino) e o Mapillary Vistas v2.0 (4012 imagens, com cada luminária ligada ao poste que a segura), todas anonimizadas antes de gravar. Quatro classes (sinal genérico, semáforo, candeeiro, contentor); o tipo de sinal e de contentor vem da segunda fase. 31 épocas, em 2h30. Na validação (577 imagens): mAP50 de 0,51 e mAP50-95 de 0,31.

Zona de teste (Av. Lourenço Peixinho, 400 imagens, sem nada afinado nela), emparelhamento a 15 m:

| Detetor | Sinal (P/R) | Luz (P/R) | Lixo (P/R) | Tipo de sinal certo | Erro mediano sinal / luz |
|---|---|---|---|---|---|
| OWLv2 + CLIP zero-shot | 0,42 / 0,66 | 0,35 / 0,63 | 0,31 / 0,45 | 21% (36 de 172) | 5,0 m / 6,3 m |
| OWLv2 + CLIP + cabeça | 0,46 / 0,52 | 0,40 / 0,65 | 0,30 / 0,40 | 44% (57 de 131) | 4,8 m / 4,0 m |
| YOLO11s + CLIP + cabeça | 0,49 / 0,51 | 0,44 / 0,69 | 0,39 / 0,22 | 54% (73 de 134) | 3,8 m / 3,8 m |

Notas para ler a tabela:

- A linha zero-shot é de uma corrida anterior (limiar de tipo 0,5, sem `limiar_detecao`, amostra de 375 sinais de referência em vez de 383). Não é uma comparação perfeita.
- A cabeça duplica o tipo certo (21% para 44%) e o YOLO acrescenta 10 pontos, em parte por ter caixas mais ajustadas.
- O YOLO é cerca de 4 vezes mais rápido (1,6 imagens por segundo contra 0,37) e dá menos erro de posição.
- O lixo é o ponto fraco do YOLO: recall de 22%, contra 40% do OWLv2. As papeleiras quase não aparecem (recall de 5%); o Vistas tem poucos exemplos de "trash-can".
- O limiar de deteção de 0,3 não melhorou o F do sinal na zona de teste (0,50 com e 0,51 sem): ajudou no Rossio, mas não aqui.
- Uma única corrida por configuração e uma única zona de teste: diferenças de poucos pontos não são significativas.
- **As linhas desta tabela não usam as mesmas imagens.** A amostra "regular" de 400 escolhia uma imagem a cada `n/400` da listagem do Mapillary, e a listagem muda de uma corrida para outra (mesmo com minutos de intervalo): duas corridas seguidas tinham só 43 de 400 imagens em comum, e a mesma configuração deu F de resíduos 0,37 numa e 0,26 na outra. A amostra passou a escolher as 400 imagens com menor hash do id, o que a mantém estável (400 de 400 em comum entre corridas).

### Limiares de deteção do YOLO (17 de novembro)

Afinação no Rossio (400 imagens, YOLO com limiar bruto 0,1, um limiar `limiar_detecao` igual para todas as categorias, de 0,1 a 0,6): as curvas de F são quase planas. Melhor F do sinal a 0,10–0,15 (0,58 contra 0,55 a 0,3), da iluminação a 0,35 (0,56 contra 0,53), dos resíduos a 0,3 (0,56).

Medição única na zona de teste, sobre a mesma amostra estável de 400 imagens:

| Limiares | Sinal (P/R) | Luz (P/R) | Lixo (P/R) | Tipo de sinal certo |
|---|---|---|---|---|
| 0,3 em todas (atual) | 0,43 / 0,48 | 0,43 / 0,63 | 0,36 / 0,27 | 54% (64 de 119) |
| sinal 0,15, luz 0,35, lixo 0,3 | 0,43 / 0,51 | 0,45 / 0,63 | 0,36 / 0,27 | 52% (66 de 128) |

Ganho de 0,01 a 0,02 no F, que no sinal exigiria também baixar o limiar bruto do worker. Os limiares ficam em 0,3.
