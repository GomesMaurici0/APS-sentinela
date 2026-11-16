"""Comandos do laboratório biométrico e do servidor local do painel."""

import argparse
import json
import sqlite3
import sys
import urllib.error
from dataclasses import asdict
from time import monotonic

import cv2
import numpy as np

from sentinela.autorizacao import UserPermission, autorizar
from sentinela.biometria.matching import MatchStatus, identificar
from sentinela.biometria.models import DEFAULT_MODELS, baixar_modelos, validar_modelos
from sentinela.biometria.pipeline import CaptureStatus, FacePipeline
from sentinela.config import BiometricConfig, diretorio_dados
from sentinela.galeria import MINIMUM_SAMPLES, Gallery


def executar_camera(argumentos, motor_facial: FacePipeline, galeria: Gallery):
    permissao = None
    if argumentos.enroll:
        if not argumentos.consent:
            raise ValueError("Cadastro exige --consent, após consentimento livre do voluntário.")
        permissao = UserPermission(argumentos.level, frozenset(argumentos.division))
        if argumentos.enroll in galeria.ler()["subjects"]:
            raise ValueError("Identificador já cadastrado. Exclua antes de recadastrar.")
        print("Consentimento laboratorio-v1: processamento local de referências faciais para APS.")
        print("Sem salvar fotografias. Referências criptografadas, sem garantia de vivacidade.")
        print("Retirada/exclusão: sentinela delete IDENTIFICADOR. Não use nome real.")
        if input("O voluntário concorda? Digite CONSINTO: ").strip() != "CONSINTO":
            raise ValueError("Cadastro cancelado: consentimento não confirmado.")
    elif argumentos.consent:
        raise ValueError("--consent é usado somente com --enroll.")

    registros = galeria.ler()["subjects"]
    referencias = {
        chave: [np.asarray(vetor, np.float32) for vetor in registro["samples"]]
        for chave, registro in registros.items()
        if registro["active"]
    }
    captura = cv2.VideoCapture(argumentos.device)
    try:
        if not captura.isOpened():
            raise ValueError(
                "Câmera indisponível. Verifique permissão, índice e outros aplicativos."
            )
        captura.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        captura.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        print("Janela local: ESPAÇO coleta amostra; ESC ou Q encerra. Nenhuma image m é salva.")
        amostras = []
        ultima_amostra = -float("inf")
        while True:
            sucesso, quadro = captura.read()
            if not sucesso:
                raise ValueError("Falha de aquisição. Câmera desconectada ou ocupada.")
            resultado = motor_facial.analisar(quadro)
            visualizacao = resultado.frame.copy() if resultado.frame is not None else quadro.copy()
            rotulo = resultado.status.value
            cor = (60, 190, 240)
            if argumentos.enroll:
                rotulo += f" | amostras {len(amostras)}/{MINIMUM_SAMPLES} | ESPACO captura"
            elif resultado.status == CaptureStatus.OK:
                identificacao = identificar(resultado.embedding, referencias, motor_facial.config)
                rotulo = identificacao.status.value
                if identificacao.similarity is not None:
                    rotulo += f" | sim {identificacao.similarity:.3f}"
                if identificacao.status == MatchStatus.MATCHED:
                    registro = registros[identificacao.subject_id]
                    usuario = UserPermission(
                        registro["level"], frozenset(registro["divisions"]), registro["active"]
                    )
                    decisao = autorizar(
                        usuario, argumentos.access_level, argumentos.access_division
                    )
                    rotulo = f"{identificacao.subject_id} | {decisao.reason}"
                    cor = (90, 210, 90) if decisao.granted else (70, 70, 240)
                else:
                    cor = (70, 70, 240)
            if resultado.faces is not None:
                for rosto in resultado.faces:
                    x, y, largura, altura = map(int, rosto[:4])
                    cv2.rectangle(visualizacao, (x, y), (x + largura, y + altura), cor, 2)
                    for indice in range(4, 14, 2):
                        cv2.circle(
                            visualizacao, tuple(map(int, rosto[indice : indice + 2])), 2, cor, -1
                        )
            cv2.putText(
                visualizacao,
                "SENTINELA | LABORATORIO SEM AUDITORIA",
                (10, 23),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (230, 230, 230),
                1,
            )
            cv2.putText(visualizacao, rotulo, (10, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, cor, 1)
            metricas = f"{resultado.elapsed_ms:.0f} ms | ESC encerra"
            if resultado.brightness is not None:
                metricas += f" | luz {resultado.brightness:.0f} | nitidez {resultado.sharpness:.0f}"
            cv2.putText(
                visualizacao, metricas, (10, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1
            )
            if resultado.aligned is not None:
                # Recorte permanece apenas na memória/janela e desaparece na captura seguinte.
                recorte = cv2.resize(resultado.aligned, (112, 112))
                if visualizacao.shape[0] >= 112 and visualizacao.shape[1] >= 112:
                    visualizacao[-112:, -112:] = recorte
            cv2.imshow("SENTINELA - laboratorio", visualizacao)
            chave = cv2.waitKey(1) & 0xFF
            if chave in (27, ord("q")):
                break
            if cv2.getWindowProperty("SENTINELA - laboratorio", cv2.WND_PROP_VISIBLE) < 1:
                break
            if argumentos.enroll and chave == 32 and resultado.status == CaptureStatus.OK:
                if monotonic() - ultima_amostra < 0.8:
                    continue
                amostras.append(resultado.embedding.copy())
                ultima_amostra = monotonic()
                if len(amostras) == MINIMUM_SAMPLES:
                    galeria.cadastrar_biometria(
                        argumentos.enroll, permissao, amostras, consent=True
                    )
                    print("Cadastro experimental salvo. Nenhuma fotografia foi persistida.")
                    break
    finally:
        captura.release()
        cv2.destroyAllWindows()


def principal(argumentos_cli=None) -> int:
    analisador_argumentos = argparse.ArgumentParser(
        description="SENTINELA — laboratório biométrico local"
    )
    subcomandos = analisador_argumentos.add_subparsers(dest="command", required=True)
    for comando in ("download-models", "doctor", "camera", "delete", "serve"):
        subcomando = subcomandos.add_parser(comando)
        if comando != "delete":
            from pathlib import Path

            subcomando.add_argument("--models", type=Path, default=DEFAULT_MODELS)
        if comando == "delete":
            subcomando.add_argument("subject")
        if comando == "serve":
            subcomando.add_argument("--port", type=int, default=8000)
        if comando == "camera":
            subcomando.add_argument("--device", type=int, default=0)
            subcomando.add_argument("--enroll", metavar="IDENTIFICADOR")
            subcomando.add_argument("--consent", action="store_true")
            subcomando.add_argument("--level", type=int, choices=(1, 2, 3), default=1)
            subcomando.add_argument("--division", action="append", default=[])
            subcomando.add_argument("--access-level", type=int, choices=(1, 2, 3), default=1)
            subcomando.add_argument("--access-division")
            subcomando.add_argument("--threshold", type=float, default=0.45)
            subcomando.add_argument("--margin", type=float, default=0.08)
    argumentos = analisador_argumentos.parse_args(argumentos_cli)
    try:
        if argumentos.command == "serve":
            import uvicorn

            from sentinela.api import criar_aplicacao

            if not 1 <= argumentos.port <= 65535:
                raise ValueError("Porta inválida.")
            print(f"Abra http://127.0.0.1:{argumentos.port} no navegador. Ctrl+C encerra.")
            uvicorn.run(
                criar_aplicacao(models=argumentos.models),
                host="127.0.0.1",
                port=argumentos.port,
                workers=1,
                access_log=False,
                proxy_headers=False,
            )
        elif argumentos.command == "download-models":
            baixar_modelos(argumentos.models)
            print("Modelos disponíveis e checksums verificados.")
        elif argumentos.command == "doctor":
            validar_modelos(argumentos.models)
            motor_facial = FacePipeline(argumentos.models)
            resultado = motor_facial.analisar(np.zeros((480, 640, 3), dtype=np.uint8))
            print(
                json.dumps(
                    {
                        "python": sys.version.split()[0],
                        "opencv": cv2.__version__,
                        "models": "sha256_ok",
                        "synthetic_frame": resultado.status,
                        "elapsed_ms": round(resultado.elapsed_ms, 2),
                        "config": asdict(motor_facial.config),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif argumentos.command == "delete":
            Gallery(diretorio_dados()).excluir(argumentos.subject)
            print(
                "Referências excluídas da galeria ativa. Backups externos exigem exclusão própria."
            )
        elif argumentos.command == "camera":
            if (
                autorizar(
                    UserPermission(3), argumentos.access_level, argumentos.access_division
                ).reason
                == "recurso_invalido"
            ):
                raise ValueError(
                    "Informe divisão somente para acesso ao nível 2, onde é obrigatória."
                )
            configuracao = BiometricConfig(
                similarity_threshold=argumentos.threshold, ambiguity_margin=argumentos.margin
            )
            executar_camera(
                argumentos,
                FacePipeline(argumentos.models, configuracao),
                Gallery(diretorio_dados()),
            )
        return 0
    except (ValueError, OSError, sqlite3.Error, cv2.error, urllib.error.URLError) as erro:
        # Não imprimir mensagens OpenCV/SQLite que possam conter dados internos.
        mensagem = (
            str(erro)
            if isinstance(erro, ValueError)
            else "Falha operacional. Verifique ambiente e arquivos."
        )
        print(f"Erro: {mensagem}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Operação interrompida.", file=sys.stderr)
        return 130


# Compatibilidade com atalhos de console instalados antes da refatoração.
main = principal


if __name__ == "__main__":
    raise SystemExit(principal())
