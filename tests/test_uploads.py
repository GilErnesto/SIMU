from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from pipeline.errors import ErroPipeline
from pipeline.ingest import uploads
from pipeline.ingest.uploads import (
    Trilho,
    azimute,
    carregar,
    distancia_m,
    emparelhar,
    extrair_frames,
    ler_exif,
    ler_gpx,
    nome_original,
    tipo_de,
)


def _foto(caminho: Path, lat= 40.63, lon= -8.66, rumo= 90.0, data= "2026:05:01 10:00:00", largura= 64):
    imagem= Image.new("RGB", (largura, 32), (120, 120, 120))
    exif= Image.Exif()
    graus_lat= int(abs(lat))
    minutos_lat= (abs(lat) - graus_lat) * 60
    graus_lon= int(abs(lon))
    minutos_lon= (abs(lon) - graus_lon) * 60
    gps= {
        1: "N" if lat >= 0 else "S",
        2: (float(graus_lat), float(int(minutos_lat)), (minutos_lat - int(minutos_lat)) * 60),
        3: "E" if lon >= 0 else "W",
        4: (float(graus_lon), float(int(minutos_lon)), (minutos_lon - int(minutos_lon)) * 60),
    }
    if rumo is not None:
        gps[17]= rumo
    exif[0x8825]= gps
    if data:
        exif[0x8769]= {36867: data}
    imagem.save(caminho, exif=exif)
    return caminho


def _gpx(caminho: Path, pontos):
    linhas= "".join(
        f'<trkpt lat="{lat}" lon="{lon}"><time>{t}</time></trkpt>' for lat, lon, t in pontos
    )
    caminho.write_text(
        f'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>{linhas}</trkseg></trk></gpx>'
    )
    return caminho


def _video(caminho: Path, frames= 30, fps= 10):
    escritor= cv2.VideoWriter(str(caminho), cv2.VideoWriter_fourcc(*"MJPG"), fps, (64, 48))
    for i in range(frames):
        escritor.write(np.full((48, 64, 3), (i * 8) % 255, dtype=np.uint8))
    escritor.release()
    return caminho


def test_tipos_de_ficheiro():
    assert tipo_de("a.JPG") == "imagem"
    assert tipo_de("a.png") == "imagem"
    assert tipo_de("b.mp4") == "video"
    assert tipo_de("c.gpx") == "gpx"
    assert tipo_de("d.exe") is None
    assert nome_original(Path("0007_minha_foto.jpg")) == "minha_foto.jpg"


def test_distancia_e_azimute():
    assert distancia_m(40.0, -8.0, 40.001, -8.0) == pytest.approx(111.2, abs=0.5)
    assert azimute(40.0, -8.0, 40.001, -8.0) == pytest.approx(0, abs=0.01)
    assert azimute(40.0, -8.0, 40.0, -7.999) == pytest.approx(90, abs=0.1)
    assert azimute(40.0, -8.0, 39.999, -8.0) == pytest.approx(180, abs=0.01)


def test_exif_com_gps_rumo_e_data(tmp_path):
    info= ler_exif(_foto(tmp_path / "a.jpg", lat= 40.63, lon= -8.66, rumo= 123.0))
    assert info["lat"] == pytest.approx(40.63, abs=1e-4)
    assert info["lon"] == pytest.approx(-8.66, abs=1e-4)
    assert info["rumo"] == pytest.approx(123.0)
    assert info["data"] == datetime(2026, 5, 1, 10, 0, 0, tzinfo=UTC)
    assert info["esferica"] is False


def test_exif_sem_gps_nem_rumo(tmp_path):
    caminho= tmp_path / "b.jpg"
    Image.new("RGB", (32, 32)).save(caminho)
    info= ler_exif(caminho)
    assert info["lat"] is None and info["rumo"] is None and info["data"] is None


def test_exif_ficheiro_que_nao_e_imagem(tmp_path):
    caminho= tmp_path / "c.jpg"
    caminho.write_bytes(b"isto nao e uma imagem")
    assert ler_exif(caminho)["lat"] is None


