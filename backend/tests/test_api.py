import base64
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sentinela.api import criar_aplicacao
from sentinela.autorizacao import UserPermission
from sentinela.biometria.models import DEFAULT_MODELS, MODELS
from sentinela.biometria.pipeline import Analysis, CaptureStatus
from sentinela.config import BiometricConfig
from sentinela.galeria import Gallery


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

    def analisar(self, frame):
        if self.failure:
            raise cv2.error("falha simulada")
        return Analysis(self.status, frame=frame, embedding=self.feature.copy(), elapsed_ms=2)


@pytest.fixture
def environment(tmp_path):
    pipeline = ControlledPipeline()
    app = criar_aplicacao(tmp_path, pipeline=pipeline)
    with TestClient(app, base_url="http://localhost") as client:
        yield client, app, pipeline


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


def cadastrar_biometria(client, subject="voluntario"):
    return client.post(
        f"/api/users/{subject}/biometrics", json={"consent": True, "images": [image()] * 5}
    )


def avaliar_acesso(client, app, level=1, division=None, encoded=None):
    app.state.access.last_attempt = 0
    return client.post(
        "/api/attempts",
        json={"image": encoded or image(), "requested_level": level, "division": division},
    )


@pytest.mark.parametrize("path", ["/api/users", "/api/attempts", "/api/stats", "/api/openapi.json"])
def test_reads_work_without_login(environment, path):
    client, _, _ = environment
    assert client.get(path).status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [("POST", "/api/auth/login"), ("GET", "/api/auth/session"), ("POST", "/api/auth/logout")],
)
def test_removed_auth_routes_are_unavailable(environment, method, path):
    client, _, _ = environment
    assert client.request(method, path).status_code in (404, 405)


def test_local_origin_and_host_boundary(environment):
    client, _, _ = environment
    assert (
        client.post("/api/users", headers={"Origin": "https://hostil.example"}, json={}).status_code
        == 403
    )
    assert client.get("/api/users", headers={"Host": "hostil.example"}).status_code == 400


def test_user_crud_multidivision_and_conflict(environment):
    client, _, _ = environment
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
def test_invalid_permissions_rejected(environment, values):
    client, _, _ = environment
    response = client.post(
        "/api/users", json={"subject_id": "a", "display_name": "Teste", **values}
    )
    assert response.status_code == 422


def test_enrollment_requires_consent_quality_and_no_biometric_response(environment):
    client, app, pipeline = environment
    create(client)
    assert (
        client.post(
            "/api/users/voluntario/biometrics", json={"consent": False, "images": [image()] * 5}
        ).status_code
        == 422
    )
    pipeline.status = CaptureStatus.MULTIPLE_FACES
    assert cadastrar_biometria(client).status_code == 422
    assert client.get("/api/users/voluntario").json()["sample_count"] == 0
    pipeline.status = CaptureStatus.OK
    response = cadastrar_biometria(client)
    assert response.status_code == 200 and response.json()["sample_count"] == 5
    assert "samples" not in response.text and "embedding" not in response.text
    assert b'"samples"' not in app.state.database.path.read_bytes()


def test_duplicate_face_rejected(environment):
    client, _, _ = environment
    create(client, "a")
    assert cadastrar_biometria(client, "a").status_code == 200
    create(client, "b")
    assert cadastrar_biometria(client, "b").status_code == 409


def test_permission_changes_are_effective_and_attempts_persist(environment):
    client, app, _ = environment
    create(client, level=2, divisions=["a", "b"])
    assert cadastrar_biometria(client).status_code == 200
    first = avaliar_acesso(client, app, 2, "b")
    assert first.status_code == 200 and first.json()["granted"] is True
    assert avaliar_acesso(client, app, 2, "c").json()["reason"] == "divisao_nao_autorizada"
    assert avaliar_acesso(client, app, 3).json()["reason"] == "nivel_insuficiente"
    client.put("/api/users/voluntario", json={"display_name": "Teste", "level": 3, "active": False})
    assert avaliar_acesso(client, app).json()["reason"] == "usuario_inativo"
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


