import base64
import sqlite3
from dataclasses import dataclass, field

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sentinela.api import COOKIE, create_app
from sentinela.autorizacao import UserPermission
from sentinela.biometria.models import DEFAULT_MODELS, MODELS
from sentinela.biometria.pipeline import Analysis, CaptureStatus
from sentinela.config import BiometricConfig
from sentinela.galeria import Gallery

PASSWORD = "senha-ficticia-teste-123"


def image():
    ok, buffer = cv2.imencode(".png", np.zeros((160, 160, 3), np.uint8))
    assert ok
    return base64.b64encode(buffer).decode()


def vector(index=0):
    value = np.zeros(128, np.float32)
    value[index] = 1
    return value


@dataclass
class ControlledPipeline:
    """Só para testar orquestração HTTP. Não é evidência de acurácia facial."""

    config: BiometricConfig = field(default_factory=BiometricConfig)
    status: CaptureStatus = CaptureStatus.OK
    feature: np.ndarray = field(default_factory=vector)
    failure: bool = False

    def analyze(self, frame):
        if self.failure:
            raise cv2.error("falha simulada")
        return Analysis(self.status, frame=frame, embedding=self.feature.copy(), elapsed_ms=2)


@pytest.fixture
def environment(tmp_path):
    pipeline = ControlledPipeline()
    app = create_app(tmp_path, pipeline=pipeline)
    app.state.database.create_admin("admin", PASSWORD)
    with TestClient(app, base_url="http://localhost") as client:
        yield client, app, pipeline


@pytest.fixture
def signed(environment):
    client, app, pipeline = environment
    response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client, app, pipeline


def create(client, subject="voluntario", level=1, divisions=None):
    response = client.post(
        "/api/users",
        json={
            "subject_id": subject,
            "display_name": subject,
            "level": level,
            "divisions": divisions or [],
            "active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def enroll(client, subject="voluntario"):
    return client.post(
        f"/api/users/{subject}/biometrics", json={"consent": True, "images": [image()] * 5}
    )


def attempt(client, app, level=1, division=None, encoded=None):
    app.state.access.last_attempt = 0
    return client.post(
        "/api/attempts",
        json={"image": encoded or image(), "requested_level": level, "division": division},
    )


@pytest.mark.parametrize(
    "path", ["/api/users", "/api/attempts", "/api/stats", "/api/auth/session", "/api/openapi.json"]
)
def test_reads_require_auth(environment, path):
    client, _, _ = environment
    assert client.get(path).status_code == 401


def test_session_cookie_csrf_expiry_and_logout(signed):
    client, app, _ = signed
    token = client.cookies.get(COOKIE)
    assert client.get("/api/auth/session").json()["username"] == "admin"
    with app.state.database.connect() as connection:
        stored = connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
        encoded = connection.execute("SELECT password_hash FROM administrators").fetchone()[0]
    assert token != stored and PASSWORD not in encoded
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/auth/logout").status_code == 403
    session = client.get("/api/auth/session").json()
    client.headers["X-CSRF-Token"] = session["csrf_token"]
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set(COOKIE, token, path="/api")
    assert client.get("/api/users").status_code == 401


def test_cookie_flags_and_origin(environment):
    client, _, _ = environment
    response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert (
        client.post(
            "/api/auth/login",
            headers={"Origin": "https://hostil.example"},
            json={"username": "admin", "password": PASSWORD},
        ).status_code
        == 403
    )
    assert client.get("/api/users", headers={"Host": "hostil.example"}).status_code == 400


def test_expired_session_denied(signed):
    client, app, _ = signed
    with app.state.database.connect(write=True) as connection:
        connection.execute("UPDATE sessions SET expires_at=0")
    assert client.get("/api/users").status_code == 401


def test_repeated_invalid_login_is_limited(environment):
    client, _, _ = environment
    for _ in range(5):
        assert (
            client.post(
                "/api/auth/login", json={"username": "admin", "password": "errada"}
            ).status_code
            == 401
        )
    assert (
        client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD}).status_code
        == 429
    )


def test_user_crud_multidivision_and_conflict(signed):
    client, _, _ = signed
    create(client, level=2, divisions=["a", "b"])
    assert client.get("/api/users").json()["items"][0]["divisions"] == ["a", "b"]
    assert (
        client.post(
            "/api/users", json={"subject_id": "voluntario", "display_name": "Outro", "level": 1}
        ).status_code
        == 409
    )
    response = client.put(
        "/api/users/voluntario", json={"display_name": "Atualizado", "level": 3, "active": False}
    )
    assert response.status_code == 200 and response.json()["divisions"] == []
    assert client.delete("/api/users/voluntario").status_code == 204
    assert client.get("/api/users/voluntario").status_code == 404


