"""Acervo fictício da APS, sem dados ambientais reais."""

from sentinela.autorizacao import UserPermission, autorizar

AVISO = "Dados simulados para fins acadêmicos. Locais, substâncias e ocorrências são fictícios."
REGISTROS = (
    (
        "AMB-001",
        "Boletim de qualidade ambiental",
        1,
        None,
        "Vale Claro fictício",
        "Monitoramento regular",
        "Índice ambiental simulado: 82/100. Água, solo e vegetação acompanhados no exercício.",
    ),
    (
        "AMB-002",
        "Relatório público de recuperação",
        1,
        None,
        "Parque Aurora fictício",
        "Em acompanhamento",
        "Recuperação simulada de 120 hectares; cobertura vegetal estimada em 68%.",
    ),
    (
        "DIV-001",
        "Qualidade de recursos hídricos",
        2,
        "agua",
        "Bacia Cristal fictícia",
        "Atenção",
        "Três pontos simulados de alteração de qualidade. Coleta complementar "
        "prevista no exercício.",
    ),
    (
        "DIV-002",
        "Integridade do solo",
        2,
        "solo",
        "Setor Horizonte fictício",
        "Em análise",
        "Dois setores com alteração simulada de indicadores; área isolada no cenário acadêmico.",
    ),
    (
        "DIV-003",
        "Acompanhamento de biodiversidade",
        2,
        "biodiversidade",
        "Reserva Ipê fictícia",
        "Monitoramento regular",
        "Quatorze espécies fictícias acompanhadas; dois habitats em recuperação simulada.",
    ),
    (
        "DIV-004",
        "Cobertura florestal",
        2,
        "florestas",
        "Floresta Serena fictícia",
        "Atenção",
        "Redução simulada de 8% da cobertura vegetal; vistoria incluída no exercício.",
    ),
    (
        "MIN-001",
        "Dossiê reservado de substâncias ambientais",
        3,
        None,
        "Área Ômega fictícia",
        "Risco simulado alto",
        "Substância inventada Eco-X17: possível impacto fictício na água, no solo e "
        "na fauna. Avaliação ministerial; sem composição ou instruções de uso.",
    ),
    (
        "MIN-002",
        "Avaliação integrada de ocorrência crítica",
        3,
        None,
        "Complexo Atlas fictício",
        "Análise ministerial",
        "Agente inventado Bio-Z9 associado a alterações simuladas em ecossistemas. "
        "Relatório consolidado das divisões e acompanhamento de contenção no cenário "
        "didático.",
    ),
)


def abrir_cofre(permissao: UserPermission, nivel_solicitado: int) -> dict:
    registros = []
    for codigo, titulo, nivel, divisao, local, situacao, resumo in REGISTROS:
        if nivel <= nivel_solicitado and autorizar(permissao, nivel, divisao).granted:
            registros.append(
                {
                    "id": codigo,
                    "title": titulo,
                    "level": nivel,
                    "division": divisao,
                    "location": local,
                    "status": situacao,
                    "summary": resumo,
                }
            )
    return {"notice": AVISO, "records": registros}
