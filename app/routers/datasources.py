"""
routers/datasources.py — 数据源管理
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies import get_current_user
from app.schemas.common import ApiResponse
from app.schemas.datasource import DatasourceCreate, DatasourceUpdate, DatasourceTestResult, DatasourceTestConnection
from app.services.datasource_service import DatasourceService

router = APIRouter(prefix="/api/datasources", tags=["datasources"])


def _serialize(ds, svc: DatasourceService) -> dict:
    return svc.serialize(ds)


@router.get("")
def list_datasources(include_disabled: bool = True, db: Session = Depends(get_db)):
    svc = DatasourceService(db)
    return ApiResponse(data=[_serialize(ds, svc) for ds in svc.list_datasources(include_disabled=include_disabled)])


@router.get("/enabled")
def list_enabled_datasources(db: Session = Depends(get_db)):
    """前端下拉只展示已启用的数据源"""
    svc = DatasourceService(db)
    return ApiResponse(data=[_serialize(ds, svc) for ds in svc.list_datasources(include_disabled=False)])


@router.get("/{ds_id}")
def get_datasource(ds_id: int, db: Session = Depends(get_db)):
    svc = DatasourceService(db)
    ds = svc.get_datasource(ds_id)
    if not ds:
        return ApiResponse(code=40400, message="数据源不存在")
    return ApiResponse(data=_serialize(ds, svc))


@router.post("")
def create_datasource(req: DatasourceCreate,
                       current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = DatasourceService(db)
    ds = svc.create_datasource(
        name=req.name, ds_type=req.ds_type, config=req.config,
        is_enabled=req.is_enabled, remark=req.remark,
        operator_id=current_user.id,
    )
    return ApiResponse(data={"id": ds.id})


@router.put("/{ds_id}")
def update_datasource(ds_id: int, req: DatasourceUpdate,
                       current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = DatasourceService(db)
    svc.update_datasource(
        ds_id=ds_id, name=req.name, config=req.config,
        is_enabled=req.is_enabled, remark=req.remark,
        operator_id=current_user.id,
    )
    return ApiResponse()


@router.delete("/{ds_id}")
def delete_datasource(ds_id: int,
                       current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = DatasourceService(db)
    svc.delete_datasource(ds_id=ds_id, operator_id=current_user.id)
    return ApiResponse()


@router.post("/{ds_id}/toggle")
def toggle_enabled(ds_id: int, enabled: bool,
                    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = DatasourceService(db)
    svc.toggle_enabled(ds_id=ds_id, enabled=enabled, operator_id=current_user.id)
    return ApiResponse()


@router.post("/test-connection", response_model=ApiResponse[DatasourceTestResult])
def test_connection(req: DatasourceTestConnection):
    """测试连接（不保存）"""
    result = DatasourceService.test_connection(ds_type=req.ds_type, config=req.config)
    return ApiResponse(data=result)
