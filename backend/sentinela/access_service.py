import base64
import binascii
import io
import json
import threading
import time
import warnings
from contextlib import contextmanager
from dataclasses import asdict

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from sentinela.autorizacao import AccessDecision, autorizar
from sentinela.biometria.matching import MatchStatus, identificar
from sentinela.biometria.models import DEFAULT_MODELS, MODEL_ID
from sentinela.biometria.pipeline import Analysis, CaptureStatus, FacePipeline
from sentinela.config import BiometricConfig
from sentinela.database import Database, agora
from sentinela.errors import DomainError


def decodificar_imagem(encoded: str) -> np.ndarray:
    try:
        dados_brutos = base64.b64decode(encoded, validate=True)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(dados_brutos)) as imagem:
                if imagem.format not in ("JPEG", "PNG") or not (
                    16 <= imagem.width <= 960 and 16 <= imagem.height <= 960
                ):
                    raise ValueError("Dimensões ou formato inválidos")
                imagem.verify()
        quadro = cv2.imdecode(np.frombuffer(dados_brutos, np.uint8), cv2.IMREAD_COLOR)
        if quadro is None:
            raise ValueError("Imagem inválida")
        return quadro
    except (
        ValueError,
        OSError,
        binascii.Error,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        cv2.error,
    ) as erro:
        raise DomainError(
            422, "Imagem inválida. Use JPEG/PNG com dimensões entre 16 e 960 px."
        ) from erro


def dados_captura(resultado: Analysis) -> dict:
    rosto_alinhado = None
    if resultado.aligned is not None:
        sucesso, encoded = cv2.imencode(".jpg", resultado.aligned)
        if sucesso:
            rosto_alinhado = base64.b64encode(encoded).decode("ascii")
    return {
        "status": resultado.status.value,
        "brightness": resultado.brightness,
        "sharpness": resultado.sharpness,
        "elapsed_ms": round(resultado.elapsed_ms, 2),
        "width": resultado.frame.shape[1] if resultado.frame is not None else None,
        "height": resultado.frame.shape[0] if resultado.frame is not None else None,
        "faces": resultado.faces.tolist() if resultado.faces is not None else [],
        "aligned_image": rosto_alinhado,
    }


def registro_tentativa(linha) -> dict:
    registro = dict(linha)
    registro["granted"] = bool(registro["granted"])
    registro["config"] = json.loads(registro.pop("config_json"))
    return registro


class AccessService:
    def __init__(self, banco: Database, modelos=DEFAULT_MODELS, motor_facial=None):
        self.database = banco
        self.models = modelos
        self.pipeline = motor_facial
        self.config = motor_facial.config if motor_facial else BiometricConfig()
        self.lock = threading.Lock()
        self.rate_lock = threading.Lock()
        self.last_attempt = 0.0

    @contextmanager
    def processamento_exclusivo(self):
        if not self.lock.acquire(timeout=1):
            raise DomainError(429, "Processamento ocupado. Aguarde e tente novamente.")
        try:
            if self.pipeline is None:
                self.pipeline = FacePipeline(self.models, self.config)
            yield
        except (cv2.error, ValueError, OSError) as erro:
            raise DomainError(
                503, "Motor biométrico indisponível. Verifique modelos e chave."
            ) from erro
        finally:
            self.lock.release()

    def analisar(self, encoded: str) -> dict:
        quadro = decodificar_imagem(encoded)
        with self.processamento_exclusivo():
            return dados_captura(self.pipeline.analisar(quadro))

    def cadastrar_biometria(self, identificador: str, imagens: list[str]):
        with self.database.conectar() as conexao:
            self.database.obter_usuario(conexao, identificador)
        resultados = []
        with self.processamento_exclusivo():
            for indice, encoded in enumerate(imagens, 1):
                resultado = self.pipeline.analisar(decodificar_imagem(encoded))
                if resultado.status != CaptureStatus.OK:
                    raise DomainError(422, f"Amostra {indice} rejeitada: {resultado.status.value}.")
                resultados.append(resultado.embedding)
        conteudo_cifrado = self.database.cifrar_amostras(resultados)
        with self.database.conectar(write=True) as conexao:
            self.database.obter_usuario(conexao, identificador)
            referencias = self.database.obter_referencias(conexao)
            referencias.pop(identificador, None)
            for amostra in resultados:
                identificacao = identificar(amostra, referencias, self.config)
                if (
                    identificacao.similarity is not None
                    and identificacao.similarity >= self.config.similarity_threshold
                ):
                    raise DomainError(
                        409, "Rosto semelhante a outro cadastro. Revise as identidades."
                    )
            self.database.salvar_amostras(conexao, identificador, conteudo_cifrado)

    def avaliar_acesso(self, imagem: str, nivel_solicitado: int, divisao: str | None) -> dict:
        inicio = time.perf_counter()
        with self.rate_lock:
            if time.monotonic() - self.last_attempt < 0.8:
                raise DomainError(429, "Aguarde um segundo entre tentativas.")
            self.last_attempt = time.monotonic()
        resultado = None
        identificacao = None
        falha_motor = False
        try:
            quadro = decodificar_imagem(imagem)
            with self.processamento_exclusivo():
                resultado = self.pipeline.analisar(quadro)
        except DomainError as erro:
            if erro.status == 429:
                raise
            falha_motor = erro.status == 503
            motivo = "falha_biometrica" if falha_motor else "imagem_invalida"
        else:
            motivo = resultado.status.value
        decisao = AccessDecision(False, motivo)
        identificador = None
        # Permissões, referências e auditoria usam a mesma transação: alterações de cadastro
        # não podem intercalar entre autorização e persistência da decisão.
        with self.database.conectar(write=True) as conexao:
            if resultado is not None and resultado.status == CaptureStatus.OK:
                try:
                    identificacao = identificar(
                        resultado.embedding, self.database.obter_referencias(conexao), self.config
                    )
                    decisao = AccessDecision(False, identificacao.status.value)
                    if identificacao.status == MatchStatus.MATCHED:
                        identificador = identificacao.subject_id
                        usuario = self.database.obter_usuario(conexao, identificador)
                        decisao = autorizar(
                            self.database.obter_permissao(usuario), nivel_solicitado, divisao
                        )
                except (DomainError, ValueError):
                    falha_motor = True
                    identificador = None
                    identificacao = None
                    decisao = AccessDecision(False, "falha_biometrica")
            tempo_ms = round((time.perf_counter() - inicio) * 1000, 2)
            cursor_sql = conexao.execute(
                "INSERT INTO attempts (occurred_at, subject_id, requested_level, "
                "division, granted, "
                "reason, similarity, margin, elapsed_ms, model_id, config_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    agora(),
                    identificador,
                    nivel_solicitado,
                    divisao,
                    int(decisao.granted),
                    decisao.reason,
                    identificacao.similarity if identificacao else None,
                    identificacao.margin if identificacao else None,
                    tempo_ms,
                    MODEL_ID,
                    json.dumps(asdict(self.config)),
                ),
            )
            linha = conexao.execute(
                "SELECT * FROM attempts WHERE id=?", (cursor_sql.lastrowid,)
            ).fetchone()
            saida = registro_tentativa(linha)
        if falha_motor:
            raise DomainError(503, "Motor biométrico indisponível. Tentativa negada e registrada.")
        saida["capture"] = dados_captura(resultado) if resultado else None
        return saida
