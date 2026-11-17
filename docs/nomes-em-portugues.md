# Nomes em português para estudar o SENTINELA

A refatoração de 16/11/2026 traduz variáveis locais, parâmetros internos e estados
React. Usa snake_case no Python e camelCase no TypeScript, sem acentos nos nomes.

| Antes | Agora | Significado |
|---|---|---|
| frame | quadro | Matriz de pixels capturada |
| result | resultado | Análise da captura |
| face / faces | rosto / rostos | Detecções retornadas pelo YuNet |
| brightness / sharpness | iluminacao / nitidez | Medidas de qualidade |
| query | consulta | Vetor facial que será comparado |
| scores | pontuacoes | Média das similaridades por pessoa |
| best / margin | melhor_pontuacao / margem | Critérios de aceitação da identidade |
| references | referencias | Vetores das pessoas cadastradas |
| user / decision | usuario / decisao | Permissão cadastrada e resultado final |
| connection / row | conexao / linha | Acesso e registro do banco |
| stream / running | fluxoCamera / cameraAtiva | Câmera no navegador |
| images / frozen | imagens / imagemCongelada | Capturas temporárias da interface |
| busy / error | processando / erro | Estado e mensagem da operação |
| setDecision | definirDecisao | Atualiza o estado React da avaliação |

## Por onde começar

1. `autorizacao.py`: leia `usuario`, `nivel_solicitado` e `divisao` para entender a regra.
2. `biometria/matching.py`: acompanhe `consulta`, `pontuacoes`, `melhor_pontuacao` e `margem`.
3. `biometria/pipeline.py`: acompanhe `quadro`, `rostos`, `recorte`, `iluminacao` e `nitidez`.
4. `access_service.py`: veja a passagem de `resultado` para `identificacao` e `decisao`.
5. `frontend/src/Camera.tsx`: acompanhe `fluxoCamera`, `imagens`, `captura` e `decisao`.

## Nomes que continuam em inglês

Os campos da API, colunas SQL, propriedades dos modelos de dados e nomes de
bibliotecas mantêm a compatibilidade com o banco, o OpenAPI e o Postman. Por isso
você verá `usuario.level` (campo do modelo) junto de `nivel_solicitado` (variável).
Da mesma forma, a interface envia `{ image: imagem }`: `image` é o campo JSON e
`imagem` é a variável local. Não são duas imagens diferentes.

Os nomes dos arquivos e das classes de domínio continuam como referências.
As funções e os métodos próprios agora também têm nomes em português. Argumentos usados por nome nas
chamadas existentes também foram preservados. `self`, `cls`, `np` e `cv2` seguem
as convenções das bibliotecas.

As rotas HTTP e o contrato OpenAPI foram comparados antes/depois e permaneceram
iguais. Não houve migração do banco nem alteração dos modelos faciais nesta etapa.
Reinicie Run/Debug na IDE para carregar as novas variáveis no depurador.

## Funções e métodos em português

| Antes | Agora | Responsabilidade |
|---|---|---|
| `create_app` | `criar_aplicacao` | Monta o servidor FastAPI |
| `decode_image` | `decodificar_imagem` | Converte base64 em imagem |
| `analyze` | `analisar` | Executa o processamento facial |
| `face_quality` | `avaliar_qualidade_rosto` | Verifica qualidade da captura |
| `normalized_embedding` | `normalizar_vetor_facial` | Normaliza as características |
| `identify` | `identificar` | Compara com as referências |
| `authorize` | `autorizar` | Aplica níveis e divisões |
| `enroll` | `cadastrar_biometria` | Salva as referências aprovadas |
| `attempt` | `avaliar_acesso` | Coordena decisão e auditoria |
| `connect` | `conectar` | Abre transação do banco |
| `initialize` | `inicializar` | Aplica migrações SQL |
| `references` | `obter_referencias` | Lê referências biométricas |
| `save_samples` | `salvar_amostras` | Persiste as amostras cifradas |
| `validate_models` | `validar_modelos` | Confere modelos e integridade |
| `download_models` | `baixar_modelos` | Obtém os arquivos dos modelos |
| `main` | `principal` | Entrada do CLI |
| `label` / `date` | `traduzirMotivo` / `formatarData` | Formatação na interface |

O fluxo para explicar é: `criar_aplicacao` → `avaliar_acesso` → `analisar` →
`identificar` → `autorizar` → registrar a tentativa no banco.

`__init__`, `__call__` e `__post_init__` são nomes especiais exigidos pelo Python.
`openapi`, `feature`, `connect` de sqlite3 e `read` de arquivos são métodos das
bibliotecas e permanecem como definidos por elas. A variável `main = principal`
serve apenas para compatibilidade com atalhos de console já instalados.
As rotas e os campos HTTP permanecem iguais; os decoradores preservam os IDs das
operações anteriores, portanto a collection continua compatível.
