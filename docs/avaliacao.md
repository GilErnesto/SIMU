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

Configuração: limiar de deteção 0,3; raio de deduplicação 6,5 m; altura típica 6 m para a distância monocular (4 m para o candeeiro e 7 m para o poste de luz desde 20 de novembro, ver abaixo); alcance máximo 30 m (observações estimadas mais longe são ignoradas); luzes de tipos diferentes são alternativas do mesmo objeto, por isso nunca se separam por tipo (`tipos_exclusivos`). Referência: map features do Mapillary, emparelhamento a 15 m, só onde há imagens a menos de 30 m. A precisão está subestimada, porque a referência é incompleta.

| Zona | Imagens | Referências | F a 5, 10 e 15 m | P / R a 15 m | Erro mediano |
|---|---|---|---|---|---|
| Rossio (afinação) | 800 | 231 | 0,35 / 0,48 / 0,56 | 0,51 / 0,64 | 3,2 m |
| Verdemilho (teste) | 400 | 159 | 0,45 / 0,58 / 0,63 | 0,51 / 0,82 | 2,4 m |
| Mário Sacramento | 497 | 115 | 0,49 / 0,62 / 0,66 | 0,52 / 0,90 | 2,1 m |
| Santa Joana | 800 | 111 | 0,32 / 0,55 / 0,59 | 0,46 / 0,84 | 4,5 m |

Alcance máximo, o mesmo código com 60 m (o valor anterior) e 30 m: Rossio F a 15 m 0,54 contra 0,56 (precisão 0,43 contra 0,51, recall 0,73 contra 0,64); Verdemilho 0,59 contra 0,63 (precisão 0,45 contra 0,51, recall 0,85 contra 0,82). Alcances de 8 a 12 m pioram o F nas duas zonas. Como a avaliação só conta referências a menos de 30 m de uma imagem e isso podia favorecer o alcance curto, repetiu-se a comparação com a cobertura alargada a 60 m, nas cinco zonas e com as alturas por tipo: 30 m continua o melhor (F médio a 5, 10 e 15 m de 0,427 / 0,550 / 0,610, contra 0,420 / 0,542 / 0,598 a 35 m, 0,392 / 0,539 / 0,599 a 45 m e 0,373 / 0,518 / 0,571 a 60 m). A explicação provável, não medida, é que um poste de 6 m só cabe inteiro numa imagem a partir de cerca de 7 m, e mais perto a distância estimada falha.

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

### Zona piloto, análise de 19 de novembro (Rua do ISCA até à Av. Mário Sacramento)

231 imagens do Mapillary (183 panoramas), analisadas em 3 min 43 s na GPU (cerca de 1 s por imagem, porque os panoramas dominam). 240 elementos: 120 de iluminação (73 por triangulação), 14 de resíduos e 106 de sinais. Não há posições de referência nesta zona.

Iluminação: 85 postes de luz, 29 candeeiros e 6 por classificar. A primeira versão desta análise (cabeça de tipo anterior e luzes separadas por tipo) tinha 133 luzes (88 postes de luz, 40 candeeiros, 5 por classificar), e a revisão do técnico aos 40 candeeiros deu 28 certos, 10 postes de luz, 1 cena de água e 1 câmara. Na versão atual, uma leitura visual minha aos 29 candeeiros (não é uma revisão do técnico) vê quase todos como candeeiros de globo e 4 que destoam, 3 postes altos com braço e a câmara, ou seja cerca de 25 certos em 29. A medição que conta é uma nova revisão do técnico.

Os possíveis duplicados propostos na revisão passaram de 107 para 82 pares. Os pares de luzes exatamente na mesma posição baixaram de 24 para 6; ficam 46 pares de sinais, 24 deles com classes diferentes na mesma posição (dois sinais no mesmo poste, que são elementos distintos).

### Altura por tipo de luz e recorte mínimo (20 de novembro)

A distância monocular usa uma altura típica por tipo: candeeiro 4 m, poste de luz 7 m, e 6 m para o que ficou por classificar. Mediu-se a altura efetiva com posições trianguladas na análise piloto: cerca de 4,2 m para o candeeiro e 7,4 m para o poste de luz, estável de 15 a 40 m. O erro mediano da distância monocular na zona piloto desce de 15,9 para 7,9 m nos candeeiros e de 9,3 para 7,5 m nos postes. Em quatro das cinco zonas do Mapillary com referência a posição melhora (em Santa Joana o F a 10 m desce 0,02); o Rossio, a zona de afinação, piora um pouco (F da luz a 5 m de 0,33 para 0,30; erro de 3,3 para 4,1 m).

