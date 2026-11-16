from dataclasses import dataclass


@dataclass(frozen=True)
class UserPermission:
    level: int
    divisions: frozenset[str] = frozenset()
    active: bool = True

    def __post_init__(self):
        if self.level not in (1, 2, 3):
            raise ValueError("Nível deve ser 1, 2 ou 3.")
        if any(not division.strip() for division in self.divisions):
            raise ValueError("Divisão vazia.")
        if self.level != 2 and self.divisions:
            raise ValueError("Somente diretores recebem divisões explícitas.")
        if self.level == 2 and not self.divisions:
            raise ValueError("Diretor precisa de pelo menos uma divisão autorizada.")


@dataclass(frozen=True)
class AccessDecision:
    granted: bool
    reason: str


def authorize(
        user: UserPermission | None, requested_level: int, division: str | None = None
) -> AccessDecision:
    if requested_level not in (1, 2, 3):
        return AccessDecision(False, "recurso_invalido")
    if (requested_level == 2 and not division) or (requested_level != 2 and division is not None):
        return AccessDecision(False, "recurso_invalido")
    if user is None:
        return AccessDecision(False, "identidade_nao_autenticada")
    if not user.active:
        return AccessDecision(False, "usuario_inativo")
    if user.level < requested_level:
        return AccessDecision(False, "nivel_insuficiente")
    if requested_level == 2 and user.level != 3 and division not in user.divisions:
        return AccessDecision(False, "divisao_nao_autorizada")
    return AccessDecision(True, "acesso_autorizado")
