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

from sentinela.autorizacao import AccessDecision, authorize
from sentinela.biometria.matching import MatchStatus, identify
from sentinela.biometria.models import DEFAULT_MODELS, MODEL_ID
from sentinela.biometria.pipeline import Analysis, CaptureStatus, FacePipeline
from sentinela.config import BiometricConfig
from sentinela.database import Database, now
from sentinela.errors import DomainError


def decode_image(encoded: str) -> np.ndarray:
    try:
        raw = base64.b64decode(encoded, validate=True)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ("JPEG", "PNG") or not (
                    16 <= image.width <= 960 and 16 <= image.height <= 960
                ):
                    raise ValueError("Dimensões ou formato inválidos")
                image.verify()
        frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("Imagem inválida")
        return frame
    except (
        ValueError,
        OSError,
        binascii.Error,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        cv2.error,
    ) as error:
        raise DomainError(
            422, "Imagem inválida. Use JPEG/PNG com dimensões entre 16 e 960 px."
        ) from error


def capture_data(result: Analysis) -> dict:
    aligned = None
    if result.aligned is not None:
        ok, encoded = cv2.imencode(".jpg", result.aligned)
        if ok:
            aligned = base64.b64encode(encoded).decode("ascii")
    return {
        "status": result.status.value,
        "brightness": result.brightness,
        "sharpness": result.sharpness,
        "elapsed_ms": round(result.elapsed_ms, 2),
        "width": result.frame.shape[1] if result.frame is not None else None,
        "height": result.frame.shape[0] if result.frame is not None else None,
        "faces": result.faces.tolist() if result.faces is not None else [],
        "aligned_image": aligned,
    }


def attempt_record(row) -> dict:
    record = dict(row)
    record["granted"] = bool(record["granted"])
    record["config"] = json.loads(record.pop("config_json"))
    return record


class AccessService:
    def __init__(self, database: Database, models=DEFAULT_MODELS, pipeline=None):
        self.database = database
        self.models = models
        self.pipeline = pipeline
        self.config = pipeline.config if pipeline else BiometricConfig()
        self.lock = threading.Lock()
        self.rate_lock = threading.Lock()
        self.last_attempt = 0.0

    @contextmanager
    def exclusive(self):
        if not self.lock.acquire(timeout=1):
            raise DomainError(429, "Processamento ocupado. Aguarde e tente novamente.")
        try:
            if self.pipeline is None:
                self.pipeline = FacePipeline(self.models, self.config)
            yield
        except (cv2.error, ValueError, OSError) as error:
            raise DomainError(
                503, "Motor biométrico indisponível. Verifique modelos e chave."
            ) from error
        finally:
            self.lock.release()

    def analyze(self, encoded: str) -> dict:
        frame = decode_image(encoded)
        with self.exclusive():
            return capture_data(self.pipeline.analyze(frame))

    def enroll(self, subject_id: str, images: list[str]):
        with self.database.connect() as connection:
            self.database.user(connection, subject_id)
        results = []
        with self.exclusive():
            for index, encoded in enumerate(images, 1):
                result = self.pipeline.analyze(decode_image(encoded))
                if result.status != CaptureStatus.OK:
                    raise DomainError(422, f"Amostra {index} rejeitada: {result.status.value}.")
                results.append(result.embedding)
        encrypted = self.database.encode_samples(results)
        with self.database.connect(write=True) as connection:
            self.database.user(connection, subject_id)
            references = self.database.references(connection)
            references.pop(subject_id, None)
            for sample in results:
                match = identify(sample, references, self.config)
                if (
                    match.similarity is not None
                    and match.similarity >= self.config.similarity_threshold
                ):
                    raise DomainError(
                        409, "Rosto semelhante a outro cadastro. Revise as identidades."
                    )
            self.database.save_samples(connection, subject_id, encrypted)

    def attempt(self, image: str, requested_level: int, division: str | None) -> dict:
        start = time.perf_counter()
        with self.rate_lock:
            if time.monotonic() - self.last_attempt < 0.8:
                raise DomainError(429, "Aguarde um segundo entre tentativas.")
            self.last_attempt = time.monotonic()
        result = None
        match = None
        engine_failure = False
        try:
            frame = decode_image(image)
            with self.exclusive():
                result = self.pipeline.analyze(frame)
        except DomainError as error:
            if error.status == 429:
                raise
            engine_failure = error.status == 503
            reason = "falha_biometrica" if engine_failure else "imagem_invalida"
        else:
            reason = result.status.value
        decision = AccessDecision(False, reason)
        subject_id = None
        # Permissões, referências e auditoria usam a mesma transação: alterações de cadastro
        # não podem intercalar entre autorização e persistência da decisão.
        with self.database.connect(write=True) as connection:
            if result is not None and result.status == CaptureStatus.OK:
                try:
                    match = identify(
                        result.embedding, self.database.references(connection), self.config
                    )
                    decision = AccessDecision(False, match.status.value)
                    if match.status == MatchStatus.MATCHED:
                        subject_id = match.subject_id
                        user = self.database.user(connection, subject_id)
                        decision = authorize(
                            self.database.permission(user), requested_level, division
                        )
                except (DomainError, ValueError):
                    engine_failure = True
                    subject_id = None
                    match = None
                    decision = AccessDecision(False, "falha_biometrica")
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            cursor = connection.execute(
                "INSERT INTO attempts (occurred_at, subject_id, requested_level, "
                "division, granted, "
                "reason, similarity, margin, elapsed_ms, model_id, config_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    now(),
                    subject_id,
                    requested_level,
                    division,
                    int(decision.granted),
                    decision.reason,
                    match.similarity if match else None,
                    match.margin if match else None,
                    elapsed_ms,
                    MODEL_ID,
                    json.dumps(asdict(self.config)),
                ),
            )
            row = connection.execute(
                "SELECT * FROM attempts WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
            output = attempt_record(row)
        if engine_failure:
            raise DomainError(503, "Motor biométrico indisponível. Tentativa negada e registrada.")
        output["capture"] = capture_data(result) if result else None
        return output
