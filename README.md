# Ctrl + F Aveiro

Deteta mobiliário urbano (sinais de trânsito, candeeiros, ecopontos) em imagens de rua, calcula a posição de cada elemento, guarda-o num catálogo PostGIS e exporta em GeoJSON e CSV. Projeto do ATC Hackathon 2026, desafio 2 (Câmara Municipal de Aveiro e Universidade de Aveiro).

Estado: pipeline mínimo (ingest, anonimização, deteção, geolocalização, catálogo). Faltam `backend/`, `frontend/` e `training/`.

## Arranque

Requisitos: Python 3.11 ou superior, Docker.

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ml]"
docker compose up -d db
pytest
```

Preencher em `.env` o `MAPILLARY_TOKEN` e a palavra-passe da base de dados (a mesma em `POSTGRES_PASSWORD` e `DATABASE_URL`).

## Configuração

- `config/municipio.yaml`: nome, bbox (lon/lat) e CRS métrico. A bbox atual é provisória, a substituir pela da zona piloto.
- `config/classes.yaml`: taxonomia, raio de deduplicação, altura típica (usada na distância monocular) e superclasse de recurso dos sinais.

O código não contém nada específico de um município.

## Modelos necessários

Ficam em `models/`, que não é versionada.

- `models/detetor.pt`: pesos YOLO treinados com as classes de `config/classes.yaml`.
- `models/egoblur/ego_blur_face.jit` e `models/egoblur/ego_blur_lp.jit`: modelos EgoBlur (rostos e matrículas). São pedidos à Meta através do formulário do projeto EgoBlur.

Sem estes ficheiros o pipeline termina com uma mensagem de erro e não grava nenhuma imagem.

## Correr

```bash
python -m pipeline.run --municipio config/municipio.yaml --fonte mapillary
```

Imagens já registadas na base de dados são ignoradas. Um elemento novo a menos do raio de deduplicação de outro da mesma classe junta-se a ele.

Exportação: `pipeline.catalog.export.to_geojson(sessao)` e `to_csv(sessao)`.

## Privacidade

A imagem original só existe em memória. Só a versão anonimizada (rostos e matrículas desfocados) é gravada, em `data/anon/`.

## Atribuição

As imagens do Mapillary são CC BY-SA 4.0. O autor, a fonte, o URL de origem e a licença ficam na tabela `imagem` e saem no GeoJSON, em `atribuicao`.

## Limitações conhecidas

- Dois raios de objetos diferentes da mesma classe podem gerar um ponto falso por triangulação.
- Deteções sem posição possível (raios paralelos e objeto demasiado longe para a estimativa monocular) não entram no catálogo.
- Distância monocular só por altura conhecida. Depth Anything ainda não está integrado.
- O campo de visão de imagens em perspetiva é fixo (65 graus) em `pipeline/geolocate/bearing.py`.
- O KartaView e o vídeo não estão implementados.
