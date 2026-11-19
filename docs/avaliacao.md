# Avaliação

Estado (19 de novembro): medições feitas contra uma referência automática do Mapillary e, para o tipo de luz, contra caixas desenhadas à mão pelo técnico. A zona piloto não tem posições de referência. Os números abaixo são medições, não estimativas; cada uma é uma única corrida e as amostras de candeeiros são pequenas, o que se diz onde pesa. A secção sobre iluminação, no fim, é a mais recente.

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
| Rua do ISCA até à Av. Mário Sacramento | `config/municipio.yaml` | piloto (desde 19/11) | sem posições; caixas desenhadas à mão numa parte das imagens |
| Rossio | `config/avaliacao/rossio.yaml` | afinar limiares | 621 elementos |
| Av. Lourenço Peixinho | `config/avaliacao/lourenco_peixinho.yaml` | teste, nunca para afinar | 747 elementos |
| Verdemilho (Av. Europa) | `config/avaliacao/verdemilho.yaml` | teste, nunca para afinar nem treinar | 179 luzes, 54 papeleiras, 194 sinais |
| Mário Sacramento | `config/avaliacao/mario_sacramento.yaml` | treino do tipo de luz | luzes do Mapillary |
| Santa Joana (Gulbenkian) | `config/avaliacao/santa_joana.yaml` | treino do tipo de luz | luzes do Mapillary |

A Rua da Pega foi a zona piloto até 19/11 (160 elementos de referência automática). Foi abandonada porque a equipa não a pôde usar. O vídeo que existe dela serve de teste do caminho vídeo mais GPX (ver a secção de iluminação).

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

## Iluminação (19 de novembro)

O foco da equipa. Três perguntas: onde fica cada luz, se o mesmo poste aparece uma só vez, e se é poste de luz ou candeeiro.

### Posição das luzes (imagens do Mapillary)

Configuração: limiar de deteção 0,3; raio de deduplicação 6,5 m; altura típica 6 m; alcance máximo 30 m (observações estimadas mais longe são ignoradas); luzes de tipos diferentes são alternativas do mesmo objeto, por isso nunca se separam por tipo (`tipos_exclusivos`). Referência: map features do Mapillary, emparelhamento a 15 m, só onde há imagens a menos de 30 m. A precisão está subestimada, porque a referência é incompleta.

| Zona | Imagens | Referências | F a 5, 10 e 15 m | P / R a 15 m | Erro mediano |
|---|---|---|---|---|---|
| Rossio (afinação) | 800 | 231 | 0,35 / 0,48 / 0,56 | 0,51 / 0,64 | 3,2 m |
| Verdemilho (teste) | 400 | 159 | 0,45 / 0,58 / 0,63 | 0,51 / 0,82 | 2,4 m |
| Mário Sacramento | 497 | 115 | 0,49 / 0,62 / 0,66 | 0,52 / 0,90 | 2,1 m |
| Santa Joana | 800 | 111 | 0,32 / 0,55 / 0,59 | 0,46 / 0,84 | 4,5 m |

Alcance máximo, o mesmo código com 60 m (o valor anterior) e 30 m: Rossio F a 15 m 0,54 contra 0,56 (precisão 0,43 contra 0,51, recall 0,73 contra 0,64); Verdemilho 0,59 contra 0,63 (precisão 0,45 contra 0,51, recall 0,85 contra 0,82). Alcances de 8 a 12 m pioram o F nas duas zonas. A explicação provável, não medida, é que um poste de 6 m só cabe inteiro numa imagem a partir de cerca de 7 m, e mais perto a distância estimada falha.

Tratar os tipos de luz como alternativas do mesmo objeto não muda estas métricas (iguais, ou mais 0,01, nas quatro zonas); serve para não criar dois elementos no mesmo poste quando o tipo varia entre fotografias (ver mais abaixo).

### Vídeo gravado na rua (Rua da Pega, 805 frames a 2 por segundo, 614 m)

Sem posições de referência, por isso as medições são de estabilidade e de coerência, não de erro de posição.

- O vídeo é vertical (1080 por 1920). O campo de visão de 65° estava aplicado à largura; passou a aplicar-se ao lado maior (cerca de 37° na horizontal). As imagens horizontais do Mapillary ficam com os mesmos valores de antes.
- Estabilidade: o `locate` corre só com os frames pares e só com os ímpares (1 frame por segundo cada, sem frames em comum) e vê-se que fração das luzes de uma metade tem par na outra. Antes do seguimento: 43% a 3 m, 62% a 5 m, 73% a 10 m. Cada caixa passou a ser seguida de frame em frame (um trilho, um elemento), e a concordância passou para 60%, 72% e 75%.
- Contagem: 80 luzes antes do seguimento, 48 depois (a contagem da equipa para a rua é 118, mas uma parte está do outro lado da estrada, fora do alcance de 30 m; com 45 m saem 74 luzes e a concordância baixa para 59% a 5 m).
- Alcance no vídeo: 30 m dá 48 luzes e 72% de concordância a 5 m; 45 m dá 74 luzes e 59%; 60 m dá 99 luzes e 56%.
- Frames por segundo, sobre as mesmas deteções e antes do seguimento: 2 por segundo (7,1 min na GPU) dá 80 luzes e 83 sinais; 1 por segundo (3,6 min) dá 68 e 74; 0,5 por segundo (1,8 min) dá 58 e 52. Abaixo de 1 por segundo perdem-se sinais.
- Medidas que não ajudaram e não foram adotadas: distância mínima entre câmaras na triangulação, mediana em vez de média, mínimos quadrados, posição pelas caixas maiores, mínimo de observações.

