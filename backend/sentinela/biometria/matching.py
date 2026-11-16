from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence

import numpy as np

from sentinela.biometria.pipeline import normalizar_vetor_facial
from sentinela.config import BiometricConfig


class MatchStatus(StrEnum):
    MATCHED = "identificado"
    UNKNOWN = "desconhecido"
    AMBIGUOUS = "ambiguo"
    EMPTY = "sem_referencias"


@dataclass(frozen=True)
class Match:
    status: MatchStatus
    subject_id: str | None = None
    similarity: float | None = None
    margin: float | None = None


def identificar(
    consulta: np.ndarray, galeria: Mapping[str, Sequence[np.ndarray]], configuracao: BiometricConfig
) -> Match:
    consulta = normalizar_vetor_facial(consulta)
    pontuacoes = []
    for identificador, amostras in galeria.items():
        if len(amostras) == 0:
            continue
        similaridades = [float(consulta @ normalizar_vetor_facial(amostra)) for amostra in amostras]
        pontuacoes.append((float(np.mean(similaridades)), identificador))
    if not pontuacoes:
        return Match(MatchStatus.EMPTY)
    pontuacoes.sort(reverse=True)
    melhor_pontuacao, identificador = pontuacoes[0]
    melhor_pontuacao = float(np.clip(melhor_pontuacao, -1, 1))
    margem = melhor_pontuacao - pontuacoes[1][0] if len(pontuacoes) > 1 else None
    if melhor_pontuacao < configuracao.similarity_threshold:
        return Match(MatchStatus.UNKNOWN, similarity=melhor_pontuacao, margin=margem)
    if margem is not None and margem < configuracao.ambiguity_margin:
        return Match(MatchStatus.AMBIGUOUS, similarity=melhor_pontuacao, margin=margem)
    return Match(MatchStatus.MATCHED, identificador, melhor_pontuacao, margem)
