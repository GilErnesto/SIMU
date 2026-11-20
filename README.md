# SIMU

**Sistema de Identificação de Mobiliário Urbano.** Projeto do ATC Hackathon 2026 (Aveiro Tech City Hackathon), desafio 2, da Câmara Municipal de Aveiro e da Universidade de Aveiro.

A aplicação deteta mobiliário urbano em imagens de rua (sinais de trânsito, candeeiros e postes de luz, contentores e ecopontos), calcula a posição de cada elemento, guarda-o num catálogo PostGIS, mostra-o num mapa onde um técnico o corrige, e exporta GeoJSON e CSV. Zona piloto: Rua do ISCA até à Av. Dr. Mário Sacramento, em Aveiro.

- Entrada: fotografias com GPS, vídeos com GPX, ou uma zona do Mapillary.
- Privacidade: rostos e matrículas são desfocados (EgoBlur) antes de qualquer imagem ser gravada.
- Só modelos locais e de código aberto na deteção, sem APIs externas.
- Nada específico de Aveiro no código: o município vem de `config/`.

## Arranque rápido (Docker)

Requisitos: Docker. Para a GPU, uma placa NVIDIA e, no Linux, o `nvidia-container-toolkit` (`docker run --rm --gpus all ubuntu nvidia-smi` deve mostrar a placa); no Windows basta o Docker Desktop com WSL2 e o controlador NVIDIA.

```bash
cp .env.example .env
mkdir -p models data/anon data/raw
```

Em `.env`, preencher a palavra-passe da base (igual em `POSTGRES_PASSWORD` e `DATABASE_URL`, sem `@`, `/` nem `:`). O `MAPILLARY_TOKEN` só é preciso para o pipeline do Mapillary. Pôr os modelos em `models/` (ver "Modelos").

**Com GPU NVIDIA** (recomendado):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

**Sem GPU** (CPU):

```bash
docker compose up -d --build
```

Abrir `http://localhost:8080`. A API fica em `http://localhost:8010` (documentação em `/docs`). Tudo escuta só em `127.0.0.1`. Parar com `docker compose down` (os dados ficam no volume `pgdata`; `down -v` apaga-os).

| Serviço | Porta | Variável |
|---|---|---|
| Interface | 8080 | `FRONTEND_PORT` |
| API | 8010 | `BACKEND_PORT` |
| Base de dados | 5440 | `POSTGRES_PORT` |

### GPU ou CPU

| | Tempo por imagem |
|---|---|
| GPU (RTX 4060 laptop) | cerca de 0,5 s por fotografia; a zona piloto (231 imagens, 183 panoramas) demora cerca de 6,3 minutos, com duas passagens do EgoBlur e, nos panoramas, vistas inclinadas para a iluminação |
| CPU (4 núcleos) | 15 a 30 s, quase tudo na anonimização |

Desde 20/11 o EgoBlur corre duas passagens (a segunda sobre a imagem já desfocada, para apanhar o que a primeira deixou escapar): cerca de 0,3 s a mais por imagem na GPU (medido) e o dobro do tempo no CPU, por isso os tempos desta tabela são anteriores. O CPU serve para poucas fotografias. Na GPU o EgoBlur corre em meia precisão com o limiar de rostos e matrículas 0,05 mais baixo: desfoca um pouco mais, nunca menos. A imagem do worker com GPU tem cerca de 11 GB; o primeiro build demora uns minutos, os seguintes só segundos se mudar apenas o código. `WORKER_CPUS` e `WORKER_MEM` no `.env` limitam o worker.

## Usar a interface

1. Largar fotografias, vídeos e GPX na página inicial. Cada envio é uma análise, com endereço próprio (`/a/<código>`).
2. O **worker** analisa-os. Se ele não estiver a correr, a análise fica "Na fila" e a interface avisa.
3. Na análise: mapa, lista com filtros, fotografias com a caixa desenhada, e Avaliar (validar, rejeitar, corrigir tipo e posição, juntar ou separar elementos). Exportar em GeoJSON ou CSV pelo menu Exportar.

Regras dos envios:

- Fotografias: GPS e, de preferência, direção no EXIF (sem direção, deduz-se das vizinhas). **Sem GPS a fotografia é analisada na mesma**: os elementos aparecem na lista com o aviso "GPS indisponível", e o técnico indica a posição ao avaliar.
- Vídeos: de preferência com um GPX gravado ao mesmo tempo, com o mesmo nome ou como único par. O início do vídeo assume-se igual ao do GPX, com desfasamento opcional. **Sem GPX, ou com frames fora do trilho, os frames são analisados na mesma**, com um aviso, e os elementos ficam sem posição. Sem posição não se juntam elementos entre imagens, por isso há duplicados.
- Os originais ficam em `data/raw/<código>/` (nunca servida pela API) só até a análise acabar bem. Só a versão anonimizada vai para `data/anon/`.
- A lixeira, na lista de análises, apaga a análise inteira (base de dados e ficheiros).

## Modelos

Em `models/` (fora do git):

- `models/egoblur/ego_blur_face.jit` e `ego_blur_lp.jit`: EgoBlur, pedidos à Meta. Sem eles nada é gravado.
- `models/detetor.pt`: YOLO próprio (ver "Treino"). Sem ele usa-se o OWLv2 zero-shot. Se existirem também `models/detetor_b23.pt`, `models/detetor_b23_1280.pt` e `models/detetor_b23p_1280.pt`, usa-os todos em conjunto (`--pesos a.pt,b.pt,...`): as caixas em que concordam ficam com confiança alta. Corre com aumento em teste (inversão e escalas); `--sem-aumento` desliga-o e `--ladrilhos` procura também em recortes de 1024 px das fotos grandes (mais lento).
- `models/tipo_sinal.npz`: cabeça que escolhe o tipo de sinal. Sem ela o tipo vem do CLIP zero-shot.

O CLIP (1,7 GB) descarrega-se na primeira análise. Para reutilizar a cache que já tens, define `HF_CACHE` no `.env` (por exemplo `~/.cache/huggingface`).

Deteção em duas fases: o YOLO (ou OWLv2) encontra só os "três grandes" (sinal, candeeiro, contentor) e o CLIP classifica o tipo no recorte, descartando o que não conta (portas, letreiros). O tipo do elemento sai da votação de todas as imagens que o veem.

## Configuração

- `config/municipio.yaml`: nome, bbox e CRS métrico (zona piloto).
- `config/classes.yaml`: taxonomia, limiares, raio de deduplicação, altura típica (distância monocular) e descrições do CLIP.
- `config/avaliacao/` e `config/treino/`: zonas de avaliação e de treino, no mesmo formato.

## Desenvolvimento sem Docker

Requisitos: Python 3.11 ou superior, Node 20 ou superior.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,api,ml]"
docker compose up -d db
uvicorn backend.main:app --reload
python -m pipeline.worker
cd frontend && npm install && npm run dev
```

A interface fica em `http://localhost:5173` e fala com a API pelo prefixo `/api`. Se a API não estiver na porta 8000: `API_URL=http://localhost:PORTA npm run dev`. Variáveis opcionais da API: `MUNICIPIO_YAML` e `ANON_DIR`.

### Pipeline do Mapillary

```bash
python -m pipeline.run --bbox -8.653933,40.630337,-8.648515,40.632975
```

`--bbox` é `lon_min,lat_min,lon_max,lat_max` (longitude primeiro) e dispensa criar um `.yaml`: usa o município e o CRS de `config/municipio.yaml`. Sem `--bbox` usa a bbox desse ficheiro. Também existe em `pipeline.bancada` e `pipeline.referencia`.

Aparece como uma análise por zona. Imagens já registadas são ignoradas. Opções: `--detetor owlv2|yolo|auto`, `--limiar`, `--sem-refinar`, `--limiar-classe`, `--regenerar-imagens` (recria a cache de `data/anon`).

## API

