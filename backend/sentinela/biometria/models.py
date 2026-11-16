"""Pesos oficiais fixados por revisão e SHA-256; nenhum download durante inferência."""

import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path

REVISION = "48b10fa505aeb51fbd127fc60a5c660040e823b7"
MODEL_ID = "sface-2021dec:0ba9fbfa01b5270c"
DEFAULT_MODELS = Path(__file__).resolve().parents[3] / "models"
MODELS = {
    "yunet": {
        "directory": "face_detection_yunet",
        "file": "face_detection_yunet_2023mar.onnx",
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "size": 232589,
    },
    "sface": {
        "directory": "face_recognition_sface",
        "file": "face_recognition_sface_2021dec.onnx",
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "size": 38696353,
    },
}


def calcular_sha256(caminho: Path) -> str:
    resumo_hash = hashlib.sha256()
    with caminho.open("rb") as origem_dados:
        for bloco in iter(lambda: origem_dados.read(1024 * 1024), b""):
            resumo_hash.update(bloco)
    return resumo_hash.hexdigest()


def validar_modelos(diretorio: Path) -> dict[str, Path]:
    caminhos = {}
    for nome, especificacao in MODELS.items():
        caminho = diretorio / especificacao["file"]
        if not caminho.is_file():
            raise ValueError("Modelo ausente. Execute: sentinela download-models")
        if (
            caminho.stat().st_size != especificacao["size"]
            or calcular_sha256(caminho) != especificacao["sha256"]
        ):
            raise ValueError(f"Checksum inválido para o modelo {nome}.")
        caminhos[nome] = caminho
    return caminhos


def baixar_modelos(diretorio: Path) -> None:
    diretorio.mkdir(parents=True, exist_ok=True)
    for nome, especificacao in MODELS.items():
        destino = diretorio / especificacao["file"]
        if destino.exists() and calcular_sha256(destino) == especificacao["sha256"]:
            continue
        url = (
            f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{REVISION}"
            f"/models/{especificacao['directory']}/{especificacao['file']}"
        )
        temporario = None
        try:
            with tempfile.NamedTemporaryFile(dir=diretorio, delete=False) as saida:
                temporario = Path(saida.name)
                with urllib.request.urlopen(url, timeout=60) as resposta:
                    restante = especificacao["size"]
                    while bloco := resposta.read(min(1024 * 1024, restante + 1)):
                        restante -= len(bloco)
                        if restante < 0:
                            raise ValueError(f"Tamanho inesperado para {nome}.")
                        saida.write(bloco)
            if calcular_sha256(temporario) != especificacao["sha256"]:
                raise ValueError(f"Download de {nome} não corresponde ao checksum oficial.")
            os.replace(temporario, destino)
        finally:
            if temporario is not None:
                temporario.unlink(missing_ok=True)
    validar_modelos(diretorio)
    (diretorio / "manifest.json").write_text(
        json.dumps({"revision": REVISION, "models": MODELS}, indent=2) + "\n", encoding="utf-8"
    )
