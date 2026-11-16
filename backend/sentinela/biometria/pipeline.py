from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from sentinela.biometria.models import validate_models
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


def normalized_embedding(value: np.ndarray) -> np.ndarray:
    feature = np.asarray(value, dtype=np.float32).reshape(-1)
    if feature.size != 128 or not np.isfinite(feature).all():
        raise ValueError("Embedding inválido.")
    norm = float(np.linalg.norm(feature))
    if not np.isfinite(norm) or norm < 1e-8:
        raise ValueError("Embedding sem informação.")
    return feature / norm


def face_quality(frame, face, config: BiometricConfig):
    x, y, width, height = map(float, face[:4])
    if min(width, height) < config.minimum_face_size:
        return CaptureStatus.SMALL_FACE, None, None
    image_height, image_width = frame.shape[:2]
    if x < 0 or y < 0 or x + width > image_width or y + height > image_height:
        return CaptureStatus.FACE_OUTSIDE, None, None
    crop = frame[int(y): int(y + height), int(x): int(x + width)]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if brightness < config.minimum_brightness:
        status = CaptureStatus.DARK
    elif brightness > config.maximum_brightness:
        status = CaptureStatus.BRIGHT
    elif sharpness < config.minimum_sharpness:
        status = CaptureStatus.BLURRY
    else:
        status = CaptureStatus.OK
    return status, brightness, sharpness


class FacePipeline:
    """Uma instância por fluxo; objetos OpenCV não são compartilhados entre threads."""

    def __init__(self, models: Path, config: BiometricConfig | None = None):
        self.config = config or BiometricConfig()
        paths = validate_models(models)
        self.detector = cv2.FaceDetectorYN.create(
            str(paths["yunet"]), "", (320, 320), self.config.detection_threshold, 0.3, 5000
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(paths["sface"]), "")

    def analyze(self, frame: np.ndarray) -> Analysis:
        start = perf_counter()
        result = Analysis(CaptureStatus.INVALID_FRAME)
        if (
                not isinstance(frame, np.ndarray)
                or frame.dtype != np.uint8
                or frame.ndim != 3
                or frame.shape[2] != 3
                or min(frame.shape[:2]) < 16
        ):
            return result
        height, width = frame.shape[:2]
        scale = min(1.0, self.config.maximum_frame_size / max(height, width))
        result.frame = cv2.resize(frame, (round(width * scale), round(height * scale)))
        height, width = result.frame.shape[:2]
        self.detector.setInputSize((width, height))
        _, faces = self.detector.detect(result.frame)
        result.faces = faces
        count = 0 if faces is None else len(faces)
        if count == 0:
            result.status = CaptureStatus.NO_FACE
        elif count != 1:
            result.status = CaptureStatus.MULTIPLE_FACES
        else:
            result.status, result.brightness, result.sharpness = face_quality(
                result.frame, faces[0], self.config
            )
            if result.status == CaptureStatus.OK:
                result.aligned = self.recognizer.alignCrop(result.frame, faces[0])
                result.embedding = normalized_embedding(self.recognizer.feature(result.aligned))
        result.elapsed_ms = (perf_counter() - start) * 1000
        return result