@pytest.mark.parametrize(
    "values",
    [
        {"level": 2},
        {"level": True},
        {"level": 1, "divisions": ["a"]},
        {"level": 2, "divisions": ["a", "a"]},
        {"level": 2, "divisions": [" "]},
    ],
)
def test_invalid_permissions_rejected(signed, values):
    client, _, _ = signed
    response = client.post(
        "/api/users", json={"subject_id": "a", "display_name": "Teste", **values}
    )
    assert response.status_code == 422


def test_enrollment_requires_consent_quality_and_no_biometric_response(signed):
    client, app, pipeline = signed
    create(client)
    assert (
        client.post(
            "/api/users/voluntario/biometrics", json={"consent": False, "images": [image()] * 5}
        ).status_code
        == 422
    )
    pipeline.status = CaptureStatus.MULTIPLE_FACES
    assert enroll(client).status_code == 422
    assert client.get("/api/users/voluntario").json()["sample_count"] == 0
    pipeline.status = CaptureStatus.OK
    response = enroll(client)
    assert response.status_code == 200 and response.json()["sample_count"] == 5
    assert "samples" not in response.text and "embedding" not in response.text
    assert b'"samples"' not in app.state.database.path.read_bytes()


def test_duplicate_face_rejected(signed):
    client, _, _ = signed
    create(client, "a")
    assert enroll(client, "a").status_code == 200
    create(client, "b")
    assert enroll(client, "b").status_code == 409


def test_permission_changes_are_effective_and_attempts_persist(signed):
    client, app, _ = signed
    create(client, level=2, divisions=["a", "b"])
    assert enroll(client).status_code == 200
    first = attempt(client, app, 2, "b")
    assert first.status_code == 200 and first.json()["granted"] is True
    assert attempt(client, app, 2, "c").json()["reason"] == "divisao_nao_autorizada"
    assert attempt(client, app, 3).json()["reason"] == "nivel_insuficiente"
    client.put("/api/users/voluntario", json={"display_name": "Teste", "level": 3, "active": False})
    assert attempt(client, app).json()["reason"] == "usuario_inativo"
    history = client.get("/api/attempts?limit=2&offset=0").json()
    assert history["total"] == 4 and len(history["items"]) == 2
    assert client.get("/api/attempts?granted=true").json()["total"] == 1
    assert "image" not in client.get("/api/attempts").text
    assert client.get("/api/stats").json() == {
        "users": 1,
        "enrolled": 1,
        "attempts": 4,
        "granted": 1,
        "denied": 3,
    }


def test_unknown_no_face_and_multiple_faces_denied(signed):
    client, app, pipeline = signed
    assert attempt(client, app).json()["reason"] == "sem_referencias"
    create(client)
    assert enroll(client).status_code == 200
    pipeline.feature = vector(1)
    assert attempt(client, app).json()["reason"] == "desconhecido"
    for status in (CaptureStatus.NO_FACE, CaptureStatus.MULTIPLE_FACES, CaptureStatus.DARK):
        pipeline.status = status
        result = attempt(client, app).json()
        assert result["reason"] == status.value and not result["granted"]


def test_delete_invalidates_references_and_anonymizes_history(signed):
    client, app, _ = signed
    create(client)
    assert enroll(client).status_code == 200
    assert attempt(client, app).json()["subject_id"] == "voluntario"
    assert client.delete("/api/users/voluntario").status_code == 204
    assert client.get("/api/attempts").json()["items"][0]["subject_id"] is None
    assert attempt(client, app).json()["reason"] == "sem_referencias"


def test_revoke_biometrics_retains_user(signed):
    client, app, _ = signed
    create(client)
    assert enroll(client).status_code == 200
    assert client.delete("/api/users/voluntario/biometrics").status_code == 204
    assert client.get("/api/users/voluntario").json()["consent_at"] is None
    assert attempt(client, app).json()["reason"] == "sem_referencias"


def test_audit_failure_never_returns_grant(signed):
    client, app, _ = signed
    create(client)
    assert enroll(client).status_code == 200
    with app.state.database.connect(write=True) as connection:
        connection.executescript(
            "CREATE TRIGGER audit_failure BEFORE INSERT ON attempts "
            "BEGIN SELECT RAISE(ABORT, 'falha'); END;"
        )
    response = attempt(client, app)
    assert response.status_code == 503 and "granted" not in response.json()
    assert client.get("/api/attempts").json()["total"] == 0


def test_engine_failure_is_denied_and_audited(signed):
    client, app, pipeline = signed
    pipeline.failure = True
    response = attempt(client, app)
    assert response.status_code == 503
    history = client.get("/api/attempts").json()["items"]
    assert history[0]["reason"] == "falha_biometrica" and not history[0]["granted"]


def test_validation_does_not_echo_sensitive_input(signed):
    client, app, _ = signed
    secret = "conteudo_biometrico_privado"
    response = client.post("/api/attempts", json={"image": secret, "requested_level": 4})
    assert response.status_code == 422 and secret not in response.text
    response = attempt(client, app, encoded=secret)
    assert response.status_code == 200 and response.json()["reason"] == "imagem_invalida"
    assert secret not in client.get("/api/attempts").text


