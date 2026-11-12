import math
import os
from dataclasses import dataclass
from pathlib import Path


def data_directory() -> Path:
    """Dados privados fora do repositório e da árvore OneDrive por padrão."""
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return Path(os.environ.get("SENTINELA_DATA_DIR", base / "Sentinela" / "prototype"))


@dataclass(frozen=True)
class BiometricConfig:
    # Valores iniciais experimentais. Similaridade não representa probabilidade.
    detection_threshold: float = 0.9
    similarity_threshold: float = 0.45
    ambiguity_margin: float = 0.08
    minimum_face_size: int = 80
    minimum_brightness: float = 45
    maximum_brightness: float = 220
    minimum_sharpness: float = 35
    maximum_frame_size: int = 960

    def __post_init__(self):
        if not all(
            math.isfinite(value)
            for value in (
                self.detection_threshold,
                self.similarity_threshold,
                self.ambiguity_margin,
                self.minimum_face_size,
                self.minimum_brightness,
                self.maximum_brightness,
                self.minimum_sharpness,
                self.maximum_frame_size,
            )
        ):
            raise ValueError("Configuração deve conter apenas números finitos.")
        if not 0 < self.detection_threshold <= 1:
            raise ValueError("Limiar de detecção deve estar entre 0 e 1.")
        if not 0 < self.similarity_threshold <= 1:
            raise ValueError("Limiar de similaridade deve estar entre 0 e 1.")
        if not 0 <= self.ambiguity_margin <= 2:
            raise ValueError("Margem de ambiguidade inválida.")
        if self.minimum_face_size < 16 or self.maximum_frame_size < self.minimum_face_size:
            raise ValueError("Dimensões inválidas.")
        if not 0 <= self.minimum_brightness < self.maximum_brightness <= 255:
            raise ValueError("Limites de iluminação inválidos.")
        if self.minimum_sharpness < 0:
            raise ValueError("Limite de nitidez inválido.")
