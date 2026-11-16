import pytest
from sentinela.autorizacao import UserPermission, autorizar


@pytest.mark.parametrize(
    "user,target,division,granted,reason",
    [
        (None, 1, None, False, "identidade_nao_autenticada"),
        (UserPermission(1), 1, None, True, "acesso_autorizado"),
        (UserPermission(1), 2, "ambiental", False, "nivel_insuficiente"),
        (UserPermission(2, frozenset({"a", "b"})), 1, None, True, "acesso_autorizado"),
        (UserPermission(2, frozenset({"a", "b"})), 2, "a", True, "acesso_autorizado"),
        (UserPermission(2, frozenset({"a", "b"})), 2, "b", True, "acesso_autorizado"),
        (UserPermission(2, frozenset({"a"})), 2, "b", False, "divisao_nao_autorizada"),
        (UserPermission(2, frozenset({"a"})), 3, None, False, "nivel_insuficiente"),
        (UserPermission(3), 1, None, True, "acesso_autorizado"),
        (UserPermission(3), 2, "qualquer", True, "acesso_autorizado"),
        (UserPermission(3), 3, None, True, "acesso_autorizado"),
        (UserPermission(3, active=False), 3, None, False, "usuario_inativo"),
        (UserPermission(3), 4, None, False, "recurso_invalido"),
        (UserPermission(3), 2, None, False, "recurso_invalido"),
        (UserPermission(3), 1, "a", False, "recurso_invalido"),
    ],
)
def test_policy(user, target, division, granted, reason):
    result = autorizar(user, target, division)
    assert (result.granted, result.reason) == (granted, reason)


@pytest.mark.parametrize("level,divisions", [(0, []), (4, []), (2, []), (1, ["a"]), (2, [""])])
def test_invalid_permissions(level, divisions):
    with pytest.raises(ValueError):
        UserPermission(level, frozenset(divisions))
