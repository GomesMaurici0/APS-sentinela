from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from sentinela.biometria.models import validar_modelos
from sentinela.config import BiometricConfig


class CaptureStatus(StrEnum):
    OK = "ok"
    INVALID_FRAME = "imagem_invalida"
    NO_FACE = "nenhum_rosto"
    MULTIPLE_FACES = "multiplos_rostos"
    SMALL_FACE = "rosto_pequeno"
    FACE_OUTSIDE = "rosto_fora_do_quadro"
    DARK = "iluminacao_baixa"
    BRIGHT = "iluminacao_alta"
    BLURRY = "imagem_desfocada"


@dataclass
class Analysis:
    status: CaptureStatus
    frame: np.ndarray | None = field(default=None, repr=False)
    faces: np.ndarray | None = field(default=None, repr=False)
    aligned: np.ndarray | None = field(default=None, repr=False)
    embedding: np.ndarray | None = field(default=None, repr=False)
    brightness: float | None = None
    sharpness: float | None = None
    elapsed_ms: float = 0


def normalizar_vetor_facial(valor: np.ndarray) -> np.ndarray:
    caracteristicas = np.asarray(valor, dtype=np.float32).reshape(-1)
    if caracteristicas.size != 128 or not np.isfinite(caracteristicas).all():
        raise ValueError("Embedding inválido.")
    norma = float(np.linalg.norm(caracteristicas))
    if not np.isfinite(norma) or norma < 1e-8:
        raise ValueError("Embedding sem informação.")
    return caracteristicas / norma


def avaliar_qualidade_rosto(quadro, rosto, configuracao: BiometricConfig):
    x, y, largura, altura = map(float, rosto[:4])
    if min(largura, altura) < configuracao.minimum_face_size:
        return CaptureStatus.SMALL_FACE, None, None
    altura_imagem, largura_imagem = quadro.shape[:2]
    if x < 0 or y < 0 or x + largura > largura_imagem or y + altura > altura_imagem:
        return CaptureStatus.FACE_OUTSIDE, None, None
    recorte = quadro[int(y) : int(y + altura), int(x) : int(x + largura)]
    tons_cinza = cv2.cvtColor(recorte, cv2.COLOR_BGR2GRAY)
    iluminacao = float(np.mean(tons_cinza))
    nitidez = float(cv2.Laplacian(tons_cinza, cv2.CV_64F).var())
    if iluminacao < configuracao.minimum_brightness:
        status = CaptureStatus.DARK
    elif iluminacao > configuracao.maximum_brightness:
        status = CaptureStatus.BRIGHT
    elif nitidez < configuracao.minimum_sharpness:
        status = CaptureStatus.BLURRY
    else:
        status = CaptureStatus.OK
    return status, iluminacao, nitidez


class FacePipeline:
    def __init__(self, modelos: Path, configuracao: BiometricConfig | None = None):
        self.config = configuracao or BiometricConfig()
        caminhos = validar_modelos(modelos)
        self.detector = cv2.FaceDetectorYN.create(
            str(caminhos["yunet"]), "", (320, 320), self.config.detection_threshold, 0.3, 5000
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(caminhos["sface"]), "")

    def analisar(self, quadro: np.ndarray) -> Analysis:
        inicio = perf_counter()
        resultado = Analysis(CaptureStatus.INVALID_FRAME)
        if (
            not isinstance(quadro, np.ndarray)
            or quadro.dtype != np.uint8
            or quadro.ndim != 3
            or quadro.shape[2] != 3
            or min(quadro.shape[:2]) < 16
        ):
            return resultado
        altura, largura = quadro.shape[:2]
        escala = min(1.0, self.config.maximum_frame_size / max(altura, largura))
        resultado.frame = cv2.resize(quadro, (round(largura * escala), round(altura * escala)))
        altura, largura = resultado.frame.shape[:2]
        self.detector.setInputSize((largura, altura))
        _, rostos = self.detector.detect(resultado.frame)
        resultado.faces = rostos
        quantidade = 0 if rostos is None else len(rostos)
        if quantidade == 0:
            resultado.status = CaptureStatus.NO_FACE
        elif quantidade != 1:
            resultado.status = CaptureStatus.MULTIPLE_FACES
        else:
            resultado.status, resultado.brightness, resultado.sharpness = avaliar_qualidade_rosto(
                resultado.frame, rostos[0], self.config
            )
            if resultado.status == CaptureStatus.OK:
                resultado.aligned = self.recognizer.alignCrop(resultado.frame, rostos[0])
                resultado.embedding = normalizar_vetor_facial(
                    self.recognizer.feature(resultado.aligned)
                )
        resultado.elapsed_ms = (perf_counter() - inicio) * 1000
        return resultado
