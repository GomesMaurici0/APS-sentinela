from dataclasses import replace

import numpy as np
import pytest
from sentinela.biometria.matching import MatchStatus, identificar
from sentinela.biometria.pipeline import (
    CaptureStatus,
    FacePipeline,
    avaliar_qualidade_rosto,
    normalizar_vetor_facial,
)
from sentinela.config import BiometricConfig


def vector(index=0):
    feature = np.zeros(128, dtype=np.float32)
    feature[index] = 1
    return feature


def test_known_unknown_empty_and_ambiguous():
    config = BiometricConfig()
    assert identificar(vector(), {}, config).status == MatchStatus.EMPTY
    assert identificar(vector(), {"a": [vector(1)]}, config).status == MatchStatus.UNKNOWN
    match = identificar(vector(), {"a": [vector()], "b": [vector(1)]}, config)
    assert match.status == MatchStatus.MATCHED
    assert match.subject_id == "a"
    match = identificar(vector(), {"a": [vector()], "b": [vector()]}, config)
    assert match.status == MatchStatus.AMBIGUOUS
    assert match.subject_id is None


def test_margin_compares_identities_not_samples():
    match = identificar(vector(), {"a": [vector()] * 5, "b": [vector(1)]}, BiometricConfig())
    assert match.subject_id == "a"
    assert match.margin == pytest.approx(1)


def test_identity_score_is_mean_not_lucky_sample():
    result = identificar(vector(), {"a": [vector()] + [vector(1)] * 4}, BiometricConfig())
    assert result.status == MatchStatus.UNKNOWN
    assert result.similarity == pytest.approx(0.2)


@pytest.mark.parametrize(
    "bad", [np.zeros(128), np.ones(127), np.full(128, np.nan), np.full(128, np.inf)]
)
def test_invalid_features_rejected(bad):
    with pytest.raises(ValueError):
        normalizar_vetor_facial(bad)


@pytest.mark.parametrize(
    "brightness,status",
    [(20, CaptureStatus.DARK), (245, CaptureStatus.BRIGHT), (120, CaptureStatus.BLURRY)],
)
def test_quality(brightness, status):
    image = np.full((160, 160, 3), brightness, np.uint8)
    assert avaliar_qualidade_rosto(image, [20, 20, 100, 100], BiometricConfig())[0] == status


def test_small_and_partial_faces_rejected():
    image = np.full((160, 160, 3), 100, np.uint8)
    assert (
        avaliar_qualidade_rosto(image, [0, 0, 40, 40], BiometricConfig())[0]
        == CaptureStatus.SMALL_FACE
    )
    assert (
        avaliar_qualidade_rosto(image, [-10, 0, 100, 100], BiometricConfig())[0]
        == CaptureStatus.FACE_OUTSIDE
    )


class Detector:
    def __init__(self, faces):
        self.faces = faces

    def setInputSize(self, size):
        self.size = size

    def detect(self, frame):
        return 0, self.faces


class ForbiddenRecognizer:
    def alignCrop(self, *args):
        pytest.fail("Não deveria extrair características de captura rejeitada")


@pytest.mark.parametrize(
    "faces,status",
    [(None, CaptureStatus.NO_FACE), (np.ones((2, 15)), CaptureStatus.MULTIPLE_FACES)],
)
def test_no_or_multiple_faces_never_extract_features(faces, status):
    pipeline = FacePipeline.__new__(FacePipeline)
    pipeline.config = BiometricConfig()
    pipeline.detector = Detector(faces)
    pipeline.recognizer = ForbiddenRecognizer()
    result = pipeline.analisar(np.zeros((480, 640, 3), np.uint8))
    assert result.status == status
    assert result.embedding is None


@pytest.mark.parametrize(
    "frame",
    [None, np.zeros((0, 0, 3), np.uint8), np.zeros((100, 100)), np.zeros((100, 100, 4), np.uint8)],
)
def test_invalid_frame_rejected_before_detector(frame):
    pipeline = FacePipeline.__new__(FacePipeline)
    result = pipeline.analisar(frame)
    assert result.status == CaptureStatus.INVALID_FRAME


@pytest.mark.parametrize(
    "change",
    [
        {"similarity_threshold": float("nan")},
        {"ambiguity_margin": -1},
        {"minimum_brightness": 250},
        {"maximum_frame_size": 10},
        {"minimum_sharpness": float("nan")},
    ],
)
def test_invalid_configuration(change):
    with pytest.raises(ValueError):
        replace(BiometricConfig(), **change)
