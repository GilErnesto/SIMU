# Ctrl + F Aveiro

Deteta mobiliário urbano (sinais de trânsito, candeeiros, ecopontos) em imagens de rua, calcula a posição de cada elemento, guarda-o num catálogo PostGIS, mostra-o num mapa para revisão por um técnico e exporta em GeoJSON e CSV. Projeto do ATC Hackathon 2026, desafio 2 (Câmara Municipal de Aveiro e Universidade de Aveiro).

Estado: pipeline (ingest, anonimização, deteção, geolocalização, catálogo), API FastAPI e interface React com mapa. Falta `training/` (treino de um YOLO próprio) e avaliar com dados reais.

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
  - `yolo`: pesos próprios em `models/detetor.pt` (`--pesos`). Treino ainda por fazer.

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

## Avaliação

`python -m pipeline.evaluate` compara o catálogo exportado com uma referência anotada à mão. Método e resultados em `docs/avaliacao.md`.

## Privacidade

A imagem original só existe em memória. Só a versão anonimizada (rostos e matrículas desfocados) é gravada, em `data/anon/`, e é a única que a API serve.

## Atribuição

As imagens do Mapillary são CC BY-SA 4.0. O autor, a fonte, o URL de origem e a licença ficam na tabela `imagem`, saem no GeoJSON em `atribuicao` e aparecem junto de cada imagem na interface. O mapa base é do OpenStreetMap.

## Limitações conhecidas

- A interface não tem autenticação: o nome do técnico é texto livre.
- O OWLv2 zero-shot não foi avaliado em imagens de rua reais. A qualidade das deteções por classe é desconhecida.
- Dois raios de objetos diferentes da mesma classe podem gerar um ponto falso por triangulação.
- Deteções sem posição possível (raios paralelos e objeto demasiado longe para a estimativa monocular) não entram no catálogo.
- Distância monocular só por altura conhecida. Depth Anything ainda não está integrado.
- O campo de visão de imagens em perspetiva é fixo (65 graus) em `pipeline/geolocate/bearing.py`.
- O Mapillary limita cada pedido a 2000 imagens: com bbox grande, algumas podem ficar de fora.
- O KartaView e o vídeo não estão implementados.
