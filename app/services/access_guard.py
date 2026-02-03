from __future__ import annotations

from app.services.access_service import get_org_access


def require_org_edit(*, user_id: int, role_code: str, org_id: int) -> None:
    acc = get_org_access(user_id=user_id, role_code=role_code, org_id=org_id)
    if not acc.can_edit:
        raise PermissionError("Недостаточно прав: требуется редактирование учреждения")