def test_unknown_no_face_and_multiple_faces_denied(environment):
    client, app, pipeline = environment
    assert avaliar_acesso(client, app).json()["reason"] == "sem_referencias"
    create(client)
    assert cadastrar_biometria(client).status_code == 200
    pipeline.feature = vector(1)
    assert avaliar_acesso(client, app).json()["reason"] == "desconhecido"
    for status in (CaptureStatus.NO_FACE, CaptureStatus.MULTIPLE_FACES, CaptureStatus.DARK):
        pipeline.status = status
        result = avaliar_acesso(client, app).json()
        assert result["reason"] == status.value and not result["granted"]


def test_delete_invalidates_references_and_anonymizes_history(environment):
    client, app, _ = environment
    create(client)
    assert cadastrar_biometria(client).status_code == 200
    assert avaliar_acesso(client, app).json()["subject_id"] == "voluntario"
    assert client.delete("/api/users/voluntario").status_code == 204
    assert client.get("/api/attempts").json()["items"][0]["subject_id"] is None
    assert avaliar_acesso(client, app).json()["reason"] == "sem_referencias"


def test_revoke_biometrics_retains_user(environment):
    client, app, _ = environment
    create(client)
    assert cadastrar_biometria(client).status_code == 200
    assert client.delete("/api/users/voluntario/biometrics").status_code == 204
    assert client.get("/api/users/voluntario").json()["consent_at"] is None
    assert avaliar_acesso(client, app).json()["reason"] == "sem_referencias"


def test_audit_failure_never_returns_grant(environment):
    client, app, _ = environment
    create(client)
    assert cadastrar_biometria(client).status_code == 200
    with app.state.database.conectar(write=True) as connection:
        connection.executescript(
            "CREATE TRIGGER audit_failure BEFORE INSERT ON tentativas_acesso "
            "BEGIN SELECT RAISE(ABORT, 'falha'); END;"
        )
    response = avaliar_acesso(client, app)
    assert response.status_code == 503 and "granted" not in response.json()
    assert client.get("/api/attempts").json()["total"] == 0


def test_engine_failure_is_denied_and_audited(environment):
    client, app, pipeline = environment
    pipeline.failure = True
    response = avaliar_acesso(client, app)
    assert response.status_code == 503
    history = client.get("/api/attempts").json()["items"]
    assert history[0]["reason"] == "falha_biometrica" and not history[0]["granted"]


def test_validation_does_not_echo_sensitive_input(environment):
    client, app, _ = environment
    secret = "conteudo_biometrico_privado"
    response = client.post("/api/attempts", json={"image": secret, "requested_level": 4})
    assert response.status_code == 422 and secret not in response.text
    response = avaliar_acesso(client, app, encoded=secret)
    assert response.status_code == 200 and response.json()["reason"] == "imagem_invalida"
    assert secret not in client.get("/api/attempts").text


def test_import_legacy_preserves_permissions_and_moves_references(environment, tmp_path):
    client, app, _ = environment
    legacy = Gallery(tmp_path)
    legacy.cadastrar_biometria(
        "antigo", UserPermission(2, frozenset({"a", "b"})), [vector()] * 5, True
    )
    response = client.post("/api/legacy/import")
    assert response.status_code == 200 and response.json()["imported"] == 1
    assert legacy.obter_referencias() == {}
    assert client.get("/api/users/antigo").json()["divisions"] == ["a", "b"]
    assert avaliar_acesso(client, app, 2, "b").json()["granted"]
    assert client.post("/api/legacy/import").json()["imported"] == 0


def test_import_conflict_never_erases_legacy(environment, tmp_path):
    client, _, _ = environment
    create(client, "antigo")
    legacy = Gallery(tmp_path)
    legacy.cadastrar_biometria("antigo", UserPermission(1), [vector()] * 5, True)
    assert client.post("/api/legacy/import").status_code == 409
    assert "antigo" in legacy.obter_referencias()


def test_persistence_survives_new_app(environment, tmp_path):
    client, _, _ = environment
    create(client)
    assert cadastrar_biometria(client).status_code == 200
    other = criar_aplicacao(tmp_path, pipeline=ControlledPipeline())
    with TestClient(other, base_url="http://localhost") as restarted:
        assert restarted.get("/api/users").json()["total"] == 1
        assert restarted.post(
            "/api/attempts", json={"image": image(), "requested_level": 1}
        ).json()["granted"]