def test_deteta_panorama_pelo_xmp(tmp_path):
    caminho= tmp_path / "p.jpg"
    caminho.write_bytes(b"\xff\xd8\xff" + b"<GPano:ProjectionType>equirectangular</GPano:ProjectionType>")
    assert uploads._e_esferica(caminho) is True


def test_gpx_ordena_e_interpola(tmp_path):
    caminho= _gpx(
        tmp_path / "t.gpx",
        [
            (40.0010, -8.0, "2026-05-01T10:00:10Z"),
            (40.0000, -8.0, "2026-05-01T10:00:00Z"),
            (40.0020, -8.0, "2026-05-01T10:00:20Z"),
        ],
    )
    pontos= ler_gpx(caminho)
    assert [p.lat for p in pontos] == [40.0, 40.001, 40.002]
    trilho= Trilho(pontos)
    lat, lon= trilho.posicao(trilho.inicio + 5)
    assert lat == pytest.approx(40.0005)
    assert lon == pytest.approx(-8.0)
    assert trilho.posicao(trilho.inicio - 1) is None
    assert trilho.posicao(trilho.inicio + 21) is None
    assert trilho.rumo(trilho.inicio + 10) == pytest.approx(0, abs=0.01)


def test_rumo_none_quando_parado(tmp_path):
    caminho= _gpx(
        tmp_path / "p.gpx",
        [(40.0, -8.0, "2026-05-01T10:00:00Z"), (40.0, -8.0, "2026-05-01T10:00:10Z")],
    )
    trilho= Trilho(ler_gpx(caminho))
    assert trilho.rumo(trilho.inicio + 5) is None


def test_gpx_invalido_ou_curto(tmp_path):
    estragado= tmp_path / "x.gpx"
    estragado.write_text("<gpx><trk>")
    with pytest.raises(ErroPipeline, match="GPX inválido"):
        ler_gpx(estragado)
    curto= _gpx(tmp_path / "y.gpx", [(40.0, -8.0, "2026-05-01T10:00:00Z")])
    with pytest.raises(ErroPipeline, match="menos de 2 pontos"):
        ler_gpx(curto)


def test_emparelha_por_nome_ou_pelo_unico_par():
    v1, v2= Path("0001_rua.mp4"), Path("0002_outra.mp4")
    g1= Path("0003_rua.gpx")
    pares= emparelhar([v1, v2], [g1])
    assert pares == {v1: g1, v2: None}
    assert emparelhar([Path("0001_a.mp4")], [Path("0002_b.gpx")]) == {Path("0001_a.mp4"): Path("0002_b.gpx")}


def test_extrai_frames_ao_ritmo_pedido(tmp_path):
    frames= extrair_frames(_video(tmp_path / "v.avi", frames= 30, fps= 10), 2.0, tmp_path / "frames")
    assert [round(t, 2) for t, _ in frames] == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    assert all(caminho.is_file() for _, caminho in frames)


def test_video_que_nao_abre(tmp_path):
    caminho= tmp_path / "x.mp4"
    caminho.write_bytes(b"nada")
    with pytest.raises(ErroPipeline, match="abrir o vídeo"):
        extrair_frames(caminho, 2.0, tmp_path / "frames")


def test_carregar_fotos_com_e_sem_gps_e_direcao_deduzida(tmp_path):
    _foto(tmp_path / "0001_a.jpg", lat= 40.6300, lon= -8.6600, rumo= None, data= "2026:05:01 10:00:00")
    _foto(tmp_path / "0002_b.jpg", lat= 40.6301, lon= -8.6600, rumo= 45.0, data= "2026:05:01 10:00:10")
    Image.new("RGB", (32, 32)).save(tmp_path / "0003_c.jpg")
    registos, avisos= carregar(tmp_path, "tk", {})
    assert [r.id_fonte for r in registos] == ["tk-00001", "tk-00002", "tk-00003"]
    assert registos[0].heading == pytest.approx(0, abs=0.5)
    assert registos[1].heading == pytest.approx(45.0)
    assert registos[0].fonte == "upload"
    assert registos[0].camera_type == "perspective"
    assert registos[0].localizavel
    assert registos[1].localizavel
    assert not registos[2].localizavel
    assert (registos[2].lon, registos[2].lat, registos[2].heading) == (None, None, None)
    aviso= next(a for a in avisos if "c.jpg" in a)
    assert "GPS indisponível" in aviso
    assert "foi analisada" in aviso
    assert len(avisos) == 1


