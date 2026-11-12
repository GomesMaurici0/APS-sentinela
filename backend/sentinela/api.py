import secrets
import sqlite3
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyCookie, APIKeyHeader
from starlette.middleware.trustedhost import TrustedHostMiddleware

from sentinela.access_service import AccessService, attempt_record
from sentinela.biometria.models import DEFAULT_MODELS
from sentinela.config import data_directory
from sentinela.database import Database, now
from sentinela.errors import DomainError
from sentinela.galeria import Gallery
from sentinela.schemas import (
    AttemptInput,
    AttemptPage,
    CaptureResponse,
    DecisionResponse,
    Enrollment,
    ErrorResponse,
    ImageInput,
    ImportResponse,
    Login,
    SessionResponse,
    StatsResponse,
    UserCreate,
    UserPage,
    UserResponse,
    UserUpdate,
)

COOKIE = "sentinela_session"
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class LocalBoundary:
    """Limites de entrada e cabeçalhos aplicados também às respostas de erro."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        method = scope["method"]
        origin = headers.get(b"origin")
        host = headers.get(b"host", b"")
        if origin and origin != scope["scheme"].encode() + b"://" + host:
            return await JSONResponse({"detail": "Origem não autorizada."}, 403)(
                scope, receive, send
            )
        chunks = []
        size = 0
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                size += len(message.get("body", b""))
                if size > 8 * 1024 * 1024:
                    return await JSONResponse({"detail": "Corpo excede 8 MiB."}, 413)(
                        scope, receive, send
                    )
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
        delivered = False

        async def limited_receive():
            nonlocal delivered
            if not delivered and chunks:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        async def protected_send(message):
            if message["type"] == "http.response.start":
                message["headers"] += [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"permissions-policy", b"camera=(self), microphone=()"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; img-src 'self' data: blob:; "
                        b"style-src 'self'; script-src 'self'; connect-src 'self'; "
                        b"object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
                    ),
                ]
            await send(message)

        await self.app(scope, limited_receive, protected_send)


def create_app(
    directory: Path | None = None, models: Path = DEFAULT_MODELS, pipeline=None
) -> FastAPI:
    directory = directory or data_directory()
    database = Database(directory)
    database.initialize()
    service = AccessService(database, models, pipeline)
    app = FastAPI(
        title="SENTINELA",
        version="0.2.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        telemetry={
            "tracing": False,
            "metrics": False,
            "logs": False,
            "operation_spans": False,
            "auto_configure": False,
        },
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    app.state.database = database
    app.state.access = service
    app.add_middleware(LocalBoundary)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
    cookie = APIKeyCookie(name=COOKIE, auto_error=False)
    csrf_header = APIKeyHeader(name="X-CSRF-Token", auto_error=False)

    def authenticated(token: str | None = Depends(cookie)):
        return database.session(token)

    def mutating(session=Depends(authenticated), csrf: str | None = Depends(csrf_header)):
        if not csrf or not secrets.compare_digest(csrf, session["csrf_token"]):
            raise DomainError(403, "Token de proteção ausente ou inválido. Atualize a sessão.")
        return session

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        return JSONResponse({"detail": error.message}, status_code=error.status)

    @app.exception_handler(sqlite3.Error)
    async def persistence_error(request: Request, error: sqlite3.Error):
        return JSONResponse(
            {"detail": "Persistência indisponível. Nenhuma autorização confirmada."},
            status_code=503,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # Nunca ecoar input, senha, base64 ou contexto de exceções de validação.
        return JSONResponse(
            {"detail": "Dados inválidos. Confira os campos e o formato das imagens."},
            status_code=422,
        )

    @app.post("/api/auth/login", response_model=SessionResponse, tags=["Autenticação"])
    def login(body: Login, response: Response):
        token, session = database.login(body.username, body.password)
        response.set_cookie(
            COOKIE,
            token,
            max_age=8 * 60 * 60,
            httponly=True,
            samesite="strict",
            secure=False,
            path="/api",
        )
        return session

    @app.get("/api/auth/session", response_model=SessionResponse, tags=["Autenticação"])
    def session_info(session=Depends(authenticated)):
        return session

    @app.post("/api/auth/logout", status_code=204, tags=["Autenticação"])
    def logout(response: Response, session=Depends(mutating)):
        with database.connect(write=True) as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (session["token_hash"],))
        response.delete_cookie(COOKIE, path="/api", httponly=True, samesite="strict")

    @app.get("/api/users", response_model=UserPage, tags=["Usuários"])
    def list_users(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        session=Depends(authenticated),
    ):
        with database.connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            ids = connection.execute(
                "SELECT subject_id FROM users ORDER BY subject_id LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
            items = [database.user(connection, row[0]) for row in ids]
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    @app.post("/api/users", status_code=201, response_model=UserResponse, tags=["Usuários"])
    def create_user(body: UserCreate, session=Depends(mutating)):
        with database.connect(write=True) as connection:
            database.insert_user(
                connection,
                body.subject_id,
                body.display_name,
                body.level,
                body.active,
                body.divisions,
            )
            return database.user(connection, body.subject_id)

    @app.get("/api/users/{subject_id}", response_model=UserResponse, tags=["Usuários"])
    def get_user(subject_id: str, session=Depends(authenticated)):
        with database.connect() as connection:
            return database.user(connection, subject_id)

    @app.put("/api/users/{subject_id}", response_model=UserResponse, tags=["Usuários"])
    def update_user(subject_id: str, body: UserUpdate, session=Depends(mutating)):
        with database.connect(write=True) as connection:
            database.user(connection, subject_id)
            connection.execute(
                "UPDATE users SET display_name=?, level=?, active=?, updated_at=? "
                "WHERE subject_id=?",
                (body.display_name, body.level, int(body.active), now(), subject_id),
            )
            connection.execute("DELETE FROM user_divisions WHERE subject_id=?", (subject_id,))
            connection.executemany(
                "INSERT INTO user_divisions VALUES (?, ?)",
                [(subject_id, division) for division in body.divisions],
            )
            return database.user(connection, subject_id)

    def purge_legacy(subject_id):
        # A exclusão confirmada não deve deixar cópia ativa no laboratório legado.
        legacy = Gallery(directory)
        try:
            if subject_id in legacy.read()["subjects"]:
                legacy.delete(subject_id)
        except ValueError as error:
            raise DomainError(503, "Não foi possível excluir a cópia do laboratório.") from error

    @app.delete("/api/users/{subject_id}", status_code=204, tags=["Usuários"])
    def delete_user(subject_id: str, session=Depends(mutating)):
        with database.connect() as connection:
            database.user(connection, subject_id)
        purge_legacy(subject_id)
        with database.connect(write=True) as connection:
            database.user(connection, subject_id)
            connection.execute("DELETE FROM users WHERE subject_id=?", (subject_id,))

    @app.post("/api/users/{subject_id}/biometrics", response_model=UserResponse, tags=["Biometria"])
    def enroll(subject_id: str, body: Enrollment, session=Depends(mutating)):
        service.enroll(subject_id, body.images)
        with database.connect() as connection:
            return database.user(connection, subject_id)

    @app.delete("/api/users/{subject_id}/biometrics", status_code=204, tags=["Biometria"])
    def delete_biometrics(subject_id: str, session=Depends(mutating)):
        with database.connect() as connection:
            database.user(connection, subject_id)
        purge_legacy(subject_id)
        with database.connect(write=True) as connection:
            database.user(connection, subject_id)
            connection.execute("DELETE FROM biometric_references WHERE subject_id=?", (subject_id,))
            connection.execute(
                "UPDATE users SET consent_at=NULL, consent_version=NULL, updated_at=? "
                "WHERE subject_id=?",
                (now(), subject_id),
            )

    @app.post("/api/biometrics/analyze", response_model=CaptureResponse, tags=["Biometria"])
    def analyze(body: ImageInput, session=Depends(mutating)):
        return service.analyze(body.image)

    @app.post("/api/attempts", response_model=DecisionResponse, tags=["Acessos"])
    def attempt(body: AttemptInput, session=Depends(mutating)):
        return service.attempt(body.image, body.requested_level, body.division)

    @app.get("/api/attempts", response_model=AttemptPage, tags=["Acessos"])
    def list_attempts(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        granted: bool | None = None,
        session=Depends(authenticated),
    ):
        where = " WHERE granted=?" if granted is not None else ""
        params = (int(granted),) if granted is not None else ()
        with database.connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM attempts" + where, params).fetchone()[
                0
            ]
            rows = connection.execute(
                "SELECT * FROM attempts" + where + " ORDER BY id DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        return {
            "items": [attempt_record(row) for row in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    @app.get("/api/stats", response_model=StatsResponse, tags=["Acessos"])
    def stats(session=Depends(authenticated)):
        with database.connect() as connection:
            users = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            enrolled = connection.execute("SELECT COUNT(*) FROM biometric_references").fetchone()[0]
            attempts, granted = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(granted),0) FROM attempts"
            ).fetchone()
        return {
            "users": users,
            "enrolled": enrolled,
            "attempts": attempts,
            "granted": granted,
            "denied": attempts - granted,
        }

    @app.post("/api/legacy/import", response_model=ImportResponse, tags=["Usuários"])
    def import_legacy(session=Depends(mutating)):
        legacy = Gallery(directory)
        try:
            records = legacy.read()["subjects"]
        except ValueError as error:
            raise DomainError(
                503, "Galeria laboratorial indisponível. Verifique a chave."
            ) from error
        encrypted = {
            key: database.encode_samples(record["samples"][:5]) for key, record in records.items()
        }
        imported = 0
        already_present = 0
        # Nunca sobrescrever cadastro do painel. Em colisão, preservar origem e pedir revisão.
        with database.connect(write=True) as connection:
            for subject_id, record in records.items():
                existing = connection.execute(
                    "SELECT 1 FROM users WHERE subject_id=?", (subject_id,)
                ).fetchone()
                if existing:
                    # Somente a mesma referência previamente importada pode concluir limpeza
                    # de uma operação cuja gravação já tenha sido confirmada.
                    user = database.user(connection, subject_id)
                    existing_samples = database.references(connection).get(subject_id, [])
                    same_samples = len(existing_samples) == 5 and all(
                        np.allclose(a, b, atol=1e-6)
                        for a, b in zip(existing_samples, record["samples"][:5], strict=True)
                    )
                    if (
                        user["consent_version"] != "laboratorio-v1"
                        or user["consent_at"] != record["consent_at"]
                        or not same_samples
                    ):
                        raise DomainError(
                            409,
                            "ID do laboratório já existe no painel. "
                            "Resolva a colisão antes de importar.",
                        )
                    already_present += 1
                    continue
                database.insert_user(
                    connection,
                    subject_id,
                    subject_id,
                    record["level"],
                    record["active"],
                    record["divisions"],
                )
                database.save_samples(
                    connection,
                    subject_id,
                    encrypted[subject_id],
                    record["consent_at"],
                    record["consent_version"],
                )
                imported += 1
        if records:
            try:

                def clear_imported(subjects):
                    for key, expected in records.items():
                        if key in subjects and subjects[key] != expected:
                            raise ValueError("Origem alterada durante a importação.")
                    for key in records:
                        subjects.pop(key, None)

                legacy._change(clear_imported)
            except (ValueError, sqlite3.Error, OSError) as error:
                raise DomainError(
                    503,
                    "Importação gravada, mas limpeza da origem falhou. Repita antes de continuar.",
                ) from error
        return {"imported": imported, "already_present": already_present}

    @app.get("/api/openapi.json", include_in_schema=False)
    def openapi(session=Depends(authenticated)):
        return app.openapi()

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise DomainError(404, "Endpoint não encontrado.")
        root = DIST.resolve()
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root):
            raise DomainError(404, "Arquivo não encontrado.")
        if candidate.is_file():
            return FileResponse(candidate)
        if not (root / "index.html").is_file():
            raise DomainError(
                503, "Interface não compilada. Execute npm ci e npm run build na pasta frontend."
            )
        return FileResponse(root / "index.html")

    generate_openapi = app.openapi

    def contracted_openapi():
        schema = generate_openapi()
        for path in schema["paths"].values():
            for operation in path.values():
                if not isinstance(operation, dict):
                    continue
                # FastAPI representa esquemas de segurança separados como alternativas.
                # Neste contrato, cookie E CSRF são exigidos nas mutações autenticadas.
                security = operation.get("security", [])
                if any("APIKeyHeader" in option for option in security):
                    operation["security"] = [{"APIKeyCookie": [], "APIKeyHeader": []}]
        return schema

    app.openapi = contracted_openapi
    return app