def test_attempt_rate_limit(environment):
    client, app, _ = environment
    assert avaliar_acesso(client, app).status_code == 200
    assert (
        client.post("/api/attempts", json={"image": image(), "requested_level": 1}).status_code
        == 429
    )


def test_oversized_body_and_bad_image_dimensions(environment):
    client, _, _ = environment
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
    app = criar_aplicacao(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        result = avaliar_acesso(client, app)
        assert result.status_code == 200
        assert result.json()["reason"] == "nenhum_rosto"
        assert not result.json()["granted"]


def test_missing_biometric_key_denies_and_audits(environment):
    client, app, _ = environment
    create(client)
    assert cadastrar_biometria(client).status_code == 200
    app.state.database.key_path.unlink()
    assert avaliar_acesso(client, app).status_code == 503
    assert not app.state.database.key_path.exists()
    last = client.get("/api/attempts").json()["items"][0]
    assert last["reason"] == "falha_biometrica" and not last["granted"]


def test_import_cleanup_retry_is_idempotent(environment, tmp_path, monkeypatch):
    client, _, _ = environment
    legacy = Gallery(tmp_path)
    legacy.cadastrar_biometria("antigo", UserPermission(1), [vector()] * 5, True)
    original = Gallery._alterar

    def fail(*args):
        raise sqlite3.OperationalError("falha de limpeza simulada")

    monkeypatch.setattr(Gallery, "_alterar", fail)
    assert client.post("/api/legacy/import").status_code == 503
    assert client.get("/api/users").json()["total"] == 1
    assert "antigo" in legacy.obter_referencias()
    monkeypatch.setattr(Gallery, "_alterar", original)
    result = client.post("/api/legacy/import")
    assert result.status_code == 200
    assert result.json() == {"imported": 0, "already_present": 1}
    assert legacy.obter_referencias() == {}


def test_delete_missing_user_does_not_erase_legacy(environment, tmp_path):
    client, _, _ = environment
    legacy = Gallery(tmp_path)
    legacy.cadastrar_biometria("antigo", UserPermission(1), [vector()] * 5, True)
    assert client.delete("/api/users/antigo").status_code == 404
    assert "antigo" in legacy.obter_referencias()


def test_openapi_has_no_administrative_authentication(environment):
    _, app, _ = environment
    schema = app.openapi()
    assert "securitySchemes" not in schema.get("components", {})
    assert all(not path.startswith("/api/auth/") for path in schema["paths"])
    assert "security" not in schema["paths"]["/api/users"]["post"]


def test_migration_removes_only_auth_tables_and_preserves_users(tmp_path):
    from sentinela.database import Database

    database = Database(tmp_path)
    tmp_path.mkdir(exist_ok=True)
    with database.conectar() as connection:
        migration = Path(__file__).parents[1] / "sentinela/migrations/001_initial.sql"
        connection.executescript(migration.read_text("utf-8"))
        connection.execute(
            "INSERT INTO users VALUES (?, ?, 1, 1, NULL, NULL, ?, ?)",
            ("preservado", "Usuário", "data", "data"),
        )
        connection.execute("INSERT INTO administrators VALUES ('antigo', 'hash-legado', 'data')")
        connection.execute(
            "INSERT INTO biometric_references VALUES ('preservado', 'modelo', ?, 5, 'data')",
            (b"referencias-cifradas-preservadas",),
        )
        connection.execute(
            "INSERT INTO attempts (occurred_at, subject_id, requested_level, granted, "
            "reason, elapsed_ms, model_id, config_json) "
            "VALUES ('data', 'preservado', 1, 1, 'acesso_autorizado', 2, 'modelo', '{}')"
        )
    database.inicializar()
    database.inicializar()
    with database.conectar() as connection:
        assert database.obter_usuario(connection, "preservado")["level"] == 1
        assert (
            connection.execute("SELECT encrypted_samples FROM referencias_biometricas").fetchone()[
                0
            ]
            == b"referencias-cifradas-preservadas"
        )
        assert (
            connection.execute("SELECT subject_id FROM tentativas_acesso").fetchone()[0]
            == "preservado"
        )
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert not tables & {"administrators", "sessions", "login_failures"}
        assert {"usuarios", "referencias_biometricas", "tentativas_acesso"} <= tables
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
