from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence

import numpy as np

from sentinela.biometria.pipeline import normalized_embedding
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


def identify(
        query: np.ndarray, gallery: Mapping[str, Sequence[np.ndarray]], config: BiometricConfig
) -> Match:
    """Média dos cossenos por identidade; segundo colocado é outra pessoa."""
    query = normalized_embedding(query)
    scores = []
    for subject_id, samples in gallery.items():
        if len(samples) == 0:
            continue
        similarities = [float(query @ normalized_embedding(sample)) for sample in samples]
        scores.append((float(np.mean(similarities)), subject_id))
    if not scores:
        return Match(MatchStatus.EMPTY)
    scores.sort(reverse=True)
    best, subject_id = scores[0]
    best = float(np.clip(best, -1, 1))
    margin = best - scores[1][0] if len(scores) > 1 else None
    if best < config.similarity_threshold:
        return Match(MatchStatus.UNKNOWN, similarity=best, margin=margin)
    if margin is not None and margin < config.ambiguity_margin:
        return Match(MatchStatus.AMBIGUOUS, similarity=best, margin=margin)
    return Match(MatchStatus.MATCHED, subject_id, best, margin)
