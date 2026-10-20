"""Project role checks. Membership is CRM data. It is not a Control Plane role."""

from dataclasses import dataclass

PROJECT_MANAGER = "project_manager"
PROJECT_MEMBER = "project_member"
SCOPE_PROJECT = "project"
SCOPE_ASSIGNED = "assigned"
ACTIVE = "active"

PROJECT_MANAGE_PERMISSION = "crm.project_management.manage"
REGISTERED_CRM_PERMISSION = "crm.lead_management.read"

ROLE_SCOPE = {
    PROJECT_MANAGER: SCOPE_PROJECT,
    PROJECT_MEMBER: SCOPE_ASSIGNED,
}

# Future record routes must call access_for and allows("access_records"), then
# honor record_scope: project means every record in the project, assigned means
# only records assigned to that member. This sprint does not store records.
ACTIONS = {
    "view_project": frozenset({PROJECT_MANAGER, PROJECT_MEMBER}),
    "list_members": frozenset({PROJECT_MANAGER, PROJECT_MEMBER}),
    "add_member": frozenset({PROJECT_MANAGER}),
    "remove_member": frozenset({PROJECT_MANAGER}),
    "assign_role": frozenset({PROJECT_MANAGER}),
    "update_project": frozenset({PROJECT_MANAGER}),
    "archive_project": frozenset({PROJECT_MANAGER}),
    "access_records": frozenset({PROJECT_MANAGER, PROJECT_MEMBER}),
    # Form definitions are CRM data. Lead read does not administer them.
    # A project manager administers forms in that project. A project member
    # may read them. crm.project_management.manage remains the only tenant-wide key.
    "view_forms": frozenset({PROJECT_MANAGER, PROJECT_MEMBER}),
    "manage_forms": frozenset({PROJECT_MANAGER}),
}


class ProjectAccess:
    def __init__(self, *, role: str | None, scope_policy: str | None, tenant_admin: bool) -> None:
        self.role = role
        self.scope_policy = scope_policy
        self.tenant_admin = tenant_admin

    def allows(self, action: str) -> bool:
        permitted = ACTIONS.get(action)
        if permitted is None:
            return False
        if self.tenant_admin:
            return True
        return self.role in permitted

    def record_scope(self) -> str | None:
        """Scope a later record query must apply. None means no record access."""

        if not self.allows("access_records"):
            return None
        if self.tenant_admin:
            return SCOPE_PROJECT
        return self.scope_policy

    def as_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "scope_policy": self.scope_policy if self.allows("view_project") else None,
            "can_manage_project": self.allows("update_project") and self.allows("archive_project"),
            "can_manage_members": self.allows("add_member")
            and self.allows("remove_member")
            and self.allows("assign_role"),
            "can_manage_forms": self.allows("manage_forms"),
            "can_access_records": self.allows("access_records"),
            "record_scope": self.record_scope(),
        }


def module_allowed(keys: list[str]) -> bool:
    """Whether the caller may open the project module and create a project.

    This is not permission to read or change every project in the tenant.
    """

    return PROJECT_MANAGE_PERMISSION in keys or REGISTERED_CRM_PERMISSION in keys


def tenant_project_admin(keys: list[str]) -> bool:
    """Tenant-wide project administration from CRM-S3-03.

    Only `crm.project_management.manage` grants it. Lead read does not.
    The key is not on the current Control Plane registration.
    """

    return PROJECT_MANAGE_PERMISSION in keys


def access_for(*, role: str | None, status: str | None, permission_keys: list[str]) -> ProjectAccess:
    admin = tenant_project_admin(permission_keys)
    active_role = role if status == ACTIVE and role in ROLE_SCOPE else None
    if active_role is not None:
        return ProjectAccess(
            role=active_role,
            scope_policy=ROLE_SCOPE[active_role],
            tenant_admin=admin,
        )
    if admin:
        return ProjectAccess(role=None, scope_policy=SCOPE_PROJECT, tenant_admin=True)
    return ProjectAccess(role=None, scope_policy=None, tenant_admin=False)


def scope_for_role(role: str) -> str:
    try:
        return ROLE_SCOPE[role]
    except KeyError:
        raise ValueError(role) from None


@dataclass(frozen=True)
class RecordRef:
    """Input for a future record route. CRM does not store records yet."""

    tenant_id: str
    project_id: str
    assignee_user_id: str | None


@dataclass(frozen=True)
class RecordDecision:
    allowed: bool
    scope: str | None


def decide_record_access(
    *,
    caller_user_id: str,
    authorized_tenant_id: str,
    authorized_project_id: str,
    access: ProjectAccess,
    record: RecordRef,
) -> RecordDecision:
    """Decide one record. A later record route must call this on every request.

    A manager may use records in the authorized project. A member may use only
    records in that project assigned to the caller. Another tenant, another
    project, a removed membership, and a missing membership are denied. The
    decision does not include names from the other tenant or project.
    """

    denied = RecordDecision(allowed=False, scope=None)
    if record.tenant_id != authorized_tenant_id or record.project_id != authorized_project_id:
        return denied
    if not access.allows("access_records"):
        return denied
    scope = access.record_scope()
    if scope == SCOPE_PROJECT:
        return RecordDecision(allowed=True, scope=SCOPE_PROJECT)
    if scope == SCOPE_ASSIGNED and record.assignee_user_id == caller_user_id:
        return RecordDecision(allowed=True, scope=SCOPE_ASSIGNED)
    return denied
