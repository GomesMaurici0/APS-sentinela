from argparse import Namespace

import pytest
from sentinela.cli import camera, main
from sentinela.galeria import Gallery


def test_invalid_access_target_does_not_open_camera(capsys):
    assert main(["camera", "--access-level", "2"]) == 1
    assert "divisão" in capsys.readouterr().err


def test_missing_models_produces_actionable_error(tmp_path, capsys):
    assert main(["doctor", "--models", str(tmp_path)]) == 1
    assert "download-models" in capsys.readouterr().err


def test_camera_unavailable_releases_device(tmp_path, monkeypatch):
    class UnavailableCamera:
        released = False

        def isOpened(self):
            return False

        def release(self):
            self.released = True

    device = UnavailableCamera()
    monkeypatch.setattr("cv2.VideoCapture", lambda index: device)
    monkeypatch.setattr("cv2.destroyAllWindows", lambda: None)
    args = Namespace(enroll=None, consent=False, device=0)
    with pytest.raises(ValueError, match="Câmera indisponível"):
        camera(args, None, Gallery(tmp_path))
    assert device.released


def test_missing_consent_does_not_open_camera(tmp_path, monkeypatch):
    def forbidden(*args):
        pytest.fail("Não abrir câmera de cadastro antes do consentimento")

    monkeypatch.setattr("cv2.VideoCapture", forbidden)
    with pytest.raises(ValueError, match="consentimento"):
        camera(Namespace(enroll="a", consent=False), None, Gallery(tmp_path))