| Zona | F da luz a 5, 10 e 15 m, com 6 m para todas | com 4 m e 7 m por tipo | Erro mediano a 15 m |
|---|---|---|---|
| Verdemilho | 0,45 / 0,58 / 0,63 | 0,50 / 0,59 / 0,64 | 2,4 para 1,6 m |
| Av. Lourenço Peixinho | 0,28 / 0,45 / 0,52 | 0,35 / 0,47 / 0,55 | 4,1 para 3,3 m |
| Mário Sacramento | 0,49 / 0,62 / 0,66 | 0,52 / 0,63 / 0,67 | 2,1 para 1,8 m |
| Santa Joana | 0,32 / 0,55 / 0,59 | 0,41 / 0,53 / 0,60 | 4,5 para 3,4 m |
| Rossio (afinação) | 0,33 / 0,44 / 0,50 | 0,30 / 0,44 / 0,51 | 3,3 para 4,1 m |

O recorte mínimo que o classificador de tipo aceita desce de 12 para 8 px na iluminação (os sinais e os resíduos mantêm 12). No Verdemilho, zona nunca vista pela cabeça, os candeeiros certos passam de 6 para 8 de 17 e já não ficam luzes por classificar; os postes dados como candeeiro mantêm-se em 17 de 372. Com 6 ou 4 px não há ganho adicional no Verdemilho.

Duas correções ao agrupamento da iluminação, medidas nas mesmas deteções gravadas. Primeira, um erro: quando a distância monocular de uma caixa ficava acima do alcance, o `separar` colocava-a no centro do grupo e criava um elemento fantasma aí, com posição errada (daí luzes a 0,0 m umas das outras); agora essas caixas são descartadas. Segunda, a caixa de menor confiança que está 80% ou mais dentro de outra maior da mesma imagem (em geral um fragmento do mesmo poste) deixa de contar. O F da luz a 5, 10 e 15 m, média das cinco zonas, passa de 0,413 / 0,530 / 0,595 (só as alturas por tipo) para 0,422 / 0,541 / 0,602 com a supressão de caixas contidas e para 0,436 / 0,560 / 0,620 com as duas correções, que melhoram todas as zonas, incluindo o Rossio:

| Zona | Antes (alturas por tipo) | Depois das duas correções |
|---|---|---|
| Rossio (afinação) | 0,30 / 0,44 / 0,51 | 0,32 / 0,48 / 0,55 (precisão a 15 m 0,51 para 0,60) |
| Verdemilho | 0,50 / 0,59 / 0,64 | 0,52 / 0,63 / 0,68 |
| Av. Lourenço Peixinho | 0,35 / 0,47 / 0,55 | 0,38 / 0,49 / 0,56 |
| Mário Sacramento | 0,52 / 0,63 / 0,67 | 0,53 / 0,66 / 0,69 |
| Santa Joana | 0,41 / 0,53 / 0,60 | 0,43 / 0,54 / 0,62 |

Os sinais e os resíduos não mudam (mesmo F a 10 m nas cinco zonas). Os outros parâmetros da luz, medidos de novo com as alturas por tipo (limiar de deteção de 0,25 a 0,5, raio de deduplicação de 5 e 8 m, alcance de 25, 40 e 50 m), não dão ganho consistente em relação ao que está (diferenças de 0,01 na média, e o Rossio prefere a base), por isso ficam. Na zona piloto, sobre as mesmas deteções, as luzes passam de 124 para 105 (os fantasmas), os pares a menos de 2 m de 20 para 4 e as luzes com caixas repetidas do mesmo frame de 8 para 2.

Uma terceira correção, esta no detetor. Comparando com as 2390 luzes que o utilizador rotulou à mão (Verdemilho, Mário Sacramento até à imagem 162 e Santa Joana), o pipeline apanha 95% das luzes entre 15 e 30 m (94% chegam a um elemento) mas só 72% das que estão a menos de 15 m, e quase todas as falhadas são postes altos muito próximos nos panoramas: o topo sai das vistas horizontais de 90°. Numa vista centrada no poste e inclinada 25 a 40 graus para cima, o detetor recupera 80 a 87 de 111 dessas luzes (84% com qualquer das três inclinações; 6 sem inclinar). Por isso, nos panoramas, a iluminação passa a ter também 6 vistas inclinadas 35 graus, e só se acrescentam as deteções que não se sobrepõem a nenhuma das vistas horizontais, com altura mínima de 20% do panorama e confiança de 0,6 ou mais. Acrescentar as inclinadas sem estas condições piorava tudo (as caixas inclinadas, mais deformadas, substituíam boas caixas horizontais): luzes a 15 a 30 m detetadas de 97% para 91% e F pior. Com as condições, nas três zonas juntas: luzes rotuladas a menos de 15 m com elemento 72% para 79%, a 15 a 30 m iguais (94%), erro mediano da posição 1,98 para 1,88 m e F a 5, 10 e 15 m 0,495 / 0,615 / 0,656 para 0,508 / 0,612 / 0,655 (neutro: a referência do Mapillary, incompleta, pode não ter estes postes próximos). Das deteções acrescentadas com confiança de 0,5 ou mais, 82% sobrepõem uma luz rotulada. O custo é mais 6 passagens do detetor por panorama. O NMS dos panoramas também suprime agora a caixa de menor confiança que está 70% ou mais dentro de outra (sem efeito em sinais e resíduos: F igual, 0,00 a +0,01).

