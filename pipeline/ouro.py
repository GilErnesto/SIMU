"""Gold set: images reviewed by hand to measure the detector.

`preparar` picks test-zone images, runs the current detector and stores its boxes as proposals.
`servir` opens a local page where the reviewer only fixes what is wrong. Only traffic signs and
traffic lights are proposed by default (`--categorias`).
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import cv2

from pipeline import checkpoint
from pipeline.config import Classes, load_classes
from pipeline.detect.panorama import views
from pipeline.errors import ErroPipeline

PASTA= Path("data/ouro")
CATEGORIAS= ("sinal",)
FICHEIRO= "ouro.json"
LIMIAR_PROPOSTA= 0.15
LIMIAR_ACEITE= 0.3
VISTAS_POR_PANORAMA= 2
PAGINA= Path(__file__).with_name("ouro.html")


def _hash(texto: str, semente: int) -> str:
    return hashlib.sha1(f"{semente}:{texto}".encode()).hexdigest()


def escolher(ids: list[str], quantos: int, semente: int) -> list[str]:
    """Amostra estável: as imagens com menor hash, para repetir a escolha em corridas diferentes."""
    return sorted(sorted(ids), key=lambda i: _hash(i, semente))[:quantos]


def _proposta(detecao, classes: Classes) -> dict:
    estado= "por_rever" if detecao.confidence >= LIMIAR_ACEITE else "rejeitado"
    return {
        "caixa": [round(v, 1) for v in detecao.bbox_xyxy],
        "categoria": detecao.category,
        "classe": detecao.class_name,
        "classe_modelo": detecao.class_name,
        "confianca": round(detecao.confidence, 3),
        "origem": "modelo",
        "estado": estado,
    }


LADO_LADRILHO= 1024
PASSO_LADRILHO= 768
MINIMO_PARA_LADRILHAR= 1300


def _inicios(total: int, lado: int, passo: int) -> list[int]:
    if total <= lado:
        return [0]
    return [*range(0, total - lado, passo), total - lado]


def detetar_com_ladrilhos(detetor, nome: str, imagem) -> list:
    """Whole image plus overlapping native-resolution tiles, merged.

    The detector was trained at about 1024 px, so on a 2048 px photo small signs end up tiny.
    Tiles keep them at full size; duplicates between tiles and the whole image are merged.
    """
    from pipeline.detect.panorama import nms
    from pipeline.models import Detection

    altura, largura= imagem.shape[:2]
    deteccoes= list(detetor.detect(nome, imagem))
    if max(altura, largura) < MINIMO_PARA_LADRILHAR:
        return deteccoes
    for y in _inicios(altura, LADO_LADRILHO, PASSO_LADRILHO):
        for x in _inicios(largura, LADO_LADRILHO, PASSO_LADRILHO):
            for d in detetor.detect(nome, imagem[y : y + LADO_LADRILHO, x : x + LADO_LADRILHO]):
                x1, y1, x2, y2= d.bbox_xyxy
                caixa= (x1 + x, y1 + y, x2 + x, y2 + y)
                deteccoes.append(
                    Detection(nome, d.category, d.class_name, caixa, d.confidence, d.obstruido)
                )
    return nms(deteccoes, 10**9)


def _guardar_atomico(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=caminho.parent, suffix=".tmp", delete=False
    ) as ficheiro:
        json.dump(dados, ficheiro, ensure_ascii=False)
    os.replace(ficheiro.name, caminho)


def preparar(args: argparse.Namespace) -> int:
    from pipeline.run import _detetor

    saida= Path(args.saida)
    destino= saida / FICHEIRO
    if destino.exists() and not args.refazer:
        raise ErroPipeline(
            f"{destino} already exists and may hold reviews. Use --refazer to replace it."
        )
    classes= load_classes(Path(args.classes))
    registos= checkpoint.load(Path(args.checkpoint))
    pasta_imagens= Path(args.imagens)
    disponiveis= {
        id_fonte: registo
        for id_fonte, (registo, _) in registos.items()
        if (pasta_imagens / f"{registo.fonte}_{id_fonte}.jpg").is_file()
    }
    planos= [i for i, r in disponiveis.items() if r.camera_type != "spherical"]
    panoramas= [i for i, r in disponiveis.items() if r.camera_type == "spherical"]
    escolhidas= escolher(planos, args.n_perspetiva, args.semente) + escolher(
        panoramas, args.n_panoramas, args.semente
    )
    if not escolhidas:
        raise ErroPipeline("No images available: check --checkpoint and --imagens")
    detetor= _detetor(
        Namespace(
            detetor="auto",
            pesos=args.pesos,
            limiar=LIMIAR_PROPOSTA,
            sem_refinar=False,
            limiar_classe=0.3,
            cabeca_sinal=args.cabeca_sinal,
        ),
        classes,
        limiares=False,
    )
    (saida / "imagens").mkdir(parents=True, exist_ok=True)
    telas= {}
    for n, id_fonte in enumerate(escolhidas, 1):
        registo= disponiveis[id_fonte]
        origem= pasta_imagens / f"{registo.fonte}_{id_fonte}.jpg"
        imagem= cv2.imread(str(origem))
        if imagem is None:
            continue
        candidatas= []
        if registo.camera_type == "spherical":
            for yaw, vista in views(imagem):
                candidatas.append((f"{id_fonte}_v{int(yaw):03d}", vista, "vista", yaw))
        else:
            candidatas.append((id_fonte, imagem, "perspetiva", None))
        feitas= []
        for nome, tela, tipo, yaw in candidatas:
            if tipo == "perspetiva" and not args.sem_ladrilhos:
                encontradas= detetar_com_ladrilhos(detetor, nome, tela)
            else:
                encontradas= detetor.detect(nome, tela)
            deteccoes= [
                d
                for d in encontradas
                if d.confidence >= LIMIAR_PROPOSTA and d.category in args.categorias
            ]
            feitas.append((nome, tela, tipo, yaw, deteccoes))
        if registo.camera_type == "spherical":
            feitas.sort(
                key=lambda f: sum(d.confidence >= LIMIAR_ACEITE for d in f[4]), reverse=True
            )
            feitas= feitas[:VISTAS_POR_PANORAMA]
        for nome, tela, tipo, yaw, deteccoes in feitas:
            ficheiro= f"{nome}.jpg"
            if tipo == "perspetiva":
                shutil.copyfile(origem, saida / "imagens" / ficheiro)
            else:
                cv2.imwrite(str(saida / "imagens" / ficheiro), tela, [cv2.IMWRITE_JPEG_QUALITY, 92])
            altura, largura= tela.shape[:2]
            telas[nome]= {
                "imagem": ficheiro,
                "id_fonte": id_fonte,
                "tipo": tipo,
                "yaw": yaw,
                "largura": largura,
                "altura": altura,
                "revista": False,
                "caixas": [
                    _proposta(d, classes)
                    for d in sorted(deteccoes, key=lambda d: d.confidence, reverse=True)
                ],
            }
        if n % 10 == 0:
            print(f"[{n}/{len(escolhidas)}] images prepared", file=sys.stderr, flush=True)
    _guardar_atomico(destino, {"versao": 1, "categorias": list(args.categorias), "telas": telas})
    caixas= sum(len(t["caixas"]) for t in telas.values())
    print(f"{len(telas)} images to review, {caixas} proposed boxes in {destino}")
    return 0


def _estado_servido(classes: Classes, dados: dict) -> dict:
    return {
        "categorias": {
            nome: {
                "rotulo": cat.rotulo,
                "classes": [{"id": c, "rotulo": cat.rotulos.get(c, c)} for c in cat.classes],
            }
            for nome, cat in classes.categorias.items()
            if nome in dados.get("categorias", CATEGORIAS)
        },
        "telas": dados["telas"],
    }


def _validar_tela(corpo: dict, atual: dict) -> dict:
    caixas= []
    for caixa in corpo.get("caixas", []):
        x1, y1, x2, y2= (float(v) for v in caixa["caixa"])
        if not (0 <= x1 < x2 <= atual["largura"] and 0 <= y1 < y2 <= atual["altura"]):
            raise ValueError("box outside the image")
        if caixa["estado"] not in ("por_rever", "aceite", "rejeitado", "corrigido"):
            raise ValueError("invalid state")
        caixas.append(
            {
                "caixa": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                "categoria": str(caixa["categoria"]),
                "classe": str(caixa["classe"]),
                "classe_modelo": caixa.get("classe_modelo"),
                "confianca": caixa.get("confianca"),
                "origem": "manual" if caixa.get("origem") == "manual" else "modelo",
                "estado": caixa["estado"],
            }
        )
    return {**atual, "revista": bool(corpo.get("revista")), "caixas": caixas}


def servir(args: argparse.Namespace) -> int:
    saida= Path(args.saida)
    caminho= saida / FICHEIRO
    if not caminho.exists():
        raise ErroPipeline(f"{caminho} does not exist. Run first: python -m pipeline.ouro preparar ...")
    classes= load_classes(Path(args.classes))
    dados= json.loads(caminho.read_text(encoding="utf-8"))
    trinco= threading.Lock()
    imagens= (saida / "imagens").resolve()

    class Pedido(BaseHTTPRequestHandler):
        def log_message(self, *_):
            return

        def _responder(self, codigo: int, tipo: str, corpo: bytes) -> None:
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _json(self, codigo: int, objeto) -> None:
            corpo= json.dumps(objeto, ensure_ascii=False).encode()
            self._responder(codigo, "application/json; charset=utf-8", corpo)

        def do_GET(self):
            caminho_url= unquote(urlparse(self.path).path)
            if caminho_url == "/":
                self._responder(200, "text/html; charset=utf-8", PAGINA.read_bytes())
            elif caminho_url == "/api/estado":
                with trinco:
                    self._json(200, _estado_servido(classes, dados))
            elif caminho_url.startswith("/imagem/"):
                ficheiro= (imagens / caminho_url.removeprefix("/imagem/")).resolve()
                if ficheiro.parent != imagens or not ficheiro.is_file():
                    self._responder(404, "text/plain", b"not found")
                    return
                self._responder(200, "image/jpeg", ficheiro.read_bytes())
            else:
                self._responder(404, "text/plain", b"not found")

        def do_POST(self):
            caminho_url= unquote(urlparse(self.path).path)
            if not caminho_url.startswith("/api/tela/"):
                self._responder(404, "text/plain", b"not found")
                return
            nome= caminho_url.removeprefix("/api/tela/")
            try:
                tamanho= int(self.headers.get("Content-Length", "0"))
                corpo= json.loads(self.rfile.read(tamanho))
                with trinco:
                    if nome not in dados["telas"]:
                        self._json(404, {"detail": "unknown image"})
                        return
                    dados["telas"][nome]= _validar_tela(corpo, dados["telas"][nome])
                    _guardar_atomico(caminho, dados)
                self._json(200, {"ok": True})
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as erro:
                self._json(422, {"detail": str(erro)})

    servidor= ThreadingHTTPServer(("127.0.0.1", args.porta), Pedido)
    revistas= sum(t["revista"] for t in dados["telas"].values())
    print(f"{revistas}/{len(dados['telas'])} images reviewed. Open http://127.0.0.1:{args.porta}")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("Server stopped.")
    return 0


def main(argv: list[str] | None= None) -> int:
    parser= argparse.ArgumentParser(prog="python -m pipeline.ouro")
    sub= parser.add_subparsers(dest="comando", required=True)
    prep= sub.add_parser("preparar", help="pick images and propose boxes")
    prep.add_argument("--checkpoint", required=True, help="deteccoes.jsonl from a bancada run")
    prep.add_argument("--imagens", default="data/avaliacao/imagens", help="anonymised images")
    prep.add_argument("--saida", default=str(PASTA))
    prep.add_argument("--classes", default="config/classes.yaml")
    prep.add_argument("--pesos", default="models/detetor.pt")
    prep.add_argument("--cabeca-sinal", default="models/tipo_sinal.npz")
    prep.add_argument("--n-perspetiva", type=int, default=80)
    prep.add_argument("--n-panoramas", type=int, default=40)
    prep.add_argument("--semente", type=int, default=0)
    prep.add_argument("--categorias", nargs="+", default=list(CATEGORIAS), help="categories to propose")
    prep.add_argument("--refazer", action="store_true", help="replace an existing ouro.json")
    prep.add_argument(
        "--sem-ladrilhos", action="store_true", help="do not tile large photos when proposing boxes"
    )
    serv= sub.add_parser("servir", help="local review page")
    serv.add_argument("--saida", default=str(PASTA))
    serv.add_argument("--classes", default="config/classes.yaml")
    serv.add_argument("--porta", type=int, default=8765)
    aval= sub.add_parser("avaliar", help="score a detector on the reviewed images")
    aval.add_argument("--nome", required=True, help="name of this run (used in the output files)")
    aval.add_argument("--saida", default=str(PASTA))
    aval.add_argument("--classes", default="config/classes.yaml")
    aval.add_argument("--detetor", choices=("auto", "owlv2", "yolo"), default="auto")
    aval.add_argument("--pesos", default="models/detetor.pt")
    aval.add_argument("--cabeca-sinal", default="models/tipo_sinal.npz")
    aval.add_argument("--sem-refinar", action="store_true")
    aval.add_argument("--refazer", action="store_true", help="run the detector again")
    args= parser.parse_args(argv)
    try:
        if args.comando == "avaliar":
            from pipeline.ouro_avaliar import avaliar

            return avaliar(args)
        return preparar(args) if args.comando == "preparar" else servir(args)
    except ErroPipeline as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
