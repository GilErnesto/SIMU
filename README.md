# Ctrl + F Aveiro

Deteta mobiliário urbano (sinais de trânsito, candeeiros, ecopontos) em imagens de rua, calcula a posição de cada elemento, guarda-o num catálogo PostGIS, mostra-o num mapa para revisão por um técnico e exporta em GeoJSON e CSV. Projeto do ATC Hackathon 2026, desafio 2 (Câmara Municipal de Aveiro e Universidade de Aveiro).

Estado: pipeline (ingest, anonimização, deteção, geolocalização, catálogo), API FastAPI, interface React com mapa, preparação de dados e treino de um YOLO próprio (`training/`) e avaliação contra uma referência do Mapillary. O tipo de sinal ainda é o ponto fraco (ver `docs/avaliacao.md`).

## Arranque

Requisitos: Python 3.11 ou superior, Node 20 ou superior, Docker.

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,api,ml]"
docker compose up -d db
```

Preencher em `.env` o `MAPILLARY_TOKEN` e a palavra-passe da base de dados (a mesma em `POSTGRES_PASSWORD` e `DATABASE_URL`). O token é um Client Token da aplicação registada em `mapillary.com/dashboard/developers`, só com leitura de dados públicos.

## Configuração

- `config/municipio.yaml`: nome, bbox (lon/lat) e CRS métrico. A bbox atual é provisória, a substituir pela da zona piloto.
- `config/classes.yaml`: taxonomia, nomes mostrados na interface, raio de deduplicação, altura típica (distância monocular), superclasse de recurso dos sinais e texto de pesquisa do detetor zero-shot.

O código não contém nada específico de um município.

## Correr o pipeline

```bash
python -m pipeline.run --municipio config/municipio.yaml --fonte mapillary
```

Imagens já registadas na base de dados são ignoradas. Um elemento novo a menos do raio de deduplicação de outro da mesma classe junta-se a ele.

Modelos necessários, em `models/` (não versionada):

- `models/egoblur/ego_blur_face.jit` e `models/egoblur/ego_blur_lp.jit`: EgoBlur (rostos e matrículas), pedidos à Meta através do formulário do projeto. Sem eles o pipeline termina com erro e não grava nenhuma imagem.
- Detetor, à escolha com `--detetor`:
  - `owlv2` (por omissão): OWLv2 zero-shot, local e Apache 2.0. Descarrega o modelo do Hugging Face na primeira utilização e usa a GPU se existir. `--limiar` define a confiança mínima (0,2 por omissão). Não deteta sinais tapados: nunca marca `obstruido`.
    Funciona em duas fases: o OWLv2 encontra só os três grandes (sinal, candeeiro, contentor de lixo) e o CLIP classifica o tipo no recorte (por exemplo, Stop, cedência, subterrâneo), descartando coisas parecidas (portas, números de porta, letreiros). `--sem-refinar` desliga a segunda fase e `--limiar-classe` define a confiança mínima do tipo. O tipo de cada elemento sai da votação de todas as imagens que o veem.
  - `yolo`: pesos próprios em `models/detetor.pt` (`--pesos`), treinados como descrito em "Treino do detetor". Também passa pela segunda fase (CLIP), salvo com `--sem-refinar`.
  - `limiar_detecao` em `config/classes.yaml` descarta deteções abaixo dessa confiança, por categoria.

## Tudo de uma vez com Docker

```bash
cp .env.example .env
docker compose up -d --build
```

Antes, cria as pastas com o teu utilizador: `mkdir -p models data/anon data/raw`.

Arranca a base de dados, a API, a interface (SIMU) e o worker que analisa os envios. Abre `http://localhost:8080`. A API fica em `http://localhost:8010` (documentação em `/docs`). As portas mudam-se com `FRONTEND_PORT`, `BACKEND_PORT` e `POSTGRES_PORT` no `.env`. Tudo escuta só em `127.0.0.1`.

