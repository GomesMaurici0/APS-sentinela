
import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from cryptography.fernet import Fernet, InvalidToken

from sentinela.autorizacao import UserPermission
from sentinela.biometria.models import MODEL_ID
from sentinela.biometria.pipeline import normalized_embedding

MINIMUM_SAMPLES = 5


class Gallery:

    def __init__(self, directory: Path):
        self.directory = directory
        self.database = directory / "gallery.db"
        self.key_path = directory / "gallery.key"

    def _cipher(self, create=False) -> Fernet:
        if not self.key_path.exists():
            if self.database.exists() or not create:
                raise ValueError("Chave biométrica ausente; não será recriada sobre uma galeria.")
            self.directory.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(Fernet.generate_key())
        return Fernet(self.key_path.read_bytes())

    def _decode(self, payload: bytes, cipher: Fernet) -> dict:
        try:
            value = json.loads(cipher.decrypt(payload))
        except (InvalidToken, ValueError, UnicodeDecodeError) as error:
            raise ValueError(
                "Galeria corrompida ou chave incorreta. Acesso interrompido."
            ) from error
        try:
            if value.get("schema") != 1 or value.get("model") != MODEL_ID:
                raise ValueError("Galeria incompatível com esta versão/modelo.")
            for record in value["subjects"].values():
                UserPermission(record["level"], frozenset(record["divisions"]), record["active"])
                if not record["consent_at"] or len(record["samples"]) < MINIMUM_SAMPLES:
                    raise ValueError("Cadastro sem consentimento ou amostras suficientes.")
                for sample in record["samples"]:
                    normalized_embedding(sample)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError("Estrutura da galeria inválida. Acesso interrompido.") from error
        return value

    @staticmethod
    def _empty() -> dict:
        return {"schema": 1, "model": MODEL_ID, "subjects": {}}

    def read(self) -> dict:
        if not self.database.exists():
            return self._empty()
        cipher = self._cipher()
        with sqlite3.connect(self.database) as connection:
            row = connection.execute("SELECT payload FROM vault WHERE id=1").fetchone()
        if row is None:
            raise ValueError("Galeria incompleta. Acesso interrompido.")
        return self._decode(row[0], cipher)

    def _change(self, operation):
        cipher = self._cipher(create=True)
        with sqlite3.connect(self.database, timeout=5) as connection:
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS vault (id INTEGER PRIMARY KEY, payload BLOB)"
            )
            row = connection.execute("SELECT payload FROM vault WHERE id=1").fetchone()
            value = self._empty() if row is None else self._decode(row[0], cipher)
            operation(value["subjects"])
            payload = cipher.encrypt(json.dumps(value, allow_nan=False).encode("utf-8"))
            connection.execute("INSERT OR REPLACE INTO vault VALUES (1, ?)", (payload,))

    def enroll(
        self, subject_id: str, permission: UserPermission, samples: list[np.ndarray], consent: bool
    ):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", subject_id):
            raise ValueError("Use identificador fictício com 1–40 letras, números, _ ou -.")
        if not consent:
            raise ValueError("Consentimento obrigatório para cadastro biométrico.")
        if len(samples) < MINIMUM_SAMPLES:
            raise ValueError(f"São necessárias pelo menos {MINIMUM_SAMPLES} amostras.")
        vectors = [normalized_embedding(sample).tolist() for sample in samples]

        def insert(subjects):
            if subject_id in subjects:
                raise ValueError("Identificador já cadastrado. Exclua antes de recadastrar.")
            subjects[subject_id] = {
                "level": permission.level,
                "divisions": sorted(permission.divisions),
                "active": permission.active,
                "samples": vectors,
                "consent_at": datetime.now(UTC).isoformat(),
                "consent_version": "laboratorio-v1",
            }

        self._change(insert)

    def delete(self, subject_id: str):
        if not self.database.exists():
            raise ValueError("Galeria vazia.")

        def remove(subjects):
            if subject_id not in subjects:
                raise ValueError("Identificador não cadastrado.")
            del subjects[subject_id]

        self._change(remove)

    def references(self) -> dict[str, list[np.ndarray]]:
        return {
            subject_id: [np.asarray(sample, dtype=np.float32) for sample in record["samples"]]
            for subject_id, record in self.read()["subjects"].items()
            if record["active"]
        }