def test_import_legacy_preserves_permissions_and_moves_references(signed, tmp_path):
    client, app, _ = signed
    legacy = Gallery(tmp_path)
    legacy.enroll("antigo", UserPermission(2, frozenset({"a", "b"})), [vector()] * 5, True)
    response = client.post("/api/legacy/import")
    assert response.status_code == 200 and response.json()["imported"] == 1
    assert legacy.references() == {}
    assert client.get("/api/users/antigo").json()["divisions"] == ["a", "b"]
    assert attempt(client, app, 2, "b").json()["granted"]
    assert client.post("/api/legacy/import").json()["imported"] == 0


def test_import_conflict_never_erases_legacy(signed, tmp_path):
    client, _, _ = signed
    create(client, "antigo")
    legacy = Gallery(tmp_path)
    legacy.enroll("antigo", UserPermission(1), [vector()] * 5, True)
    assert client.post("/api/legacy/import").status_code == 409
    assert "antigo" in legacy.references()


def test_persistence_survives_new_app(signed, tmp_path):
    client, _, _ = signed
    create(client)
    assert enroll(client).status_code == 200
    other = create_app(tmp_path, pipeline=ControlledPipeline())
    with TestClient(other, base_url="http://localhost") as restarted:
        auth = restarted.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
        restarted.headers["X-CSRF-Token"] = auth.json()["csrf_token"]
        assert restarted.get("/api/users").json()["total"] == 1
        assert restarted.post(
            "/api/attempts", json={"image": image(), "requested_level": 1}
        ).json()["granted"]


def test_attempt_rate_limit(signed):
    client, app, _ = signed
    assert attempt(client, app).status_code == 200
    assert (
        client.post("/api/attempts", json={"image": image(), "requested_level": 1}).status_code
        == 429
    )


def test_oversized_body_and_bad_image_dimensions(signed):
    client, _, _ = signed
    assert (
        client.post("/api/biometrics/analyze", content=b"x" * (8 * 1024 * 1024 + 1)).status_code
        == 413
    )
    _, buffer = cv2.imencode(".png", np.zeros((1000, 1000, 3), np.uint8))
    response = client.post(
        "/api/biometrics/analyze", json={"image": base64.b64encode(buffer).decode()}
    )
    assert response.status_code == 422


@pytest.mark.models
def test_real_api_inference_without_face(tmp_path):
    if not all((DEFAULT_MODELS / spec["file"]).exists() for spec in MODELS.values()):
        pytest.skip("Modelos locais não instalados")
    app = create_app(tmp_path)
    app.state.database.create_admin("admin", PASSWORD)
    with TestClient(app, base_url="http://localhost") as client:
        auth = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
        client.headers["X-CSRF-Token"] = auth.json()["csrf_token"]
        result = attempt(client, app)
        assert result.status_code == 200
        assert result.json()["reason"] == "nenhum_rosto"
        assert not result.json()["granted"]


def test_missing_biometric_key_denies_and_audits(signed):
    client, app, _ = signed
    create(client)
    assert enroll(client).status_code == 200
    app.state.database.key_path.unlink()
    assert attempt(client, app).status_code == 503
    assert not app.state.database.key_path.exists()
    last = client.get("/api/attempts").json()["items"][0]
    assert last["reason"] == "falha_biometrica" and not last["granted"]


def test_bootstrap_admin_cannot_be_repeated(environment):
    _, app, _ = environment
    with pytest.raises(ValueError, match="não pode ser repetida"):
        app.state.database.create_admin("outro_admin", PASSWORD)


def test_import_cleanup_retry_is_idempotent(signed, tmp_path, monkeypatch):
    client, _, _ = signed
    legacy = Gallery(tmp_path)
    legacy.enroll("antigo", UserPermission(1), [vector()] * 5, True)
    original = Gallery._change

    def fail(*args):
        raise sqlite3.OperationalError("falha de limpeza simulada")

    monkeypatch.setattr(Gallery, "_change", fail)
    assert client.post("/api/legacy/import").status_code == 503
    assert client.get("/api/users").json()["total"] == 1
    assert "antigo" in legacy.references()
    monkeypatch.setattr(Gallery, "_change", original)
    result = client.post("/api/legacy/import")
    assert result.status_code == 200
    assert result.json() == {"imported": 0, "already_present": 1}
    assert legacy.references() == {}


def test_delete_missing_user_does_not_erase_legacy(signed, tmp_path):
    client, _, _ = signed
    legacy = Gallery(tmp_path)
    legacy.enroll("antigo", UserPermission(1), [vector()] * 5, True)
    assert client.delete("/api/users/antigo").status_code == 404
    assert "antigo" in legacy.references()


def test_openapi_describes_cookie_and_csrf_as_joint_requirement(environment):
    _, app, _ = environment
    schema = app.openapi()
    assert schema["paths"]["/api/users"]["post"]["security"] == [
        {"APIKeyCookie": [], "APIKeyHeader": []}
    ]