- A API lê `./config` (só de leitura) e serve imagens de `./data/anon`, onde só escreve para apagar as fotografias de uma análise quando o botão da lixeira a apaga. Cria `data/anon` antes (`mkdir -p data/anon`): se não existir, o `docker compose up` falha em vez de a criar como `root`, o que impediria o pipeline de escrever nela.
- `data/anon` é uma cache das imagens anonimizadas que o catálogo mostra. Se a apagares por engano, `python -m pipeline.run --municipio config/municipio.yaml --regenerar-imagens` volta a criar as que faltam, sem alterar a base.
- A interface recebe as fotografias, os vídeos e o GPX, e quem os analisa é o **worker**, que arranca com o resto. Precisa dos modelos em `./models` (EgoBlur em `models/egoblur/`, e `detetor.pt` e `tipo_sinal.npz` se existirem; sem `detetor.pt` usa o OWLv2). Cada análise tem um endereço próprio, `http://localhost:8080/a/<código>`. Enquanto o worker não estiver a correr, as análises ficam "Na fila", e a interface avisa quando isso demora.
- **Por omissão, o worker do Docker usa o CPU.** Medi cerca de 15 a 30 segundos por imagem de 2048 px com 4 núcleos, quase tudo na anonimização: serve para umas poucas fotografias, não para centenas. Dar mais núcleos não ajuda (8 threads dão o mesmo tempo que 4). `WORKER_CPUS` e `WORKER_MEM` no `.env` limitam o que ele usa.
- **Com GPU NVIDIA**, arranca com `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build`. Precisa do `nvidia-container-toolkit` com CDI (`nvidia-ctk cdi list` deve mostrar `nvidia.com/gpu=all`); a imagem passa a ter o PyTorch com CUDA (cerca de 11 GB). Medi cerca de 0,5 a 0,6 s por imagem de ponta a ponta (0,35 s só no EgoBlur e no YOLO; 20 a 30 imagens de 2048 px, RTX 4060 laptop; um panorama demora cerca de 0,75 s por ter 6 vistas): na GPU a anonimização corre em meia precisão, com o limiar de rostos e matrículas 0,05 mais baixo para compensar a diferença numérica, ou seja, desfoca um pouco mais e nunca menos. Em alternativa, corre o worker no teu ambiente, com `python -m pipeline.worker` (precisa de `pip install -e ".[ml]"`), e pára o do Docker com `docker compose stop worker`.
- A primeira análise descarrega o CLIP (1,7 GB) para a cache do Hugging Face. Define `HF_CACHE` no `.env` com o caminho da cache que já tens (`~/.cache/huggingface`) para o reutilizar.
- Os ficheiros enviados ficam em `data/raw/<código>/` (nunca servida pela API) só até a análise acabar bem; depois são apagados. Em caso de falha ficam, para se poder tentar de novo. Só a versão anonimizada vai para `data/anon/`.
- As fotografias devem ter GPS e, de preferência, direção no EXIF. Se faltar a direção, deduz-se a partir das fotografias vizinhas. **Sem GPS (ou sem direção que se consiga deduzir), a fotografia é analisada na mesma**: os elementos aparecem na lista, com o aviso "GPS indisponível", mas sem posição no mapa. O técnico pode indicar a posição de cada um ao avaliá-lo. Cada vídeo precisa de um GPX gravado ao mesmo tempo, com o mesmo nome ou como único par; o início do vídeo é assumido igual ao início do GPX, com um desfasamento opcional.
- O pipeline do Mapillary (`python -m pipeline.run ...`) continua a existir e aparece como uma análise própria, uma por zona.
- Para parar: `docker compose down`. Os dados ficam no volume `pgdata`; `docker compose down -v` apaga-os.
- A palavra-passe da base entra num URL: evita caracteres como `@`, `/` e `:`.

## API e interface

```bash
uvicorn backend.main:app --reload
cd frontend && npm install && npm run dev
```

A interface fica em `http://localhost:5173` e fala com a API através do prefixo `/api`. Se a API não estiver na porta 8000, usar `API_URL=http://localhost:PORTA npm run dev`.

A API lê `DATABASE_URL` do `.env`. Variáveis opcionais: `MUNICIPIO_YAML` (por omissão `config/municipio.yaml`) e `ANON_DIR` (por omissão `data/anon`).

- `GET /elementos?bbox=&categoria=&estado=`: GeoJSON.
- `GET /elementos/{id}`: elemento com observações, imagens e atribuição.
- `PATCH /elementos/{id}`: corrige classe, posição ou estado. Cada alteração fica em `correcao`. Nunca se apaga um elemento.
- `GET /export.geojson` e `GET /export.csv`: catálogo completo, com filtro opcional `?estado=`.
- `GET /imagens/{id}`: só serve ficheiros de `ANON_DIR`.

Na interface o técnico indica o nome no campo Técnico, escolhe um elemento no mapa ou na lista, e valida, rejeita ou corrige a classe e a posição (por coordenadas ou clicando no mapa).

## Testes

```bash
pytest
TEST_DATABASE_URL=postgresql+psycopg://utilizador:palavra-passe@localhost:5432/base_de_testes pytest
```

Os testes de catálogo e API só correm com `TEST_DATABASE_URL`. Esta base tem de ser descartável e vazia: os testes assumem que não há dados.

## Treino do detetor

Os três grandes (sinal, semáforo, candeeiro, contentor) treinam-se com o Open Images e o Mapillary Vistas v2.0:

