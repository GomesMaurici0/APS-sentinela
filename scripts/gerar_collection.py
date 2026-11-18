"""Exporta a API real e uma collection Postman v2.1 para importação."""

# Descrições e JavaScript da exportação preservam suas linhas literais.
# ruff: noqa: E501

import base64
import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
from sentinela.api import criar_aplicacao

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "postman"


def event(kind, code):
    return {"listen": kind, "script": {"type": "text/javascript", "exec": code.splitlines()}}


def request(name, method, path, description, body=None, status=200, checks="", guard=None):
    headers = []
    value = {
        "method": method,
        "header": headers,
        "url": "{{base_url}}" + path,
        "description": description,
    }
    if body is not None:
        headers.append({"key": "Content-Type", "value": "application/json"})
        value["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, ensure_ascii=False, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    code = f'pm.test("HTTP {status}", () => pm.response.to.have.status({status}));\n' + checks
    events = [event("test", code)]
    if guard:
        events.insert(0, event("prerequest", guard))
    return {"name": name, "request": value, "event": events}


def documentar_colecao(colecao):
    """Traduz variáveis do Postman e relaciona cada chamada ao código e às tabelas."""
    nomes = {
        "base_url": "endereco_base",
        "subject_id": "identificador_usuario",
        "imagem_nenhum_rosto": "imagem_sem_rosto",
    }
    explicacoes = {
        1: ("criar_usuario → inserir_usuario", "usuarios e divisoes_usuarios"),
        2: ("listar_usuarios", "usuarios, divisoes_usuarios e referencias_biometricas"),
        3: (
            "consultar_usuario → obter_usuario",
            "usuarios, divisoes_usuarios e referencias_biometricas",
        ),
        4: ("atualizar_usuario", "usuarios e divisoes_usuarios"),
        5: (
            "analisar → decodificar_imagem → analisar",
            "Não grava dados; analisa uma imagem sintética",
        ),
        6: (
            "analisar → decodificar_imagem → analisar",
            "Não grava dados; analisa uma captura real",
        ),
        7: (
            "cadastrar_biometria → cifrar_amostras → salvar_amostras",
            "usuarios e referencias_biometricas",
        ),
        8: (
            "avaliar_acesso → analisar → identificar → autorizar",
            "tentativas_acesso; consulta usuarios e referencias_biometricas",
        ),
        9: (
            "avaliar_acesso → analisar → identificar → autorizar",
            "tentativas_acesso; consulta usuarios, divisoes_usuarios e referencias_biometricas",
        ),
        10: ("listar_tentativas", "tentativas_acesso"),
        11: ("listar_tentativas", "tentativas_acesso, filtrada por granted=false"),
        12: ("consultar_indicadores", "usuarios, referencias_biometricas e tentativas_acesso"),
        13: ("Validação UserCreate antes de criar_usuario", "Nenhuma gravação esperada"),
        14: ("Validação Enrollment antes de cadastrar_biometria", "Nenhuma gravação esperada"),
        15: ("Validação AttemptInput antes de avaliar_acesso", "Nenhuma gravação esperada"),
        16: ("obter_contrato → openapi do FastAPI", "Não consulta o banco"),
        17: ("servir_interface", "Não consulta o banco"),
        18: (
            "importar_legado",
            "usuarios, divisoes_usuarios e referencias_biometricas; lê e limpa a galeria antiga",
        ),
        19: (
            "excluir_biometria",
            "Remove referencias_biometricas e limpa consentimento em usuarios",
        ),
        20: (
            "excluir_usuario",
            "Remove usuarios e vínculos; mantém tentativas_acesso com subject_id nulo",
        ),
    }

    def traduzir_texto(texto):
        for antigo, novo in nomes.items():
            texto = texto.replace("{{" + antigo + "}}", "{{" + novo + "}}")
            texto = (
                texto.replace('"' + antigo + '"', '"' + novo + '"')
                if "pm.variables" in texto
                else texto
            )
        return texto

    for variavel in colecao["variable"]:
        variavel["key"] = nomes.get(variavel["key"], variavel["key"])
    for evento in colecao["event"]:
        evento["script"]["exec"] = [
            traduzir_texto(linha)
            .replace("const base =", "const enderecoBase =")
            .replace("test(base ||", "test(enderecoBase ||")
            for linha in evento["script"]["exec"]
        ]
    for pasta in colecao["item"]:
        for item in pasta["item"]:
            requisicao = item["request"]
            requisicao["url"] = traduzir_texto(requisicao["url"])
            if "body" in requisicao:
                requisicao["body"]["raw"] = traduzir_texto(requisicao["body"]["raw"])
            for evento in item["event"]:
                evento["script"]["exec"] = [
                    traduzir_texto(linha)
                    .replace("const data =", "const dados =")
                    .replace("const d =", "const dados =")
                    .replace("data.", "dados.")
                    .replace("d.attempts", "dados.attempts")
                    .replace("d.granted", "dados.granted")
                    .replace("d.denied", "dados.denied")
                    for linha in evento["script"]["exec"]
                ]
            numero = int(item["name"].split()[0])
            funcoes, tabelas = explicacoes[numero]
            requisicao["description"] += (
                "\n\nCódigo em português: " + funcoes + ".\nBanco SQLite: " + tabelas + "."
            )
    colecao["info"]["description"] += (
        "\n\nGuia de leitura: endereco_base é o endereço local; identificador_usuario seleciona o cadastro demonstrativo; imagem_sem_rosto é um PNG sintético. Os nomes das variáveis e do código estão em português. O contrato HTTP mantém nomes como subject_id (identificador), display_name (nome de exibição), level (nível), divisions (divisões), active (ativo), image (imagem), images (amostras), consent (consentimento), requested_level (nível solicitado), division (divisão), granted (autorizado), reason (motivo), similarity (similaridade), margin (margem), elapsed_ms (tempo em milissegundos) e sample_count (quantidade de amostras). Tabelas atuais: usuarios, divisoes_usuarios, referencias_biometricas e tentativas_acesso. Não há login administrativo."
    )


def build():
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sentinela-contract-") as directory:
        schema = criar_aplicacao(Path(directory)).openapi()
    (ROOT / "contracts").mkdir(exist_ok=True)
    (ROOT / "contracts" / "openapi.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    page_check = """pm.test("Página contém itens e total", () => {
  const data = pm.response.json();
  pm.expect(data.items).to.be.an("array");
  pm.expect(data.total).to.be.a("number");
});"""
    user = {
        "subject_id": "{{subject_id}}",
        "display_name": "Voluntário demonstração Postman",
        "level": 2,
        "divisions": ["ambiental"],
        "active": True,
    }
    bio_guard = """if (pm.variables.get("executar_biometria_real") !== "true") {
  pm.execution.skipRequest();
}"""
    users = [
        request(
            "01 Criar usuário de demonstração",
            "POST",
            "/api/users",
            "Cria somente metadados, sem biometria. Nível 2 exige pelo menos uma divisão. Níveis 1 e 3 exigem lista vazia. Retorna 409 se o ID já existir. O script cria um ID novo com prefixo demo-postman-.",
            user,
            201,
            'pm.test("Usuário criado sem referências faciais", () => pm.expect(pm.response.json().sample_count).to.eql(0));',
        ),
        request(
            "02 Listar usuários",
            "GET",
            "/api/users?offset=0&limit=50",
            "Paginação: offset >= 0; limit entre 1 e 100. Retorna items, total, offset e limit.",
            checks=page_check,
        ),
        request(
            "03 Consultar usuário",
            "GET",
            "/api/users/{{subject_id}}",
            "Consulta cadastro, permissões e quantidade de amostras, sem devolver vetores biométricos. ID ausente retorna 404.",
        ),
        request(
            "04 Atualizar usuário",
            "PUT",
            "/api/users/{{subject_id}}",
            "Substitui os campos editáveis; não é PATCH. Mantém nível 2 e divisão ambiental neste exemplo.",
            {key: value for key, value in user.items() if key != "subject_id"},
        ),
    ]
    biometric = [
        request(
            "05 Analisar imagem sintética sem rosto",
            "POST",
            "/api/biometrics/analyze",
            "Usa PNG preto gerado localmente. Exercita o motor verdadeiro e deve resultar em nenhum_rosto, sem cadastrar biometria. HTTP 200 significa análise concluída, não rosto aceito.",
            {"image": "{{imagem_nenhum_rosto}}"},
            checks='pm.test("Sem rosto detectado", () => pm.expect(pm.response.json().status).to.eql("nenhum_rosto"));',
        ),
        request(
            "06 Analisar captura real (manual)",
            "POST",
            "/api/biometrics/analyze",
            "Opcional: configure executar_biometria_real=true e imagem_base64 localmente. JPEG/PNG base64 puro, sem data:image/...; até 1.048.576 caracteres. A resposta mostra qualidade e eventual região alinhada. Não sincronize imagens pessoais com a nuvem.",
            {"image": "{{imagem_base64}}"},
            guard=bio_guard,
        ),
        request(
            "07 Cadastrar cinco amostras (manual)",
            "POST",
            "/api/users/{{subject_id}}/biometrics",
            "Opcional. Exige consentimento explícito e exatamente cinco imagens aprovadas do mesmo voluntário. Reprocessa tudo no servidor; salva referências cifradas e consentimento. Pode retornar 422 por qualidade e 409 por conflito biométrico. Não treina novamente o SFace. Defina as cinco variáveis somente localmente.",
            {"consent": True, "images": ["{{amostra_" + str(i) + "}}" for i in range(1, 6)]},
            guard=bio_guard,
        ),
    ]
    attempts = [
        request(
            "08 Avaliar acesso sem rosto",
            "POST",
            "/api/attempts",
            "Avalia imagem sintética com motor real. Deve negar e registrar o motivo. O HTTP 200 transporta tanto concessões quanto negações: consulte granted e reason. Aguarde pelo menos um segundo entre avaliações.",
            {"image": "{{imagem_nenhum_rosto}}", "requested_level": 1, "division": None},
            checks="""pm.test("Negação por ausência de rosto", () => {
  const data = pm.response.json();
  pm.expect(data.granted).to.eql(false);
  pm.expect(data.vault).to.eql(null);
  pm.expect(data.reason).to.eql("nenhum_rosto");
  pm.expect(data.id).to.be.a("number");
});""",
        ),
        request(
            "09 Avaliar acesso real à divisão (manual)",
            "POST",
            "/api/attempts",
            "Opcional. Executa identificação 1:N e depois autorização. Nível 2 exige division; nos níveis 1 e 3 ela deve ser null. Pontuação não é probabilidade. Depurar AccessService.avaliar_acesso → FacePipeline.analisar → identificar → autorizar → INSERT attempts.",
            {"image": "{{imagem_base64}}", "requested_level": 2, "division": "ambiental"},
            guard=bio_guard,
        ),
        request(
            "10 Consultar histórico",
            "GET",
            "/api/attempts?offset=0&limit=50",
            "Tentativas em ordem decrescente de ID. Registra decisão, motivo, similaridade, margem e tempo; não armazena fotos no histórico.",
            checks=page_check,
        ),
        request(
            "11 Filtrar acessos negados",
            "GET",
            "/api/attempts?granted=false&offset=0&limit=50",
            "O filtro granted aceita true ou false. Use para mostrar que negações também são auditadas.",
            checks=page_check,
        ),
        request(
            "12 Consultar estatísticas",
            "GET",
            "/api/stats",
            "Contagem de usuários, usuários com referências, tentativas, concessões e negações. Não representa acurácia facial.",
            checks="""pm.test("Tentativas = concessões + negações", () => {
  const d = pm.response.json(); pm.expect(d.attempts).to.eql(d.granted + d.denied);
});""",
        ),
    ]
    validation = [
        request(
            "13 Rejeitar nível inválido",
            "POST",
            "/api/users",
            "Teste negativo: Pydantic rejeita nível 4 antes de gravar. Ajuda a explicar validação de entrada no backend.",
            {**user, "level": 4},
            422,
        ),
        request(
            "14 Rejeitar cadastro sem consentimento",
            "POST",
            "/api/users/{{subject_id}}/biometrics",
            "Teste negativo estrutural. consent=false e lista vazia devem retornar 422 sem processar rosto ou salvar referências.",
            {"consent": False, "images": []},
            422,
        ),
        request(
            "15 Rejeitar recurso sem divisão",
            "POST",
            "/api/attempts",
            "Nível 2 sem divisão é uma entrada inválida; não equivale a uma tentativa biométrica registrada.",
            {"image": "{{imagem_nenhum_rosto}}", "requested_level": 2, "division": None},
            422,
        ),
    ]
    extras = [
        request(
            "16 Obter contrato OpenAPI",
            "GET",
            "/api/openapi.json",
            "Contrato gerado do FastAPI, disponível diretamente no protótipo local. A API não expõe Swagger UI ou ReDoc.",
            checks='pm.test("Contrato possui operações", () => pm.expect(pm.response.json().paths).to.have.property("/api/attempts"));',
        ),
        request(
            "17 Abrir interface compilada",
            "GET",
            "/",
            "Rota HTML da aplicação React. O catch-all GET /{path:path} também serve assets e rotas da SPA; não é endpoint de negócio.",
        ),
        request(
            "18 Importar laboratório legado (manual)",
            "POST",
            "/api/legacy/import",
            "Operação opcional com efeitos: transfere a galeria antiga para o painel e limpa registros importados da origem. Não sobrescreve IDs em conflito (409). Use somente se pretende migrar dados. Exige executar_importacao_legada=true.",
            guard='if (pm.variables.get("executar_importacao_legada") !== "true") pm.execution.skipRequest();',
        ),
    ]
    cleanup = [
        request(
            "19 Excluir biometria do usuário demonstrativo",
            "DELETE",
            "/api/users/{{subject_id}}/biometrics",
            "Revoga referências e consentimento, preservando cadastro. Pode também remover cópia legada do mesmo ID. Restrito nesta collection a IDs demo-postman-.",
            status=204,
        ),
        request(
            "20 Excluir usuário demonstrativo",
            "DELETE",
            "/api/users/{{subject_id}}",
            "Remove cadastro e referências. Preserva tentativas anteriores com vínculo de usuário nulo. Restrito a IDs demo-postman-.",
            status=204,
        ),
    ]
    pre = r"""const base = pm.variables.get("base_url");
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(base || "")) {
  throw new Error("Use um servidor local: http://127.0.0.1:8000");
}
if (pm.info.requestName === "01 Criar usuário de demonstração") {
  pm.variables.set("subject_id", "demo-postman-" + Date.now());
}
if (pm.request.method === "DELETE" && !String(pm.variables.get("subject_id") || "").startsWith("demo-postman-")) {
  pm.execution.skipRequest();
  throw new Error("Exclusões permitidas somente para IDs demo-postman- nesta collection.");
}"""
    collection = {
        "info": {
            "name": "SENTINELA — APS | API completa e demonstração",
            "schema": "https://schema.postman.com/json/collection/v2.1.0/collection.json",
            "description": "Collection derivada de backend/sentinela/api.py e schemas.py. Inclui todas as 13 operações concretas da API (12 no OpenAPI + o próprio contrato), mais a entrada HTML da SPA. Painel e API locais sem login administrativo, cookies de sessão ou CSRF. Execute as pastas em ordem para demonstrar cadastro, biometria, autorização e auditoria. Biometria real e importação legada são opcionais e ignoradas por padrão. As exclusões se limitam aos IDs demonstrativos. Testes sintéticos não medem acurácia. Erros: 403 origem, 404 cadastro inexistente, 409 conflito, 413 corpo >8 MiB, 422 entrada/captura inválida, 429 frequência, 503 motor/persistência. Veja postman/README.md e docs/estrategia-e-debug.md.",
        },
        "auth": {"type": "noauth"},
        "event": [event("prerequest", pre)],
        "variable": [
            {"key": key, "value": value}
            for key, value in {
                "endereco_base": "http://127.0.0.1:8000",
                "subject_id": "demo-postman-manual",
                "executar_biometria_real": "false",
                "executar_importacao_legada": "false",
            }.items()
        ],
        "item": [
            {"name": name, "item": items}
            for name, items in [
                ("01 Cadastro e permissões", users),
                ("02 Processamento e cadastro facial", biometric),
                ("03 Avaliação e auditoria", attempts),
                ("04 Validações negativas", validation),
                ("05 Contrato, interface e migração", extras),
                ("06 Limpeza demonstrativa", cleanup),
            ]
        ],
    }
    documentar_colecao(collection)
    (OUT / "SENTINELA.postman_collection.json").write_text(
        json.dumps(collection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    ok, buffer = cv2.imencode(".png", np.zeros((160, 160, 3), np.uint8))
    assert ok
    environment = {
        "name": "SENTINELA — Local",
        "_postman_variable_scope": "environment",
        "values": [
            {
                "key": key,
                "value": value,
                "enabled": True,
                "type": "default",
            }
            for key, value in {
                "endereco_base": "http://127.0.0.1:8000",
                "imagem_sem_rosto": base64.b64encode(buffer).decode(),
                "imagem_base64": "",
                **{f"amostra_{i}": "" for i in range(1, 6)},
            }.items()
        ],
    }
    (OUT / "SENTINELA-Local.postman_environment.json").write_text(
        json.dumps(environment, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Collection exportada: 20 requisições; contrato OpenAPI exportado.")


if __name__ == "__main__":
    build()
