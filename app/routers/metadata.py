"""
routers/metadata.py — 元数据接入（CRUD + Excel 模板下载 + 导入）
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models.user import User
from app.dependencies import get_current_user, require_permission
from app.schemas.common import ApiResponse
from app.schemas.metadata import MetaTableCreate, MetaTableUpdate
from app.services.metadata_service import MetadataService

router = APIRouter(prefix="/api/metadata", tags=["metadata"])


def _serialize_table(t) -> dict:
    return {
        "id": t.id, "serial_no": t.serial_no, "table_name": t.table_name, "table_comment": t.table_comment,
        "datasource_id": t.datasource_id, "status": t.status,
        "created_by": t.created_by, "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "fields": [{
            "id": f.id, "field_name": f.field_name, "field_type": f.field_type,
            "field_comment": f.field_comment, "is_primary_key": f.is_primary_key,
            "is_nullable": f.is_nullable, "ordinal_position": f.ordinal_position,
        } for f in t.fields],
    }


@router.get("/tables")
def list_tables(status: Optional[str] = None,
                current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = MetadataService(db)
    tables = svc.list_tables(status=status)
    return ApiResponse(data=[_serialize_table(t) for t in tables])


@router.get("/tables/{table_id}")
def get_table(table_id: int,
              current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = MetadataService(db)
    table = svc.get_table(table_id)
    if not table:
        raise HTTPException(status_code=404, detail="表不存在")
    return ApiResponse(data=_serialize_table(table))


@router.post("/tables", dependencies=[Depends(require_permission("metadata:edit"))])
def create_table(req: MetaTableCreate,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = MetadataService(db)
    table = svc.create_table(
        table_name=req.table_name,
        table_comment=req.table_comment,
        fields=[f.model_dump() for f in req.fields],
        datasource_id=req.datasource_id,
        created_by=current_user.id,
    )
    return ApiResponse(data={"id": table.id})


@router.put("/tables/{table_id}", dependencies=[Depends(require_permission("metadata:edit"))])
def update_table(table_id: int, req: MetaTableUpdate,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = MetadataService(db)
    svc.update_table(
        table_id=table_id,
        table_comment=req.table_comment,
        datasource_id=req.datasource_id,
        fields=[f.model_dump() for f in req.fields] if req.fields is not None else None,
        operator_id=current_user.id,
    )
    return ApiResponse()


@router.delete("/tables/{table_id}", dependencies=[Depends(require_permission("metadata:edit"))])
def delete_table(table_id: int,
                 current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    svc = MetadataService(db)
    svc.delete_table(table_id=table_id, operator_id=current_user.id)
    return ApiResponse()


# ========== 模板下载 ==========
@router.get("/template")
def download_template(current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    svc = MetadataService(db)
    bytes_data = svc.generate_template()
    return Response(
        content=bytes_data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=metadata_template.xlsx"},
    )


# ========== Excel 导入 ==========
@router.post("/import", dependencies=[Depends(require_permission("metadata:edit"))])
async def import_excel(file: UploadFile = File(...),
                       current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 校验文件扩展名
    fname = (file.filename or "").lower()
    if not fname.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")

    svc = MetadataService(db)
    table = svc.import_excel(file_bytes=content, created_by=current_user.id)
    return ApiResponse(data={
        "table": _serialize_table(table),
        "field_count": len(table.fields),
    })
