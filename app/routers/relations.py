"""
routers/relations.py — 表关联关系
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies import get_current_user, require_permission
from app.schemas.common import ApiResponse
from app.schemas.relation import RelationCreate, RelationUpdate
from app.services.relation_service import RelationService

router = APIRouter(prefix="/api/relations", tags=["relations"])


def _serialize(r) -> dict:
    return {
        "id": r.id, "serial_no": r.serial_no,
        "left_table_id": r.left_table_id, "left_field_id": r.left_field_id,
        "right_table_id": r.right_table_id, "right_field_id": r.right_field_id,
        "relation_type": r.relation_type,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("")
def list_relations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = RelationService(db)
    return ApiResponse(data=[_serialize(r) for r in svc.list_relations()])


@router.post("", dependencies=[Depends(require_permission("relation:edit"))])
def create_relation(req: RelationCreate,
                     current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = RelationService(db)
    r = svc.create_relation(
        left_table_id=req.left_table_id, left_field_id=req.left_field_id,
        right_table_id=req.right_table_id, right_field_id=req.right_field_id,
        relation_type=req.relation_type, created_by=current_user.id,
    )
    return ApiResponse(data={"id": r.id})


@router.put("/{relation_id}", dependencies=[Depends(require_permission("relation:edit"))])
def update_relation(relation_id: int, req: RelationUpdate,
                     current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = RelationService(db)
    svc.update_relation(
        relation_id=relation_id,
        relation_type=req.relation_type,
        left_field_id=req.left_field_id,
        right_field_id=req.right_field_id,
        operator_id=current_user.id,
    )
    return ApiResponse()


@router.delete("/{relation_id}", dependencies=[Depends(require_permission("relation:edit"))])
def delete_relation(relation_id: int,
                     current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = RelationService(db)
    svc.delete_relation(relation_id=relation_id, operator_id=current_user.id)
    return ApiResponse()
