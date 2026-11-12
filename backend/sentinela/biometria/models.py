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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_models(directory: Path) -> dict[str, Path]:
    paths = {}
    for name, spec in MODELS.items():
        path = directory / spec["file"]
        if not path.is_file():
            raise ValueError("Modelo ausente. Execute: sentinela download-models")
        if path.stat().st_size != spec["size"] or sha256(path) != spec["sha256"]:
            raise ValueError(f"Checksum inválido para o modelo {name}.")
        paths[name] = path
    return paths


def download_models(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, spec in MODELS.items():
        target = directory / spec["file"]
        if target.exists() and sha256(target) == spec["sha256"]:
            continue
        url = (
            f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{REVISION}"
            f"/models/{spec['directory']}/{spec['file']}"
        )
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory, delete=False) as output:
                temporary = Path(output.name)
                with urllib.request.urlopen(url, timeout=60) as response:
                    remaining = spec["size"]
                    while block := response.read(min(1024 * 1024, remaining + 1)):
                        remaining -= len(block)
                        if remaining < 0:
                            raise ValueError(f"Tamanho inesperado para {name}.")
                        output.write(block)
            if sha256(temporary) != spec["sha256"]:
                raise ValueError(f"Download de {name} não corresponde ao checksum oficial.")
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    validate_models(directory)
    (directory / "manifest.json").write_text(
        json.dumps({"revision": REVISION, "models": MODELS}, indent=2) + "\n", encoding="utf-8"
    )
