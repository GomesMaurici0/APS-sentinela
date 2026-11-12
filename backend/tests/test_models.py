import numpy as np
import pytest
from sentinela.biometria.models import (
    DEFAULT_MODELS,
    MODELS,
    download_models,
    sha256,
    validate_models,
)
from sentinela.biometria.pipeline import CaptureStatus, FacePipeline, normalized_embedding


def test_absent_or_corrupt_weights_fail(tmp_path):
    with pytest.raises(ValueError, match="ausente"):
        validate_models(tmp_path)
    (tmp_path / MODELS["yunet"]["file"]).write_bytes(b"not an onnx model")
    with pytest.raises(ValueError, match="Checksum"):
        validate_models(tmp_path)


@pytest.mark.models
def test_real_models_on_synthetic_input(monkeypatch):
    if not all((DEFAULT_MODELS / spec["file"]).exists() for spec in MODELS.values()):
        pytest.skip("Execute sentinela download-models para integração com modelos reais")

    def network_forbidden(*args, **kwargs):
        pytest.fail("Inferência não deve depender da rede")

    monkeypatch.setattr("urllib.request.urlopen", network_forbidden)
    paths = validate_models(DEFAULT_MODELS)
    assert sha256(paths["yunet"]) == MODELS["yunet"]["sha256"]
    pipeline = FacePipeline(DEFAULT_MODELS)
    result = pipeline.analyze(np.zeros((480, 640, 3), np.uint8))
    assert result.status == CaptureStatus.NO_FACE
    # Testa execução do reconhecedor com tensor sintético; não mede reconhecimento de pessoas.
    patch = np.random.default_rng(42).integers(0, 256, (112, 112, 3), dtype=np.uint8)
    feature = normalized_embedding(pipeline.recognizer.feature(patch))
    assert feature.shape == (128,)
    assert np.linalg.norm(feature) == pytest.approx(1)


def test_corrupt_download_is_never_installed(tmp_path, monkeypatch):
    from io import BytesIO

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: BytesIO(b"tampered"))
    with pytest.raises(ValueError, match="checksum"):
        download_models(tmp_path)
    assert list(tmp_path.iterdir()) == []