```bash
python -m training.datasets.openimages
python -m training.datasets.vistas --origem datasets/mtsd_raw/<pasta mtsd_v2_fully_annotated>
python -m training.train --config training/configs/grandes.yaml
```

- O Open Images traz imagens CC BY 2.0 e o Vistas é CC BY-NC-SA 4.0: **os pesos resultantes só servem para uso não comercial**. O autor e a licença de cada imagem ficam em `atribuicao.csv`, na pasta de cada dataset.
- Todas as imagens passam pelo EgoBlur antes de serem gravadas em `data/datasets/`. Nada disto vai para o git.
- O Vistas tem polígonos por objeto, sem o tipo do sinal. Junta-se cada luminária ao poste que a segura, para a caixa servir à estimativa de distância.
- Para o tipo de sinal (Stop, cedência, proibição...) o ideal é o MTSD verdadeiro (`mapillary.com/dataset/trafficsign`, com conta): `python -m training.datasets.mtsd --origem <pasta>` e `training/configs/sinais.yaml`.

### Tipo de sinal com as deteções do Mapillary

Sem o MTSD, o tipo aprende-se com as deteções por imagem da API do Mapillary, que trazem o tipo de cada sinal:

```bash
python -m training.datasets.tipos_mapillary --zona config/treino/aveiro_tipos.yaml --excluir config/municipio.yaml config/avaliacao/rossio.yaml config/avaliacao/lourenco_peixinho.yaml
python -m training.tipos recortar
python -m training.tipos treinar
```

- Deixa de fora as zonas piloto, de afinação e de teste, para a avaliação não ver imagens do treino.
- Os originais ficam em `data/raw/tipos_mapillary/` só até serem anonimizados e recortados, e depois são apagados.
- `treinar` ajusta uma regressão logística sobre as características de imagem do CLIP, compara-a com o CLIP zero-shot no mesmo conjunto de validação (`data/datasets/tipos/relatorio.json`) e grava `models/tipo_sinal.npz`.
- Se esse ficheiro existir, o pipeline usa-o para escolher o tipo (`--cabeca-sinal`); o CLIP zero-shot continua a descartar o que não é sinal. As etiquetas vêm de um modelo do Mapillary, por isso têm ruído. Imagens CC BY-SA 4.0.

## Avaliação

`python -m pipeline.evaluate` compara o catálogo exportado com uma referência. Método e resultados em `docs/avaliacao.md`.

```bash
python -m pipeline.referencia --municipio config/municipio.yaml --saida data/avaliacao/referencia.geojson
python -m pipeline.bancada --fonte mapillary --municipio config/avaliacao/rossio.yaml --nome experiencia --referencia data/avaliacao/referencia_rossio.geojson
```

- `pipeline.referencia` gera a referência a partir das map features do Mapillary. A tua referência anotada à mão pode ser um GeoJSON ou um CSV com as colunas `lat`, `lon` e `classe` (ou `categoria`).
- `pipeline.bancada` corre um detetor sobre uma zona sem tocar na base de dados e avalia-o, com `--nivel categoria` ou `classe`. Guarda as deteções em cache para repetir a avaliação sem voltar a detetar.
- Afinar limiares só nas zonas em `config/avaliacao/` marcadas como afinação, e medir na de teste uma única vez.

## Privacidade

A imagem original só existe em memória. Só a versão anonimizada (rostos e matrículas desfocados) é gravada, em `data/anon/`, e é a única que a API serve.

## Atribuição

As imagens do Mapillary são CC BY-SA 4.0. O autor, a fonte, o URL de origem e a licença ficam na tabela `imagem`, saem no GeoJSON em `atribuicao` e aparecem junto de cada imagem na interface. O mapa base é do OpenStreetMap.

## Limitações conhecidas

- A interface não tem autenticação: o nome do técnico é texto livre.
- O tipo de sinal é fraco: o CLIP zero-shot acerta o tipo em cerca de 19% a 28% dos sinais encontrados (`docs/avaliacao.md`). A referência é automática (Mapillary), não anotada por pessoas.
- Dois raios de objetos diferentes da mesma classe podem gerar um ponto falso por triangulação.
- Deteções sem posição possível (raios paralelos e objeto demasiado longe para a estimativa monocular) não entram no catálogo.
- Distância monocular só por altura conhecida. Depth Anything ainda não está integrado.
- O campo de visão de imagens em perspetiva é fixo (65 graus) em `pipeline/geolocate/bearing.py`.
- O Mapillary limita cada pedido a 2000 imagens: com bbox grande, algumas podem ficar de fora.
- O KartaView e o vídeo não estão implementados.
