from dataclasses import dataclass


@dataclass(frozen=True)
class UserPermission:
    level: int
    divisions: frozenset[str] = frozenset()
    active: bool = True

    def __post_init__(self):
        if self.level not in (1, 2, 3):
            raise ValueError("Nível deve ser 1, 2 ou 3.")
        if any(not divisao.strip() for divisao in self.divisions):
            raise ValueError("Divisão vazia.")
        if self.level != 2 and self.divisions:
            raise ValueError("Somente diretores recebem divisões explícitas.")
        if self.level == 2 and not self.divisions:
            raise ValueError("Diretor precisa de pelo menos uma divisão autorizada.")


@dataclass(frozen=True)
class AccessDecision:
    granted: bool
    reason: str


def autorizar(
    usuario: UserPermission | None, nivel_solicitado: int, divisao: str | None = None
) -> AccessDecision:
    if nivel_solicitado not in (1, 2, 3):
        return AccessDecision(False, "recurso_invalido")
    if (nivel_solicitado == 2 and not divisao) or (nivel_solicitado != 2 and divisao is not None):
        return AccessDecision(False, "recurso_invalido")
    if usuario is None:
        return AccessDecision(False, "identidade_nao_autenticada")
    if not usuario.active:
        return AccessDecision(False, "usuario_inativo")
    if usuario.level < nivel_solicitado:
        return AccessDecision(False, "nivel_insuficiente")
    if nivel_solicitado == 2 and usuario.level != 3 and divisao not in usuario.divisions:
        return AccessDecision(False, "divisao_nao_autorizada")
    return AccessDecision(True, "acesso_autorizado")
