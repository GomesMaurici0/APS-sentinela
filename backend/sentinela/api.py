import sqlite3
from pathlib import Path

import numpy as np
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from sentinela.access_service import AccessService, registro_tentativa
from sentinela.biometria.models import DEFAULT_MODELS
from sentinela.config import diretorio_dados
from sentinela.database import Database, agora
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
    StatsResponse,
    UserCreate,
    UserPage,
    UserResponse,
    UserUpdate,
)

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class LocalBoundary:
    """Limites de entrada e cabeçalhos aplicados também às respostas de erro."""

    def __init__(self, aplicacao):
        self.app = aplicacao

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        cabecalhos = dict(scope["headers"])
        metodo = scope["method"]
        origem = cabecalhos.get(b"origin")
        host = cabecalhos.get(b"host", b"")
        if origem and origem != scope["scheme"].encode() + b"://" + host:
            return await JSONResponse({"detail": "Origem não autorizada."}, 403)(
                scope, receive, send
            )
        partes = []
        tamanho = 0
        if metodo in ("POST", "PUT", "PATCH", "DELETE"):
            while True:
                mensagem = await receive()
                if mensagem["type"] == "http.disconnect":
                    return
                tamanho += len(mensagem.get("body", b""))
                if tamanho > 8 * 1024 * 1024:
                    return await JSONResponse({"detail": "Corpo excede 8 MiB."}, 413)(
                        scope, receive, send
                    )
                partes.append(mensagem.get("body", b""))
                if not mensagem.get("more_body", False):
                    break
        entregue = False

        async def receber_com_limite():
            nonlocal entregue
            if not entregue and partes:
                entregue = True
                return {"type": "http.request", "body": b"".join(partes), "more_body": False}
            return await receive()

        async def enviar_com_protecao(mensagem):
            if mensagem["type"] == "http.response.start":
                mensagem["headers"] += [
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
            await send(mensagem)

        await self.app(scope, receber_com_limite, enviar_com_protecao)


def criar_aplicacao(
    diretorio: Path | None = None, models: Path = DEFAULT_MODELS, pipeline=None
) -> FastAPI:
    diretorio = diretorio or diretorio_dados()
    banco = Database(diretorio)
    banco.inicializar()
    servico = AccessService(banco, models, pipeline)
    aplicacao = FastAPI(
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
            403: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    aplicacao.state.database = banco
    aplicacao.state.access = servico
    aplicacao.add_middleware(LocalBoundary)
    aplicacao.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

    @aplicacao.exception_handler(DomainError)
    async def tratar_erro_dominio(requisicao: Request, erro: DomainError):
        return JSONResponse({"detail": erro.message}, status_code=erro.status)

    @aplicacao.exception_handler(sqlite3.Error)
    async def tratar_erro_persistencia(requisicao: Request, erro: sqlite3.Error):
        return JSONResponse(
            {"detail": "Persistência indisponível. Nenhuma autorização confirmada."},
            status_code=503,
        )

    @aplicacao.exception_handler(RequestValidationError)
    async def tratar_erro_validacao(requisicao: Request, erro: RequestValidationError):
        # Nunca ecoar input, base64 ou contexto de exceções de validação.
        return JSONResponse(
            {"detail": "Dados inválidos. Confira os campos e o formato das imagens."},
            status_code=422,
        )

    @aplicacao.get(
        "/api/users",
        response_model=UserPage,
        tags=["Usuários"],
        operation_id="list_users_api_users_get",
        summary="List Users",
    )
    def listar_usuarios(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
    ):
        with banco.conectar() as conexao:
            total = conexao.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            identificadores = conexao.execute(
                "SELECT subject_id FROM users ORDER BY subject_id LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
            itens = [banco.obter_usuario(conexao, linha[0]) for linha in identificadores]
        return {"items": itens, "total": total, "offset": offset, "limit": limit}

    @aplicacao.post(
        "/api/users",
        status_code=201,
        response_model=UserResponse,
        tags=["Usuários"],
        operation_id="create_user_api_users_post",
        summary="Create User",
    )
    def criar_usuario(corpo: UserCreate):
        with banco.conectar(write=True) as conexao:
            banco.inserir_usuario(
                conexao,
                corpo.subject_id,
                corpo.display_name,
                corpo.level,
                corpo.active,
                corpo.divisions,
            )
            return banco.obter_usuario(conexao, corpo.subject_id)

    @aplicacao.get(
        "/api/users/{subject_id}",
        response_model=UserResponse,
        tags=["Usuários"],
        operation_id="get_user_api_users__subject_id__get",
        summary="Get User",
    )
    def consultar_usuario(subject_id: str):
        with banco.conectar() as conexao:
            return banco.obter_usuario(conexao, subject_id)

    @aplicacao.put(
        "/api/users/{subject_id}",
        response_model=UserResponse,
        tags=["Usuários"],
        operation_id="update_user_api_users__subject_id__put",
        summary="Update User",
    )
    def atualizar_usuario(subject_id: str, corpo: UserUpdate):
        with banco.conectar(write=True) as conexao:
            banco.obter_usuario(conexao, subject_id)
            conexao.execute(
                "UPDATE users SET display_name=?, level=?, active=?, updated_at=? "
                "WHERE subject_id=?",
                (corpo.display_name, corpo.level, int(corpo.active), agora(), subject_id),
            )
            conexao.execute("DELETE FROM user_divisions WHERE subject_id=?", (subject_id,))
            conexao.executemany(
                "INSERT INTO user_divisions VALUES (?, ?)",
                [(subject_id, divisao) for divisao in corpo.divisions],
            )
            return banco.obter_usuario(conexao, subject_id)

    def limpar_galeria_legada(subject_id):
        # A exclusão confirmada não deve deixar cópia ativa no laboratório legado.
        galeria_legada = Gallery(diretorio)
        try:
            if subject_id in galeria_legada.ler()["subjects"]:
                galeria_legada.excluir(subject_id)
        except ValueError as erro:
            raise DomainError(503, "Não foi possível excluir a cópia do laboratório.") from erro

    @aplicacao.delete(
        "/api/users/{subject_id}",
        status_code=204,
        tags=["Usuários"],
        operation_id="delete_user_api_users__subject_id__delete",
        summary="Delete User",
    )
    def excluir_usuario(subject_id: str):
        with banco.conectar() as conexao:
            banco.obter_usuario(conexao, subject_id)
        limpar_galeria_legada(subject_id)
        with banco.conectar(write=True) as conexao:
            banco.obter_usuario(conexao, subject_id)
            conexao.execute("DELETE FROM users WHERE subject_id=?", (subject_id,))

    @aplicacao.post(
        "/api/users/{subject_id}/biometrics",
        response_model=UserResponse,
        tags=["Biometria"],
        operation_id="enroll_api_users__subject_id__biometrics_post",
        summary="Enroll",
    )
    def cadastrar_biometria(subject_id: str, corpo: Enrollment):
        servico.cadastrar_biometria(subject_id, corpo.images)
        with banco.conectar() as conexao:
            return banco.obter_usuario(conexao, subject_id)

    @aplicacao.delete(
        "/api/users/{subject_id}/biometrics",
        status_code=204,
        tags=["Biometria"],
        operation_id="delete_biometrics_api_users__subject_id__biometrics_delete",
        summary="Delete Biometrics",
    )
    def excluir_biometria(subject_id: str):
        with banco.conectar() as conexao:
            banco.obter_usuario(conexao, subject_id)
        limpar_galeria_legada(subject_id)
        with banco.conectar(write=True) as conexao:
            banco.obter_usuario(conexao, subject_id)
            conexao.execute("DELETE FROM biometric_references WHERE subject_id=?", (subject_id,))
            conexao.execute(
                "UPDATE users SET consent_at=NULL, consent_version=NULL, updated_at=? "
                "WHERE subject_id=?",
                (agora(), subject_id),
            )

    @aplicacao.post(
        "/api/biometrics/analyze",
        response_model=CaptureResponse,
        tags=["Biometria"],
        operation_id="analyze_api_biometrics_analyze_post",
        summary="Analyze",
    )
    def analisar(corpo: ImageInput):
        return servico.analisar(corpo.image)

    @aplicacao.post(
        "/api/attempts",
        response_model=DecisionResponse,
        tags=["Acessos"],
        operation_id="attempt_api_attempts_post",
        summary="Attempt",
    )
    def avaliar_acesso(corpo: AttemptInput):
        return servico.avaliar_acesso(corpo.image, corpo.requested_level, corpo.division)

    @aplicacao.get(
        "/api/attempts",
        response_model=AttemptPage,
        tags=["Acessos"],
        operation_id="list_attempts_api_attempts_get",
        summary="List Attempts",
    )
    def listar_tentativas(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        granted: bool | None = None,
    ):
        condicao_sql = " WHERE granted=?" if granted is not None else ""
        parametros = (int(granted),) if granted is not None else ()
        with banco.conectar() as conexao:
            total = conexao.execute(
                "SELECT COUNT(*) FROM attempts" + condicao_sql, parametros
            ).fetchone()[0]
            linhas = conexao.execute(
                "SELECT * FROM attempts" + condicao_sql + " ORDER BY id DESC LIMIT ? OFFSET ?",
                (*parametros, limit, offset),
            ).fetchall()
        return {
            "items": [registro_tentativa(linha) for linha in linhas],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    @aplicacao.get(
        "/api/stats",
        response_model=StatsResponse,
        tags=["Acessos"],
        operation_id="stats_api_stats_get",
        summary="Stats",
    )
    def consultar_indicadores():
        with banco.conectar() as conexao:
            usuarios = conexao.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            cadastrados = conexao.execute("SELECT COUNT(*) FROM biometric_references").fetchone()[0]
            tentativas, granted = conexao.execute(
                "SELECT COUNT(*), COALESCE(SUM(granted),0) FROM attempts"
            ).fetchone()
        return {
            "users": usuarios,
            "enrolled": cadastrados,
            "attempts": tentativas,
            "granted": granted,
            "denied": tentativas - granted,
        }

    @aplicacao.post(
        "/api/legacy/import",
        response_model=ImportResponse,
        tags=["Usuários"],
        operation_id="import_legacy_api_legacy_import_post",
        summary="Import Legacy",
    )
    def importar_legado():
        galeria_legada = Gallery(diretorio)
        try:
            registros = galeria_legada.ler()["subjects"]
        except ValueError as erro:
            raise DomainError(
                503, "Galeria laboratorial indisponível. Verifique a chave."
            ) from erro
        conteudo_cifrado = {
            chave: banco.cifrar_amostras(registro["samples"][:5])
            for chave, registro in registros.items()
        }
        importados = 0
        ja_presentes = 0
        # Nunca sobrescrever cadastro do painel. Em colisão, preservar origem e pedir revisão.
        with banco.conectar(write=True) as conexao:
            for subject_id, registro in registros.items():
                existente = conexao.execute(
                    "SELECT 1 FROM users WHERE subject_id=?", (subject_id,)
                ).fetchone()
                if existente:
                    # Somente a mesma referência previamente importada pode concluir limpeza
                    # de uma operação cuja gravação já tenha sido confirmada.
                    usuario = banco.obter_usuario(conexao, subject_id)
                    amostras_existentes = banco.obter_referencias(conexao).get(subject_id, [])
                    mesmas_amostras = len(amostras_existentes) == 5 and all(
                        np.allclose(vetor_a, vetor_b, atol=1e-6)
                        for vetor_a, vetor_b in zip(
                            amostras_existentes, registro["samples"][:5], strict=True
                        )
                    )
                    if (
                        usuario["consent_version"] != "laboratorio-v1"
                        or usuario["consent_at"] != registro["consent_at"]
                        or not mesmas_amostras
                    ):
                        raise DomainError(
                            409,
                            "ID do laboratório já existe no painel. "
                            "Resolva a colisão antes de importar.",
                        )
                    ja_presentes += 1
                    continue
                banco.inserir_usuario(
                    conexao,
                    subject_id,
                    subject_id,
                    registro["level"],
                    registro["active"],
                    registro["divisions"],
                )
                banco.salvar_amostras(
                    conexao,
                    subject_id,
                    conteudo_cifrado[subject_id],
                    registro["consent_at"],
                    registro["consent_version"],
                )
                importados += 1
        if registros:
            try:

                def limpar_importados(pessoas):
                    for chave, esperado in registros.items():
                        if chave in pessoas and pessoas[chave] != esperado:
                            raise ValueError("Origem alterada durante a importação.")
                    for chave in registros:
                        pessoas.pop(chave, None)

                galeria_legada._alterar(limpar_importados)
            except (ValueError, sqlite3.Error, OSError) as erro:
                raise DomainError(
                    503,
                    "Importação gravada, mas limpeza da origem falhou. Repita antes de continuar.",
                ) from erro
        return {"imported": importados, "already_present": ja_presentes}

    @aplicacao.get("/api/openapi.json", include_in_schema=False)
    def obter_contrato():
        return aplicacao.openapi()

    @aplicacao.get("/{path:path}", include_in_schema=False)
    def servir_interface(path: str):
        if path.startswith("api/"):
            raise DomainError(404, "Endpoint não encontrado.")
        raiz = DIST.resolve()
        candidato = (raiz / path).resolve()
        if not candidato.is_relative_to(raiz):
            raise DomainError(404, "Arquivo não encontrado.")
        if candidato.is_file():
            return FileResponse(candidato)
        if not (raiz / "index.html").is_file():
            raise DomainError(
                503, "Interface não compilada. Execute npm ci e npm run build na pasta frontend."
            )
        return FileResponse(raiz / "index.html")

    return aplicacao