O classificador do tipo de sinal passou a ser treinado com menos regularização (C=30 em vez de C=1). Na validação, a exatidão sobe de 79,1% para 84,0% (com C=100, 84,8%; a validação é otimista, porque as fotografias são vizinhas). Nas cinco zonas de avaliação, que nunca entraram no treino, reclassificando os recortes dos sinais já detetados, o tipo certo sobe de 64,3% (305 de 474) para 66,2% (315 de 476): Rossio 58% para 60%, Verdemilho 77% para 80%, Lourenço Peixinho 61% para 65%, Mário Sacramento 75% igual e Santa Joana 54% igual; stop igual (recall 0,63) e obrigação de 0,52 para 0,60. A cabeça de luz usa C=10 no treino por `training.tipos` (melhor offline, sem diferença ponta a ponta no Verdemilho). A análise piloto final, com tudo incluindo as vistas inclinadas e a cabeça de sinais nova, tem 209 elementos: 100 luzes (71 postes de luz e 29 candeeiros, nenhuma por classificar), 94 sinais, 15 resíduos, 13 pares de luzes a menos de 4 m. Antes da cabeça de sinais nova tinha 211 elementos: 99 luzes (70 postes de luz e 29 candeeiros, nenhuma por classificar), 11 pares de luzes a menos de 4 m e 32 pares no painel de possíveis duplicados. Numa leitura visual minha (não é revisão do técnico), 1 dos 29 candeeiros é um poste alto com braço (mais 4 duvidosos) e 3 dos 70 postes de luz não são luz (2 semáforos e o poste de um sinal de STOP), ou seja, entre 83% e 97% de candeeiros certos e cerca de 96% de postes de luz certos. Cruzando os elementos desta análise com as caixas que o técnico rotulou à mão nas imagens do ISCA (53 elementos de luz com observações rotuladas; nota: a cabeça de tipo foi treinada com estes rótulos, por isso é uma medida de coerência e não independente): em 49 o tipo coincide com o rotulado (92%); em 4 o técnico rotulou candeeiro e o sistema deu poste de luz; 3 elementos têm todas as observações rotuladas como não-luz (2 semáforos). A leitura visual acima usa um critério meu (poste alto com braço é poste de luz) que pode divergir do critério do técnico, que chama candeeiro também a postes com braço de altura média; por isso essas percentagens são indicativas. Cobertura medida no catálogo real contra as luzes rotuladas pelo técnico nas 53 imagens do ISCA presentes na análise: 95% das de 15 a 30 m (73 de 77), 78% das de menos de 15 m (47 de 60) e 75% das de mais de 30 m (124 de 166). A análise demora cerca de 6,3 minutos para 231 imagens (0,61 imagens por segundo; eram 3 min 43 s antes das vistas inclinadas).

Antes das vistas inclinadas, a análise piloto tinha 220 elementos: 104 luzes (74 postes de luz e 30 candeeiros, nenhuma por classificar), 12 pares de luzes a menos de 4 m e 35 pares no painel de possíveis duplicados. Numa leitura visual minha (não é revisão do técnico), dos 30 candeeiros 2 são postes altos com braço (mais 3 duvidosos) e dos 74 postes de luz 4 não são luz (3 semáforos e o poste de um sinal de STOP), o que dá uma precisão do candeeiro entre 83% (contando os duvidosos como erros) e 93% e do poste de luz de cerca de 95% nesta zona.

Antes destas duas correções, a análise piloto refeita com as alturas por tipo e o recorte mínimo tinha: 124 luzes (88 postes de luz, 36 candeeiros, nenhuma por classificar), 28 pares a menos de 4 m. Uma leitura visual minha aos 36 candeeiros (não é revisão do técnico) vê os de parque, de globo, como certos e 8 como postes altos com braço dados como candeeiro, o que dá uma precisão do candeeiro de cerca de 78%, igual à medida fora da zona.

### YOLO26s contra YOLO11s (20 de novembro)