def test_carregar_foto_unica_sem_direcao_e_analisada_sem_posicao(tmp_path):
    _foto(tmp_path / "0001_a.jpg", rumo= None)
    registos, avisos= carregar(tmp_path, "tk", {})
    assert len(registos) == 1
    assert registos[0].lat is not None
    assert registos[0].heading is None
    assert not registos[0].localizavel
    assert any("sem direção" in a and "sem posição" in a for a in avisos)


def test_carregar_so_fotos_sem_gps_nao_falha(tmp_path):
    Image.new("RGB", (32, 32)).save(tmp_path / "0001_a.jpg")
    Image.new("RGB", (32, 32)).save(tmp_path / "0002_b.jpg")
    registos, avisos= carregar(tmp_path, "tk", {})
    assert [r.id_fonte for r in registos] == ["tk-00001", "tk-00002"]
    assert len(avisos) == 2


def test_carregar_video_com_gpx(tmp_path):
    _video(tmp_path / "0001_rua.avi", frames= 30, fps= 10)
    _gpx(
        tmp_path / "0002_rua.gpx",
        [(40.0000, -8.0, "2026-05-01T10:00:00Z"), (40.0010, -8.0, "2026-05-01T10:00:03Z")],
    )
    registos, avisos= carregar(tmp_path, "tk", {"fps": 2.0, "offset_s": 0})
    assert len(registos) == 6
    assert all(r.fonte == "video" and r.camera_type == "perspective" for r in registos)
    assert registos[0].lat == pytest.approx(40.0, abs=1e-5)
    assert registos[-1].lat > registos[0].lat
    assert all(r.heading == pytest.approx(0, abs=0.5) for r in registos)
    assert any("início do vídeo" in a for a in avisos)


def test_carregar_video_sem_gpx(tmp_path):
    _video(tmp_path / "0001_rua.avi")
    registos, avisos= carregar(tmp_path, "tk", {})
    assert registos == []
    assert any("sem GPX" in a for a in avisos)


def test_deslocamento_fora_do_trilho_avisa(tmp_path):
    _video(tmp_path / "0001_rua.avi", frames= 30, fps= 10)
    _gpx(
        tmp_path / "0002_rua.gpx",
        [(40.0000, -8.0, "2026-05-01T10:00:00Z"), (40.0010, -8.0, "2026-05-01T10:00:03Z")],
    )
    registos, avisos= carregar(tmp_path, "tk", {"offset_s": 600})
    assert registos == []
    assert any("nenhum frame coincide" in a for a in avisos)


def test_ler_ficheiro_reduz_imagens_grandes(tmp_path):
    caminho= tmp_path / "g.jpg"
    cv2.imwrite(str(caminho), np.zeros((1000, 4000, 3), dtype=np.uint8))
    from pipeline.models import ImageRecord

    registo= ImageRecord("upload", "x", "a", "l", "", None, 0, 0, 0, "perspective", str(caminho))
    imagem= uploads.ler_ficheiro(registo)
    assert max(imagem.shape[:2]) == uploads.LADO_MAXIMO


def test_ler_ficheiro_inexistente(tmp_path):
    from pipeline.models import ImageRecord

    registo= ImageRecord("upload", "x", "a", "l", "", None, 0, 0, 0, "perspective", str(tmp_path / "nao.jpg"))
    with pytest.raises(ErroPipeline, match="ler a imagem"):
        uploads.ler_ficheiro(registo)
