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
from sentinela.biometria.pipeline import normalizar_vetor_facial

MINIMUM_SAMPLES = 5


class Gallery:
    def __init__(self, diretorio: Path):
        self.directory = diretorio
        self.database = diretorio / "gallery.db"
        self.key_path = diretorio / "gallery.key"

    def _cifrador(self, create=False) -> Fernet:
        if not self.key_path.exists():
            if self.database.exists() or not create:
                raise ValueError("Chave biométrica ausente; não será recriada sobre uma galeria.")
            self.directory.mkdir(parents=True, exist_ok=True)
            try:
                descritor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descritor, "wb") as saida:
                    saida.write(Fernet.generate_key())
        return Fernet(self.key_path.read_bytes())

    def _decodificar(self, conteudo: bytes, cifrador: Fernet) -> dict:
        try:
            valor = json.loads(cifrador.decrypt(conteudo))
        except (InvalidToken, ValueError, UnicodeDecodeError) as erro:
            raise ValueError(
                "Galeria corrompida ou chave incorreta. Acesso interrompido."
            ) from erro
        try:
            if valor.get("schema") != 1 or valor.get("model") != MODEL_ID:
                raise ValueError("Galeria incompatível com esta versão/modelo.")
            for registro in valor["subjects"].values():
                UserPermission(
                    registro["level"], frozenset(registro["divisions"]), registro["active"]
                )
                if not registro["consent_at"] or len(registro["samples"]) < MINIMUM_SAMPLES:
                    raise ValueError("Cadastro sem consentimento ou amostras suficientes.")
                for amostra in registro["samples"]:
                    normalizar_vetor_facial(amostra)
        except (KeyError, TypeError, AttributeError) as erro:
            raise ValueError("Estrutura da galeria inválida. Acesso interrompido.") from erro
        return valor

    @staticmethod
    def _vazia() -> dict:
        return {"schema": 1, "model": MODEL_ID, "subjects": {}}

    def ler(self) -> dict:
        if not self.database.exists():
            return self._vazia()
        cifrador = self._cifrador()
        with sqlite3.connect(self.database) as conexao:
            linha = conexao.execute("SELECT payload FROM vault WHERE id=1").fetchone()
        if linha is None:
            raise ValueError("Galeria incompleta. Acesso interrompido.")
        return self._decodificar(linha[0], cifrador)

    def _alterar(self, operacao):
        cifrador = self._cifrador(create=True)
        with sqlite3.connect(self.database, timeout=5) as conexao:
            conexao.execute("PRAGMA secure_delete=ON")
            conexao.execute("BEGIN IMMEDIATE")
            conexao.execute(
                "CREATE TABLE IF NOT EXISTS vault (id INTEGER PRIMARY KEY, payload BLOB)"
            )
            linha = conexao.execute("SELECT payload FROM vault WHERE id=1").fetchone()
            valor = self._vazia() if linha is None else self._decodificar(linha[0], cifrador)
            operacao(valor["subjects"])
            conteudo = cifrador.encrypt(json.dumps(valor, allow_nan=False).encode("utf-8"))
            conexao.execute("INSERT OR REPLACE INTO vault VALUES (1, ?)", (conteudo,))

    def cadastrar_biometria(
        self,
        identificador: str,
        permissao: UserPermission,
        amostras: list[np.ndarray],
        consent: bool,
    ):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", identificador):
            raise ValueError("Use identificador fictício com 1–40 letras, números, _ ou -.")
        if not consent:
            raise ValueError("Consentimento obrigatório para cadastro biométrico.")
        if len(amostras) < MINIMUM_SAMPLES:
            raise ValueError(f"São necessárias pelo menos {MINIMUM_SAMPLES} amostras.")
        vetores = [normalizar_vetor_facial(amostra).tolist() for amostra in amostras]

        def inserir(pessoas):
            if identificador in pessoas:
                raise ValueError("Identificador já cadastrado. Exclua antes de recadastrar.")
            pessoas[identificador] = {
                "level": permissao.level,
                "divisions": sorted(permissao.divisions),
                "active": permissao.active,
                "samples": vetores,
                "consent_at": datetime.now(UTC).isoformat(),
                "consent_version": "laboratorio-v1",
            }

        self._alterar(inserir)

    def excluir(self, identificador: str):
        if not self.database.exists():
            raise ValueError("Galeria vazia.")

        def remover(pessoas):
            if identificador not in pessoas:
                raise ValueError("Identificador não cadastrado.")
            del pessoas[identificador]

        self._alterar(remover)

    def obter_referencias(self) -> dict[str, list[np.ndarray]]:
        return {
            identificador: [
                np.asarray(amostra, dtype=np.float32) for amostra in registro["samples"]
            ]
            for identificador, registro in self.ler()["subjects"].items()
            if registro["active"]
        }