- `GET /elementos` (filtros `bbox`, `categoria`, `estado`, `analise`, `classe`, ...) e `GET /elementos/{id}`.
- `PATCH /elementos/{id}`: corrige classe, posição ou estado. Cada alteração fica em `correcao`; nunca se apaga um elemento.
- `GET /export.geojson` e `GET /export.csv`.
- `POST /analises`, `GET /analises`, `GET /analises/{token}`, `DELETE /analises/{token}`.
- `POST /analises/zona`: analisa uma zona do Mapillary (`{bbox: [lon_min, lat_min, lon_max, lat_max], nome}`, no máximo 0,02° de lado). O worker recusa zonas com mais de `MAX_IMAGENS_ZONA` imagens (1500 por omissão) com a mensagem "A zona tem N imagens, mais do que o máximo...", porque uma análise em curso não se cancela e uma zona densa (o centro de Aveiro tem 1669 imagens numa área de 250 por 220 m) ocuparia o worker cerca de 45 minutos. Um vídeo que gere mais de `MAX_IMAGENS_VIDEO` imagens (1500 por omissão, ou seja 12,5 minutos a 2 imagens por segundo) falha logo, em segundos, com o número de imagens e a sugestão de reduzir as imagens por segundo ou cortar o vídeo.
- `GET /analises/{token}/duplicados`: pares da mesma categoria a menos de 4 m (`raio` muda a distância).
- `POST /elementos/{id}/juntar` (`{origem, autor}`) e `POST /elementos/{id}/separar` (`{observacoes, autor}`): revisão manual, sempre registada em `correcao`.
- `GET /imagens/{id}`: só serve ficheiros de `ANON_DIR`.

## Testes

```bash
pytest
TEST_DATABASE_URL=postgresql+psycopg://utilizador:palavra-passe@localhost:5432/base_de_testes pytest
```

Os testes de catálogo e API só correm com `TEST_DATABASE_URL`, que tem de apontar a uma base descartável e vazia.

## Treino

Os três grandes treinam-se com o Open Images e o Mapillary Vistas:

```bash
python -m training.datasets.openimages
python -m training.datasets.vistas --origem datasets/mtsd_raw/<pasta mtsd_v2_fully_annotated>
python -m training.train --config training/configs/grandes.yaml
```

O tipo de sinal aprende-se com as deteções da API do Mapillary:

```bash
python -m training.datasets.tipos_mapillary --zona config/treino/aveiro_tipos.yaml --excluir config/municipio.yaml config/avaliacao/rossio.yaml config/avaliacao/lourenco_peixinho.yaml
python -m training.tipos recortar
python -m training.tipos treinar
```

`treinar` ajusta uma regressão logística sobre o CLIP, compara-a com o CLIP zero-shot (`data/datasets/tipos/relatorio.json`) e grava `models/tipo_sinal.npz`. Com o MTSD verdadeiro (conta em `mapillary.com/dataset/trafficsign`): `python -m training.datasets.mtsd --origem <pasta>` e `training/configs/sinais.yaml`.

### Treinar com as correções do técnico

O que o técnico faz na interface não treina nada sozinho. Este comando exporta-o para recortes no mesmo formato do tipo de sinal e treina-se com o comando já existente:

```bash
python -m training.correcoes --categoria iluminacao --referencia data/avaliacao/referencia_tecnico.geojson
python -m training.tipos treinar --saida data/datasets/correcoes_iluminacao --categoria iluminacao --destino models/tipo_iluminacao.npz
```

- Entram elementos `validado` (com a classe do elemento), `corrigido` com a classe alterada, e `rejeitado` (como `nao_luz`, só na iluminação). Elementos só com a posição corrigida não confirmam a classe.
- Os recortes saem de `data/anon` (já anonimizada). Nos panoramas o recorte sai da vista retilínea de 90° onde a caixa aparece maior, porque é assim que o classificador vê a imagem; caixas fora das vistas (perto do zénite) ficam de fora.
- `--analise <código>` (repetível) limita a análises escolhidas. `--referencia` grava as posições indicadas pelo técnico, para medir a localização.
- Se `models/tipo_iluminacao.npz` existir, o pipeline passa a usá-lo.
- Cuidado: quem só valida o que o detetor achou não gera falsos negativos, e fotografias vizinhas dão uma validação otimista.

- Todas as imagens passam pelo EgoBlur antes de serem gravadas em `data/datasets/`. Nada disto vai para o git.
- O autor e a licença de cada imagem ficam em `atribuicao.csv`, na pasta de cada dataset.
- **Os pesos só servem para uso não comercial** (o Vistas é CC BY-NC-SA 4.0).
- As zonas piloto, de afinação e de teste ficam fora do treino.

### Sinais: conjunto de ouro e categorias oficiais

Os sinais usam as categorias do Regulamento de Sinalização do Trânsito (perigo, cedência de passagem, proibição, obrigação, prescrição específica, informação, pré-sinalização, direção, confirmação, localidades, complementares, painel adicional, turístico-cultural, temporária e sinalização luminosa; STOP e limite de velocidade são subtipos).

