from __future__ import annotations

from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import AnonymousUser
from general_manager import AdditiveManagerPermission
from general_manager.manager.general_manager import GeneralManager
from general_manager.manager.meta import GeneralManagerMeta
from general_manager.permission import register_permission
from general_manager.permission.base_permission import ReadPermissionPlan
from general_manager.permission.permission_data_manager import PermissionDataManager


def _is_in_group(user: AbstractBaseUser | AnonymousUser, group_name: str) -> bool:
    groups = getattr(user, "groups", None)
    if groups is None:
        return False
    return bool(groups.filter(name=group_name).exists())


@register_permission("isAdminGroup")
def _permission_is_admin(
    _instance: PermissionDataManager[Any] | GeneralManager | GeneralManagerMeta,
    user: AbstractBaseUser | AnonymousUser,
    _config: list[str],
) -> bool:
    return _is_in_group(user, "Admin")


@register_permission("isProjektleiter")
def _permission_is_project_leader(
    _instance: PermissionDataManager[Any] | GeneralManager | GeneralManagerMeta,
    user: AbstractBaseUser | AnonymousUser,
    _config: list[str],
) -> bool:
    return _is_in_group(user, "Projektleiter")


@register_permission("isBetrachter")
def _permission_is_viewer(
    _instance: PermissionDataManager[Any] | GeneralManager | GeneralManagerMeta,
    user: AbstractBaseUser | AnonymousUser,
    _config: list[str],
) -> bool:
    return _is_in_group(user, "Betrachter")


class CalculationPermission(AdditiveManagerPermission):
    """Permission für CalculationInterface-Manager.

    GM's Instance-Check ruft queryset.filter(id__in=...) auf, was für
    CalculationBuckets fehlschlägt (kein 'id' im identification-dict).
    Verifiziert in 0.45.0: Workaround bleibt notwendig.
    """

    def get_read_permission_plan(self) -> ReadPermissionPlan:
        return ReadPermissionPlan(
            filters=[{"filter": {}, "exclude": {}}],
            requires_instance_check=False,
        )


@register_permission("isMonteur")
def _permission_is_mechanic(
    _instance: PermissionDataManager[Any] | GeneralManager | GeneralManagerMeta,
    user: AbstractBaseUser | AnonymousUser,
    _config: list[str],
) -> bool:
    return _is_in_group(user, "Monteur")
