"""Comandos do laboratório biométrico e do servidor local do painel."""

import argparse
import getpass
import json
import sqlite3
import sys
import urllib.error
from dataclasses import asdict
from time import monotonic

import cv2
import numpy as np

from sentinela.autorizacao import UserPermission, authorize
from sentinela.biometria.matching import MatchStatus, identify
from sentinela.biometria.models import DEFAULT_MODELS, download_models, validate_models
from sentinela.biometria.pipeline import CaptureStatus, FacePipeline
from sentinela.config import BiometricConfig, data_directory
from sentinela.galeria import MINIMUM_SAMPLES, Gallery


def camera(args, pipeline: FacePipeline, gallery: Gallery):
    permission = None
    if args.enroll:
        if not args.consent:
            raise ValueError("Cadastro exige --consent, após consentimento livre do voluntário.")
        permission = UserPermission(args.level, frozenset(args.division))
        if args.enroll in gallery.read()["subjects"]:
            raise ValueError("Identificador já cadastrado. Exclua antes de recadastrar.")
        print("Consentimento laboratorio-v1: processamento local de referências faciais para APS.")
        print("Sem salvar fotografias. Referências criptografadas, sem garantia de vivacidade.")
        print("Retirada/exclusão: sentinela delete IDENTIFICADOR. Não use nome real.")
        if input("O voluntário concorda? Digite CONSINTO: ").strip() != "CONSINTO":
            raise ValueError("Cadastro cancelado: consentimento não confirmado.")
    elif args.consent:
        raise ValueError("--consent é usado somente com --enroll.")

    records = gallery.read()["subjects"]
    references = {
        key: [np.asarray(vector, np.float32) for vector in record["samples"]]
        for key, record in records.items()
        if record["active"]
    }
    capture = cv2.VideoCapture(args.device)
    try:
        if not capture.isOpened():
            raise ValueError(
                "Câmera indisponível. Verifique permissão, índice e outros aplicativos."
            )
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        print("Janela local: ESPAÇO coleta amostra; ESC ou Q encerra. Nenhuma imagem é salva.")
        samples = []
        last_sample = -float("inf")
        while True:
            ok, frame = capture.read()
            if not ok:
                raise ValueError("Falha de aquisição. Câmera desconectada ou ocupada.")
            result = pipeline.analyze(frame)
            view = result.frame.copy() if result.frame is not None else frame.copy()
            label = result.status.value
            color = (60, 190, 240)
            if args.enroll:
                label += f" | amostras {len(samples)}/{MINIMUM_SAMPLES} | ESPACO captura"
            elif result.status == CaptureStatus.OK:
                match = identify(result.embedding, references, pipeline.config)
                label = match.status.value
                if match.similarity is not None:
                    label += f" | sim {match.similarity:.3f}"
                if match.status == MatchStatus.MATCHED:
                    record = records[match.subject_id]
                    user = UserPermission(
                        record["level"], frozenset(record["divisions"]), record["active"]
                    )
                    decision = authorize(user, args.access_level, args.access_division)
                    label = f"{match.subject_id} | {decision.reason}"
                    color = (90, 210, 90) if decision.granted else (70, 70, 240)
                else:
                    color = (70, 70, 240)
            if result.faces is not None:
                for face in result.faces:
                    x, y, width, height = map(int, face[:4])
                    cv2.rectangle(view, (x, y), (x + width, y + height), color, 2)
                    for index in range(4, 14, 2):
                        cv2.circle(view, tuple(map(int, face[index : index + 2])), 2, color, -1)
            cv2.putText(
                view,
                "SENTINELA | LABORATORIO SEM AUDITORIA",
                (10, 23),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (230, 230, 230),
                1,
            )
            cv2.putText(view, label, (10, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
            metrics = f"{result.elapsed_ms:.0f} ms | ESC encerra"
            if result.brightness is not None:
                metrics += f" | luz {result.brightness:.0f} | nitidez {result.sharpness:.0f}"
            cv2.putText(view, metrics, (10, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (230, 230, 230), 1)
            if result.aligned is not None:
                # Recorte permanece apenas na memória/janela e desaparece na captura seguinte.
                crop = cv2.resize(result.aligned, (112, 112))
                if view.shape[0] >= 112 and view.shape[1] >= 112:
                    view[-112:, -112:] = crop
            cv2.imshow("SENTINELA - laboratorio", view)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if cv2.getWindowProperty("SENTINELA - laboratorio", cv2.WND_PROP_VISIBLE) < 1:
                break
            if args.enroll and key == 32 and result.status == CaptureStatus.OK:
                if monotonic() - last_sample < 0.8:
                    continue
                samples.append(result.embedding.copy())
                last_sample = monotonic()
                if len(samples) == MINIMUM_SAMPLES:
                    gallery.enroll(args.enroll, permission, samples, consent=True)
                    print("Cadastro experimental salvo. Nenhuma fotografia foi persistida.")
                    break
    finally:
        capture.release()
        cv2.destroyAllWindows()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="SENTINELA — laboratório biométrico local")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("download-models", "doctor", "camera", "delete", "admin-create", "serve"):
        child = sub.add_parser(command)
        if command not in ("delete", "admin-create"):
            from pathlib import Path

            child.add_argument("--models", type=Path, default=DEFAULT_MODELS)
        if command == "delete":
            child.add_argument("subject")
        if command == "admin-create":
            child.add_argument("--username", default="admin")
        if command == "serve":
            child.add_argument("--port", type=int, default=8000)
        if command == "camera":
            child.add_argument("--device", type=int, default=0)
            child.add_argument("--enroll", metavar="IDENTIFICADOR")
            child.add_argument("--consent", action="store_true")
            child.add_argument("--level", type=int, choices=(1, 2, 3), default=1)
            child.add_argument("--division", action="append", default=[])
            child.add_argument("--access-level", type=int, choices=(1, 2, 3), default=1)
            child.add_argument("--access-division")
            child.add_argument("--threshold", type=float, default=0.45)
            child.add_argument("--margin", type=float, default=0.08)
    args = parser.parse_args(argv)
    try:
        if args.command == "admin-create":
            from sentinela.database import Database

            password = getpass.getpass("Senha administrativa (12 a 128 caracteres): ")
            confirmation = getpass.getpass("Confirme a senha: ")
            if password != confirmation:
                raise ValueError("As senhas não coincidem.")
            Database(data_directory()).create_admin(args.username, password)
            print("Administrador criado. A senha não foi registrada em logs.")
        elif args.command == "serve":
            import uvicorn

            from sentinela.api import create_app
            from sentinela.database import Database

            if not 1 <= args.port <= 65535:
                raise ValueError("Porta inválida.")
            database = Database(data_directory())
            database.initialize()
            with database.connect() as connection:
                count = connection.execute("SELECT COUNT(*) FROM administrators").fetchone()[0]
            if count == 0:
                raise ValueError("Crie o administrador: python -m sentinela.cli admin-create")
            print(f"Abra http://127.0.0.1:{args.port} no navegador. Ctrl+C encerra.")
            uvicorn.run(
                create_app(models=args.models),
                host="127.0.0.1",
                port=args.port,
                workers=1,
                access_log=False,
                proxy_headers=False,
            )
        elif args.command == "download-models":
            download_models(args.models)
            print("Modelos disponíveis e checksums verificados.")
        elif args.command == "doctor":
            validate_models(args.models)
            pipeline = FacePipeline(args.models)
            result = pipeline.analyze(np.zeros((480, 640, 3), dtype=np.uint8))
            print(
                json.dumps(
                    {
                        "python": sys.version.split()[0],
                        "opencv": cv2.__version__,
                        "models": "sha256_ok",
                        "synthetic_frame": result.status,
                        "elapsed_ms": round(result.elapsed_ms, 2),
                        "config": asdict(pipeline.config),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "delete":
            Gallery(data_directory()).delete(args.subject)
            print(
                "Referências excluídas da galeria ativa. Backups externos exigem exclusão própria."
            )
        elif args.command == "camera":
            if (
                authorize(UserPermission(3), args.access_level, args.access_division).reason
                == "recurso_invalido"
            ):
                raise ValueError(
                    "Informe divisão somente para acesso ao nível 2, onde é obrigatória."
                )
            config = BiometricConfig(
                similarity_threshold=args.threshold, ambiguity_margin=args.margin
            )
            camera(args, FacePipeline(args.models, config), Gallery(data_directory()))
        return 0
    except (ValueError, OSError, sqlite3.Error, cv2.error, urllib.error.URLError) as error:
        # Não imprimir mensagens OpenCV/SQLite que possam conter dados internos.
        message = (
            str(error)
            if isinstance(error, ValueError)
            else "Falha operacional. Verifique ambiente e arquivos."
        )
        print(f"Erro: {message}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Operação interrompida.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