```bash
python -m pipeline.ouro preparar --checkpoint data/avaliacao/<corrida>/deteccoes.jsonl --saida data/ouro_batchN
python -m pipeline.ouro servir --saida data/ouro_batchN          # página de revisão em http://127.0.0.1:8765
python -m pipeline.ouro avaliar --nome experiencia               # mede no conjunto de teste (data/ouro)
python -m training.datasets.ouro --pastas data/ouro_batch2 data/ouro_batch3 --saida data/datasets/b23
python -m training.datasets.sinais_web                           # imagens de referência (ecdinamica.pt, bomcondutor.pt)
python -m training.tipos_web --lotes data/ouro_batch3 --lotes-parciais data/ouro_batch2 --peso 0.6
python -m training.robustez --cabecas models/tipo_sinal.npz      # tipo certo em recortes desfocados, rodados, pequenos...
```

- `data/ouro` (200 imagens revistas à mão) é o conjunto de teste: nunca entra no treino. `avaliar --degradar desfocada|movimento|escura|jpeg|metade` mede com as fotos estragadas.
- `training.tipos_web` treina a cabeça do tipo com os recortes revistos e com os sinais de referência da web, estragados de propósito (desfocados, tapados, cortados, rodados, pequenos, escuros), e mistura-a com a cabeça antiga.
- `limiar_descarte` em `config/classes.yaml`: o CLIP só deita fora uma caixa com essa certeza; abaixo disso fica com o melhor tipo. As imagens da web são de terceiros (fontes em `data/datasets/sinais_web/FONTES.md`): uso não comercial.

## Avaliação

`python -m pipeline.evaluate` compara o catálogo exportado com uma referência (GeoJSON ou CSV com `lat`, `lon` e `classe`). Método e resultados em `docs/avaliacao.md`.

```bash
python -m pipeline.referencia --municipio config/municipio.yaml --saida data/avaliacao/referencia.geojson
python -m pipeline.bancada --fonte mapillary --municipio config/avaliacao/rossio.yaml --nome experiencia --referencia data/avaliacao/referencia_rossio.geojson
```

`pipeline.referencia` gera a referência a partir das map features do Mapillary (automática, não feita por pessoas, por isso a precisão aparece subestimada). `pipeline.bancada` corre um detetor sem tocar na base de dados e guarda as deteções em cache. Afinar limiares só nas zonas marcadas como afinação; medir na zona de teste uma única vez.

## Privacidade e atribuição

- A imagem original só existe em memória e em `data/raw/`. Só a versão anonimizada é gravada e servida.
- As imagens do Mapillary são CC BY-SA 4.0: autor, fonte, URL e licença ficam na tabela `imagem`, saem no GeoJSON em `atribuicao` e aparecem junto de cada imagem. O mapa base é do OpenStreetMap.

## Limitações conhecidas

- Sem autenticação: o nome do técnico é texto livre.
- Candeeiro contra poste de luz: só se distingue bem na zona onde a cabeça foi treinada; noutras zonas cerca de 8 a 11% dos postes de luz passam por candeeiro (números em `docs/avaliacao.md`). Candeeiros pequenos e longe, como os de um vídeo gravado do outro lado da estrada, não se distinguem. Papeleiras também são fracas (recall de 19%).
- A câmara, ou uma cena parecida com um poste, pode aparecer como luz: o detetor não os distingue e o técnico rejeita-os em Avaliar.
- Nos vídeos só se contam luzes a menos de 30 m da câmara (`alcance_max_m` em `config/classes.yaml`): as do outro lado de uma rua larga ficam de fora.
- A distância monocular usa só a altura típica da categoria; o Depth Anything não está integrado.
- O campo de visão das imagens em perspetiva é de 65° no lado maior da imagem (em `pipeline/geolocate/bearing.py`); a distância focal do EXIF não é lida.
- Elementos sem posição (fotografias sem GPS, vídeos sem GPX) não se juntam entre imagens: aparecem repetidos.
- O Mapillary limita cada pedido a 2000 imagens: com bbox grande, algumas podem ficar de fora. O KartaView não está implementado.
- A referência de avaliação é automática (Mapillary), não anotada por pessoas.
