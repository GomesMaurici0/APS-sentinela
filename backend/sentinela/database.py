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
from sentinela.biometria.pipeline import normalizar_vetor_facial
from sentinela.errors import DomainError


def agora() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, diretorio: Path):
        self.directory = diretorio
        self.path = diretorio / "sentinela.db"
        self.key_path = diretorio / "biometrics.key"
        self._key_lock = threading.Lock()

    @contextmanager
    def conectar(self, write=False):
        conexao = sqlite3.connect(self.path, timeout=5)
        conexao.row_factory = sqlite3.Row
        conexao.execute("PRAGMA foreign_keys=ON")
        conexao.execute("PRAGMA secure_delete=ON")
        try:
            if write:
                conexao.execute("BEGIN IMMEDIATE")
            yield conexao
            conexao.commit()
        except BaseException:
            conexao.rollback()
            raise
        finally:
            conexao.close()

    def inicializar(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with self.conectar() as conexao:
            versao = conexao.execute("PRAGMA user_version").fetchone()[0]
            if versao > 3:
                raise ValueError("Banco foi criado por uma versão mais recente do sistema.")
            if versao == 0:
                migracao = Path(__file__).parent / "migrations" / "001_initial.sql"
                conexao.executescript("BEGIN IMMEDIATE;\n" + migracao.read_text("utf-8"))
            if versao < 2:
                migracao = Path(__file__).parent / "migrations" / "002_remove_admin_auth.sql"
                conexao.executescript("BEGIN IMMEDIATE;\n" + migracao.read_text("utf-8"))
            if versao < 3:
                migracao = Path(__file__).parent / "migrations" / "003_tabelas_em_portugues.sql"
                conexao.executescript("BEGIN IMMEDIATE;\n" + migracao.read_text("utf-8"))

    def cifrador(self) -> Fernet:
        with self._key_lock:
            if not self.key_path.exists():
                with self.conectar() as conexao:
                    quantidade = conexao.execute(
                        "SELECT COUNT(*) FROM referencias_biometricas"
                    ).fetchone()[0]
                if quantidade:
                    raise DomainError(503, "Chave biométrica ausente. Operação interrompida.")
                try:
                    descritor = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    pass
                else:
                    with os.fdopen(descritor, "wb") as saida:
                        saida.write(Fernet.generate_key())
            try:
                return Fernet(self.key_path.read_bytes())
            except (ValueError, OSError) as erro:
                raise DomainError(503, "Chave biométrica indisponível.") from erro

    def cifrar_amostras(self, amostras) -> bytes:
        vetores = [normalizar_vetor_facial(amostra).tolist() for amostra in amostras]
        return self.cifrador().encrypt(json.dumps(vetores, allow_nan=False).encode())

    def obter_referencias(self, conexao) -> dict[str, list[np.ndarray]]:
        linhas = conexao.execute("SELECT * FROM referencias_biometricas").fetchall()
        if not linhas:
            return {}
        cifrador = self.cifrador()
        resultado = {}
        for linha in linhas:
            if linha["model_id"] != MODEL_ID:
                raise DomainError(503, "Referências incompatíveis com o modelo atual.")
            try:
                vetores = json.loads(cifrador.decrypt(linha["encrypted_samples"]))
                if not isinstance(vetores, list) or len(vetores) < 5:
                    raise ValueError("Referências incompletas")
                resultado[linha["subject_id"]] = [
                    normalizar_vetor_facial(amostra) for amostra in vetores
                ]
            except (InvalidToken, ValueError, TypeError) as erro:
                raise DomainError(
                    503, "Referências biométricas inválidas ou chave incorreta."
                ) from erro
        return resultado

    @staticmethod
    def obter_usuario(conexao, identificador: str) -> dict:
        linha = conexao.execute(
            "SELECT * FROM usuarios WHERE subject_id=?", (identificador,)
        ).fetchone()
        if linha is None:
            raise DomainError(404, "Usuário não encontrado.")
        valor = dict(linha)
        valor["active"] = bool(valor["active"])
        valor["divisions"] = [
            item[0]
            for item in conexao.execute(
                "SELECT division FROM divisoes_usuarios WHERE subject_id=? ORDER BY division",
                (identificador,),
            )
        ]
        referencia = conexao.execute(
            "SELECT sample_count FROM referencias_biometricas WHERE subject_id=?", (identificador,)
        ).fetchone()
        valor["sample_count"] = referencia[0] if referencia else 0
        return valor

    @staticmethod
    def obter_permissao(usuario: dict) -> UserPermission:
        return UserPermission(usuario["level"], frozenset(usuario["divisions"]), usuario["active"])

    @staticmethod
    def inserir_usuario(conexao, identificador, nome_exibicao, nivel, ativo, divisoes):
        instante = agora()
        try:
            conexao.execute(
                "INSERT INTO usuarios VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)",
                (identificador, nome_exibicao, nivel, int(ativo), instante, instante),
            )
        except sqlite3.IntegrityError as erro:
            raise DomainError(409, "Identificador já cadastrado.") from erro
        conexao.executemany(
            "INSERT INTO divisoes_usuarios VALUES (?, ?)",
            [(identificador, divisao) for divisao in divisoes],
        )

    @staticmethod
    def salvar_amostras(
        conexao,
        identificador,
        conteudo_cifrado,
        data_consentimento=None,
        versao_consentimento="cadastro-v1",
    ):
        conexao.execute(
            "INSERT OR REPLACE INTO referencias_biometricas VALUES (?, ?, ?, ?, ?)",
            (identificador, MODEL_ID, conteudo_cifrado, 5, agora()),
        )
        conexao.execute(
            "UPDATE usuarios SET consent_at=?, consent_version=?, updated_at=? WHERE subject_id=?",
            (data_consentimento or agora(), versao_consentimento, agora(), identificador),
        )
