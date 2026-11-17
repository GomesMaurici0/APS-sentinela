# Tabelas do banco SENTINELA

O arquivo continua sendo `sentinela.db`. A versão 3 do esquema usa os nomes abaixo:

| Antes | Agora | Dados armazenados |
|---|---|---|
| users | usuarios | Cadastro, nível de acesso, estado ativo e consentimento |
| user_divisions | divisoes_usuarios | Divisões autorizadas para cada usuário |
| biometric_references | referencias_biometricas | Vetores faciais cifrados, modelo e quantidade de amostras |
| attempts | tentativas_acesso | Histórico de decisões, motivos, pontuações e tempos |

As colunas mantêm os nomes existentes. Os endpoints e campos JSON da API continuam
compatíveis com a interface e com a collection Postman. A galeria experimental
`gallery.db` é separada do painel e não foi modificada nesta etapa.

A migração `003_tabelas_em_portugues.sql` renomeia as tabelas preservando registros,
chaves estrangeiras e identificadores. Inicializações posteriores não repetem a
migração. As migrações 001 e 002 mantêm os nomes históricos para permitir atualizar
bancos anteriores corretamente. O índice do histórico agora se chama
`indice_tentativas_acesso`.

Para visualizar, abra o arquivo `sentinela.db` em
`%LOCALAPPDATA%\Sentinela\prototype` pelo DB Browser for SQLite. Caso já estivesse
aberto, feche e reabra o banco para atualizar a estrutura exibida.

Exemplos de consultas:

```sql
SELECT subject_id, display_name, level, active FROM usuarios;
SELECT subject_id, division FROM divisoes_usuarios;
SELECT subject_id, model_id, sample_count FROM referencias_biometricas;
SELECT occurred_at, subject_id, granted, reason
FROM tentativas_acesso ORDER BY id DESC;
```

A aplicação trabalha com as referências cifradas; as fotos não são persistidas.
Uma cópia de segurança do banco anterior foi criada na mesma pasta privada antes
da migração. O conteúdo das quatro tabelas foi comparado antes/depois e preservado.