### Elementos duplicados

Numa análise de 231 imagens da zona piloto, 133 elementos de luz tinham 58 pares a menos de 4 m, 24 deles exatamente na mesma posição: a cabeça de tipo variava entre fotografias do mesmo poste e o `locate` separava as caixas por tipo. Com os tipos tratados como exclusivos (repetido offline sobre as mesmas deteções): 119 luzes, 35 pares, 5 na mesma posição. Num caso monocular com duas luzes a 3 m na mesma fotografia e tipos diferentes, o código antigo punha as duas no mesmo ponto (0,0 m).

### Poste de luz ou candeeiro

O YOLO só distingue "luz". O tipo vem de uma regressão logística sobre o CLIP, com as classes `candeeiro` e `poste_luz` (nunca descarta). Treino: caixas desenhadas à mão pelo técnico em Mário Sacramento, Santa Joana e Rua da Pega, cortadas das 6 vistas retilíneas que o classificador vê nos panoramas (3559 recortes, 220 de candeeiros). Treinar com recortes da imagem esticada, como se fazia, é pior: na zona do ISCA com a zona de fora do treino, 28 de 67 candeeiros certos contra 56 de 67. O Verdemilho ficou fora de todo o treino.

Deixando uma zona de fora, recortes de vistas, limiar 0,5:

| Zona de teste | Candeeiros / postes | AUC | Candeeiros certos | Postes dados como candeeiro |
|---|---|---|---|---|
| ISCA | 67 / 416 | 0,96 | 56 | 12 (3%) |
| Santa Joana | 107 / 1193 | 0,85 | 56 | 94 (8%) |
| Mário Sacramento inteiro | 111 / 1640 | 0,86 | 49 | 133 (8%) |
| Verdemilho | 21 / 488 | 0,89 | 11 | 52 (11%) |

Fora da zona o erro é de 8 a 11% dos postes. Como os candeeiros são poucos (4% no Verdemilho), a precisão do candeeiro cai muito aí (0,17); na zona do ISCA, onde são frequentes, é de 0,82. A decisão é por limiar, aplicado no ficheiro da cabeça: 0,6 é o compromisso escolhido (zona do ISCA: 42 de 67 certos e 4 postes errados de 416).

Pipeline completo (YOLO, vistas, CLIP) nas imagens com caixas desenhadas do Verdemilho, zona que o classificador nunca viu (17 candeeiros e 372 postes de luz):

| Cabeça | Candeeiros certos | Postes dados como candeeiro | Precisão |
|---|---|---|---|
| Nenhuma | 0 de 17 | 0 | |
| Primeira (recortes da imagem esticada) | 6 de 17 | 32 | 0,16 |
| Nova (candidata, ainda não ligada), limiar 0,6 | 6 de 17 | 17 | 0,26 |
| Nova, limiar 0,7 | 6 de 17 | 13 | 0,32 |
| Nova, limiar 0,8 | 4 de 17 | 4 | 0,50 |
| Nova, limiar 0,6, recorte mínimo de 8 px em vez de 12 | 8 de 17 | 17 | 0,32 |

Revisão do técnico a uma análise da zona piloto (primeira cabeça, argmax): 40 elementos classificados como candeeiro, 28 certos, 10 eram postes de luz com o braço dobrado no topo, 1 uma cena de água das casas e 1 uma câmara (as duas últimas nem são luzes: falsos positivos do detetor).

Limitações: 17 a 21 candeeiros nas zonas de teste, por isso as diferenças de um ou dois exemplos não são significativas; os candeeiros da Rua da Pega, todos do outro lado da estrada, ficam a 45 m ou mais num vídeo vertical gravado do passeio e nem o CLIP nem um classificador treinado os distinguem de forma útil (a cabeça treinada com os recortes do vídeo só aprendia o tamanho da caixa); a cabeça só foi medida em quatro zonas de Aveiro, e generaliza pior a zonas novas do que à zona onde foi treinada.

### Falsos positivos do detetor

Uma cabeça com as classes "não é luz" e "poste elétrico" não generaliza (AUC de 0,54 a 0,80 deixando uma zona de fora): no Verdemilho, com um limiar de 0,7, remove 30 de 168 falsos (18%) e destrói 30 de 509 luzes verdadeiras (6%); com 0,5 remove 65% dos falsos mas destrói 31% das luzes. Não é usada; o técnico rejeita em Avaliar o que não é luz.
