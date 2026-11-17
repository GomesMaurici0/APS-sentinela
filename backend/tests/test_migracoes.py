import sqlite3
from pathlib import Path

from sentinela.database import Database


def test_traducao_das_tabelas_preserva_dados_e_relacionamentos(tmp_path):
    banco = Database(tmp_path)
    migracoes = Path(__file__).parents[1] / "sentinela" / "migrations"
    with sqlite3.connect(banco.path) as conexao:
        conexao.executescript((migracoes / "001_initial.sql").read_text("utf-8"))
        conexao.executescript((migracoes / "002_remove_admin_auth.sql").read_text("utf-8"))
        conexao.execute(
            "INSERT INTO users VALUES ('teste', 'Voluntário', 2, 1, 'data', 'v1', 'data', 'data')"
        )
        conexao.execute("INSERT INTO user_divisions VALUES ('teste', 'ambiental')")
        conexao.execute(
            "INSERT INTO biometric_references VALUES ('teste', 'modelo', ?, 5, 'data')",
            (b"vetores-cifrados-preservados",),
        )
        conexao.execute(
            "INSERT INTO attempts (occurred_at, subject_id, requested_level, division, granted, "
            "reason, elapsed_ms, model_id, config_json) VALUES "
            "('data', 'teste', 2, 'ambiental', 1, 'acesso_autorizado', 10, 'modelo', '{}')"
        )
        nomes = {
            "users": "usuarios",
            "user_divisions": "divisoes_usuarios",
            "biometric_references": "referencias_biometricas",
            "attempts": "tentativas_acesso",
        }
        # Os identificadores abaixo pertencem ao conjunto fixo de nomes de tabelas do teste.
        dados_antes = {
            novo: conexao.execute(f"SELECT * FROM {antigo}").fetchall()
            for antigo, novo in nomes.items()
        }

    banco.inicializar()
    banco.inicializar()
    with banco.conectar(write=True) as conexao:
        tabelas = {
            linha[0]
            for linha in conexao.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert not tabelas.intersection(nomes)
        assert set(nomes.values()) <= tabelas
        for tabela, esperado in dados_antes.items():
            assert [
                tuple(linha) for linha in conexao.execute(f"SELECT * FROM {tabela}")
            ] == esperado
        assert conexao.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conexao.execute("PRAGMA user_version").fetchone()[0] == 3
        conexao.execute("DELETE FROM usuarios WHERE subject_id='teste'")
        assert conexao.execute("SELECT * FROM divisoes_usuarios").fetchall() == []
        assert conexao.execute("SELECT * FROM referencias_biometricas").fetchall() == []
        assert conexao.execute("SELECT subject_id FROM tentativas_acesso").fetchone()[0] is None
