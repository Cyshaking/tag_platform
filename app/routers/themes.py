"""
routers/themes.py — 业务主题管理（V1.1 新增）
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies import get_current_user
from app.schemas.common import ApiResponse
from app.schemas.theme import ThemeCreate, ThemeUpdate
from app.services.theme_service import ThemeService

router = APIRouter(prefix="/api/themes", tags=["themes"])


def _serialize(theme) -> dict:
    table = theme.main_table
    return {
        "id": theme.id, "serial_no": theme.serial_no,
        "theme_code": theme.theme_code,
        "theme_name": theme.theme_name,
        "main_table_id": theme.main_table_id,
        "main_table_name": table.table_name if table else None,
        "main_table_comment": table.table_comment if table else None,
        "description": theme.description,
        "is_enabled": theme.is_enabled,
        "created_at": theme.created_at.isoformat() if theme.created_at else None,
        "updated_at": theme.updated_at.isoformat() if theme.updated_at else None,
    }


@router.get("")
def list_themes(db: Session = Depends(get_db)):
    svc = ThemeService(db)
    return ApiResponse(data=[_serialize(t) for t in svc.list_themes()])


@router.get("/{theme_id}/tables")
def get_theme_table(theme_id: int, db: Session = Depends(get_db)):
    """主题表信息（含字段），供标签任务页字段配置使用"""
    svc = ThemeService(db)
    table = svc.get_theme_table(theme_id)
    return ApiResponse(data={
        "table_id": table.id,
        "table_name": table.table_name,
        "table_comment": table.table_comment,
        "fields": [
            {
                "id": f.id, "field_name": f.field_name, "field_type": f.field_type,
                "field_comment": f.field_comment, "is_primary_key": f.is_primary_key,
                "ordinal_position": f.ordinal_position,
            } for f in table.fields
        ],
    })


@router.get("/{theme_id}")
def get_theme(theme_id: int, db: Session = Depends(get_db)):
    svc = ThemeService(db)
    theme = svc.get_theme(theme_id)
    if not theme:
        return ApiResponse(code=40400, message="业务主题不存在")
    return ApiResponse(data=_serialize(theme))


@router.post("")
def create_theme(req: ThemeCreate,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = ThemeService(db)
    theme = svc.create_theme(
        theme_code=req.theme_code, theme_name=req.theme_name,
        main_table_id=req.main_table_id, description=req.description,
        is_enabled=req.is_enabled, operator_id=current_user.id,
    )
    return ApiResponse(data={"id": theme.id})


@router.put("/{theme_id}")
def update_theme(theme_id: int, req: ThemeUpdate,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = ThemeService(db)
    svc.update_theme(
        theme_id=theme_id, theme_name=req.theme_name,
        main_table_id=req.main_table_id, description=req.description,
        is_enabled=req.is_enabled, operator_id=current_user.id,
    )
    return ApiResponse()


@router.delete("/{theme_id}")
def delete_theme(theme_id: int,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = ThemeService(db)
    svc.delete_theme(theme_id=theme_id, operator_id=current_user.id)
    return ApiResponse()
