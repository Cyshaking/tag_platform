"""
routers/enum_config.py — 字段枚举配置
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies import get_current_user, require_permission
from app.schemas.common import ApiResponse
from app.schemas.enum_config import EnumBatchCreate
from app.services.enum_service import EnumService

router = APIRouter(prefix="/api/enums", tags=["enums"])


def _serialize(e) -> dict:
    return {
        "id": e.id, "table_id": e.table_id, "field_id": e.field_id,
        "enum_code": e.enum_code, "enum_label": e.enum_label, "ordinal": e.ordinal,
    }


@router.get("")
def list_enums(field_id: Optional[int] = None, table_id: Optional[int] = None,
               current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = EnumService(db)
    return ApiResponse(data=[_serialize(e) for e in svc.list_enums(field_id=field_id, table_id=table_id)])


@router.post("", dependencies=[Depends(require_permission("enum:edit"))])
def save_enums(req: EnumBatchCreate,
               current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = EnumService(db)
    enums = svc.save_field_enums(
        table_id=req.table_id,
        field_id=req.field_id,
        enums=[e.model_dump() for e in req.enums],
        operator_id=current_user.id,
    )
    return ApiResponse(data={"count": len(enums)})


@router.delete("/{enum_id}", dependencies=[Depends(require_permission("enum:edit"))])
def delete_enum(enum_id: int,
                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = EnumService(db)
    svc.delete_enum(enum_id=enum_id, operator_id=current_user.id)
    return ApiResponse()
