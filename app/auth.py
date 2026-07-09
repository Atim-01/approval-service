"""Mock authentication for local development / this assignment.

A real deployment would replace this with a call to (or JWT issued by) the
platform's identity service. For this assessment, the caller identifies
itself via plain headers:

    X-Workspace-Id: <workspace id>
    X-User-Id: <user id>
    X-Permissions: comma separated list, e.g. "approval:read,approval:create"

No header value is ever logged verbatim beyond workspace/user ids, and none
of these headers carry secrets.
"""

from dataclasses import dataclass
from typing import FrozenSet

from fastapi import Header, HTTPException, status


VALID_PERMISSIONS = {
    "approval:read",
    "approval:create",
    "approval:decide",
    "approval:cancel",
}


@dataclass(frozen=True)
class Principal:
    workspace_id: str
    user_id: str
    permissions: FrozenSet[str]

    def has(self, permission: str) -> bool:
        return permission in self.permissions


def get_principal(
    x_workspace_id: str = Header(..., alias="X-Workspace-Id"),
    x_user_id: str = Header(..., alias="X-User-Id"),
    x_permissions: str = Header(default="", alias="X-Permissions"),
) -> Principal:
    workspace_id = x_workspace_id.strip()
    user_id = x_user_id.strip()

    if not workspace_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Workspace-Id is required")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-User-Id is required")

    perms = {p.strip() for p in x_permissions.split(",") if p.strip()}
    unknown = perms - VALID_PERMISSIONS
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"unknown permissions supplied: {sorted(unknown)}",
        )

    return Principal(workspace_id=workspace_id, user_id=user_id, permissions=frozenset(perms))


def require(principal: Principal, permission: str) -> None:
    if not principal.has(permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"missing required permission: {permission}",
        )