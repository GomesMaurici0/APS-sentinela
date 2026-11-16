import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from cryptography.fernet import Fernet, InvalidToken

from sentinela.autorizacao import UserPermission
from sentinela.biometria.models import MODEL_ID
from sentinela.biometria.pipeline import normalized_embedding
from sentinela.errors import DomainError


def now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "sentinela.db"
        self.key_path = directory / "biometrics.key"
        self._key_lock = threading.Lock()

    @contextmanager
    def connect(self, write=False):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA secure_delete=ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise ValueError("Banco foi criado por uma versão mais recente do sistema.")
            if version == 0:
                migration = Path(__file__).parent / "migrations" / "001_initial.sql"
                connection.executescript("BEGIN IMMEDIATE;\n" + migration.read_text("utf-8"))
            if version < 2:
                migration = Path(__file__).parent / "migrations" / "002_remove_admin_auth.sql"
                connection.executescript("BEGIN IMMEDIATE;\n" + migration.read_text("utf-8"))

    def cipher(self) -> Fernet:
        with self._key_lock:
            if not self.key_path.exists():
                with self.connect() as connection:
                    count = connection.execute(
                        "SELECT COUNT(*) FROM biometric_references"
                    ).fetchone()[0]
                if count:
                    raise DomainError(503, "Chave biométrica ausente. Operação interrompida.")
                try:
                    descriptor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    pass
                else:
                    with os.fdopen(descriptor, "wb") as output:
                        output.write(Fernet.generate_key())
            try:
                return Fernet(self.key_path.read_bytes())
            except (ValueError, OSError) as error:
                raise DomainError(503, "Chave biométrica indisponível.") from error

    def encode_samples(self, samples) -> bytes:
        vectors = [normalized_embedding(sample).tolist() for sample in samples]
        return self.cipher().encrypt(json.dumps(vectors, allow_nan=False).encode())

    def references(self, connection) -> dict[str, list[np.ndarray]]:
        rows = connection.execute("SELECT * FROM biometric_references").fetchall()
        if not rows:
            return {}
        cipher = self.cipher()
        result = {}
        for row in rows:
            if row["model_id"] != MODEL_ID:
                raise DomainError(503, "Referências incompatíveis com o modelo atual.")
            try:
                vectors = json.loads(cipher.decrypt(row["encrypted_samples"]))
                if not isinstance(vectors, list) or len(vectors) < 5:
                    raise ValueError("Referências incompletas")
                result[row["subject_id"]] = [normalized_embedding(sample) for sample in vectors]
            except (InvalidToken, ValueError, TypeError) as error:
                raise DomainError(
                    503, "Referências biométricas inválidas ou chave incorreta."
                ) from error
        return result

    @staticmethod
    def user(connection, subject_id: str) -> dict:
        row = connection.execute("SELECT * FROM users WHERE subject_id=?", (subject_id,)).fetchone()
        if row is None:
            raise DomainError(404, "Usuário não encontrado.")
        value = dict(row)
        value["active"] = bool(value["active"])
        value["divisions"] = [
            item[0]
            for item in connection.execute(
                "SELECT division FROM user_divisions WHERE subject_id=? ORDER BY division",
                (subject_id,),
            )
        ]
        reference = connection.execute(
            "SELECT sample_count FROM biometric_references WHERE subject_id=?", (subject_id,)
        ).fetchone()
        value["sample_count"] = reference[0] if reference else 0
        return value

    @staticmethod
    def permission(user: dict) -> UserPermission:
        return UserPermission(user["level"], frozenset(user["divisions"]), user["active"])

    @staticmethod
    def insert_user(connection, subject_id, display_name, level, active, divisions):
        stamp = now()
        try:
            connection.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
                (subject_id, display_name, level, int(active), stamp, stamp),
            )
        except sqlite3.IntegrityError as error:
            raise DomainError(409, "Identificador já cadastrado.") from error
        connection.executemany(
            "INSERT INTO user_divisions VALUES (?, ?)",
            [(subject_id, division) for division in divisions],
        )

    @staticmethod
    def save_samples(
        connection, subject_id, encrypted, consent_at=None, consent_version="cadastro-v1"
    ):
        connection.execute(
            "INSERT OR REPLACE INTO biometric_references VALUES (?, ?, ?, ?, ?)",
            (subject_id, MODEL_ID, encrypted, 5, now()),
        )
        connection.execute(
            "UPDATE users SET consent_at=?, consent_version=?, updated_at=? WHERE subject_id=?",
            (consent_at or now(), consent_version, now(), subject_id),
        )
