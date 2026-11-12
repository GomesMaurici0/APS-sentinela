# SENTINELA

Projeto acadêmico de identificação facial e autorização de acesso. O painel usa
React/TypeScript, o backend usa Python/FastAPI e OpenCV, e os dados ficam em SQLite.
Tudo funciona localmente, com o frontend servido pelo próprio backend.

## Executar (ambiente já preparado)

No PowerShell, na raiz do projeto:

```powershell
.\.venv-local\Scripts\python.exe -m sentinela.cli serve
```

Abra http://127.0.0.1:8000. Ctrl+C encerra. Para outra porta, acrescente --port 8001.
Se ainda não existir administrador, crie uma única vez:

```powershell
.\.venv-local\Scripts\python.exe -m sentinela.cli admin-create --username admin
```

A senha é solicitada no terminal (12 a 128 caracteres). Não há senha padrão.
Não apague o banco ou a chave para tentar recuperar uma senha.
Configuração da IDE: [PyCharm](../APS-Sentinela-Materiais/docs/pycharm.txt).

## Preparar o ambiente

Requisitos: Windows, Python 3.12 a 3.14 e Node.js 22.12+ ou 24.
A instalação das dependências e o download dos modelos precisam de internet.

```powershell
python -m venv .venv-local
.\.venv-local\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv-local\Scripts\python.exe -m pip install --no-deps -e .
.\.venv-local\Scripts\python.exe -m sentinela.cli download-models
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
```

Após alterar a interface, execute novamente npm.cmd run build em frontend.
Não é necessário reinstalar dependências a cada inicialização.

## Uso

- Usuários: criar e editar permissões, cadastrar cinco amostras com consentimento,
  excluir biometria ou excluir o usuário.
- Terminal: ativar a câmera, escolher nível/divisão e avaliar o acesso.
- Histórico: consultar decisões, motivos e tempo de processamento.

A câmera é aberta pelo navegador após ação do usuário. Fotografias não são gravadas.
Os dados ficam em %LOCALAPPDATA%\Sentinela\prototype, fora do repositório.
O banco sentinela.db e a chave biometrics.key devem ser tratados como dados privados.
O servidor escuta somente em 127.0.0.1 e não foi preparado para acesso pela rede.

O reconhecimento usa YuNet e SFace em CPU. Os limiares são experimentais: não
representam probabilidade de acerto. Não há detecção de vivacidade; este protótipo
não deve controlar acesso físico real. Participantes devem consentir com o cadastro.

## Verificar

```powershell
.\.venv-local\Scripts\python.exe -m sentinela.cli doctor
.\.venv-local\Scripts\python.exe -m pytest -q
.\.venv-local\Scripts\python.exe -m ruff check backend
```

Os testes usam entradas sintéticas e bancos temporários. Não medem acurácia com
pessoas nem substituem a validação com webcam e participantes.

## Organização

- backend/sentinela: servidor, biometria, permissões e persistência.
- backend/tests: testes automatizados, incluindo a API.
- frontend: interface e configuração de compilação.
- models: modelos locais, manifesto e licenças.
- .run: configurações opcionais de execução no PyCharm.

O laboratório de webcam em Python continua disponível por compatibilidade com os
cadastros anteriores: python -m sentinela.cli camera (usando o interpretador local).
Ele usa gallery.db, separado do painel, e não registra auditoria.
Veja os demais comandos com python -m sentinela.cli --help.

A documentação fica fora do projeto, em ../APS-Sentinela-Materiais/docs.
Os documentos acadêmicos e relatórios antigos registram etapas anteriores. Para
instalação e execução atuais, siga este README. Orientação recebida em 09/11/2026:
a avaliação será uma apresentação.