O YOLO26s foi treinado com os mesmos dados do YOLO11s (Open Images V7 e Mapillary Vistas), as mesmas imagens, 1024 px, lote 6 e 31 épocas, em 2,89 h. Na validação (577 imagens, 7295 instâncias):

| Modelo | Precisão | Recall | mAP50 | mAP50-95 | Inferência | Parâmetros |
|---|---|---|---|---|---|---|
| YOLO11s (atual) | 0,680 | 0,454 | 0,508 | 0,317 | 10,4 ms | 9,4 M |
| YOLO26s | 0,707 | 0,465 | 0,535 | 0,342 | 9,8 ms | 10,0 M |

O YOLO26s é melhor em todas as classes (mAP50: candeeiro 0,478 contra 0,454, contentor 0,359 contra 0,331, sinal genérico 0,607 contra 0,575, semáforo 0,698 contra 0,671).

Ponta a ponta, com o pipeline atual (400 imagens por zona, emparelhamento a 15 m, referência do Mapillary), o resultado é um empate. Média simples das três zonas (Verdemilho, Lourenço Peixinho, Rossio), precisão / recall / F:

| Categoria | YOLO11s | YOLO26s |
|---|---|---|
| Sinal | 0,62 / 0,52 / 0,56 | 0,61 / 0,52 / 0,56 |
| Luz | 0,48 / 0,67 / 0,55 | 0,51 / 0,66 / 0,56 |
| Resíduos | 0,61 / 0,51 / 0,55 | 0,59 / 0,46 / 0,51 |

Nos resíduos o recall desce no Verdemilho (0,77 para 0,66) e no Rossio (0,50 para 0,41) e sobe em Lourenço Peixinho (0,27 para 0,32). O tipo de sinal certo fica em 77%, 57% e 51% contra 73%, 56% e 56%. A bancada demora cerca de 5% menos, porque o CLIP domina o tempo.

Não foi adotado. O ganho de 0,02 a 0,03 de mAP no detetor não chega ao catálogo, e os limiares de deteção e a calibração da confiança da luz foram medidos com o YOLO11s, não foram refeitos para o YOLO26. Cada configuração foi corrida uma só vez, por isso diferenças de poucos pontos não são significativas. Os pesos estão em `models/detetor26.pt` (o `detetor.pt` continua a ser o YOLO11s).

### Privacidade: verificação independente das imagens anonimizadas (20 de novembro)

Voltou-se a correr os dois detetores do EgoBlur (rostos e matrículas, o mesmo limiar do pipeline) sobre todas as 2191 imagens já guardadas em `data/anon`: 571 do Mapillary, 10 envios e 1610 frames de vídeo (os 805 frames da Rua da Pega, analisados duas vezes). O EgoBlur volta a reconhecer as matrículas já desfocadas, por isso as deteções foram separadas medindo a nitidez do centro de cada caixa: um retângulo desfocado é plano e uma matrícula legível tem contraste (variância do Laplaciano mediana de 2,3 nas caixas sinalizadas, com uma cauda nítida bem separada). Todas as caixas nítidas foram revistas à vista.

| Origem | Imagens | Caixas nítidas | O que eram |
|---|---|---|---|
| Mapillary | 571 | 2 | uma grelha e uma fachada (falsos positivos, não são matrículas) |
| Envios | 10 | 0 | |
| Vídeo da Rua da Pega | 805 frames distintos | 8 frames distintos (1,0%) | 5 matrículas legíveis ou parcialmente legíveis (0,6%), 1 caixa pequena de rosto, 1 matrícula minúscula, 1 sinal de trânsito apanhado por engano |

Ou seja, a anonimização em passagem única deixava escapar matrículas em cerca de 0,6% dos frames do vídeo (por exemplo "89-RF-25" legível no frame 22). As imagens do Mapillary, que já vêm desfocadas, ficaram limpas.

Correção: os 16 ficheiros afetados (8 frames, nas duas análises do mesmo vídeo) foram passados mais uma vez pelo EgoBlur e a nova varredura já não encontra caixas nítidas, e o `Anonymizer` passou a fazer duas passagens: depois de desfocar, volta a detetar sobre a imagem já desfocada e desfoca o que sobrar (só pode desfocar mais). Custo medido na GPU: o EgoBlur passa de 0,29 para 0,58 s por imagem (mediana de 22 imagens); no CPU o tempo duplica.

Limitação: é uma segunda opinião do mesmo detetor. O que o EgoBlur não vê em nenhuma das passagens (ângulos difíceis, matrículas minúsculas ou muito desfocadas pelo movimento) não aparece nesta medição, e o número de casos que ficam por encontrar é desconhecido.
