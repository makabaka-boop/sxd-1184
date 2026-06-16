from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas, auth
from ..database import get_db
from ..models import BatchStatus

router = APIRouter(prefix="/batches", tags=["试配批次"])


@router.post("/", response_model=schemas.BatchResponse)
def create_batch(
    batch: schemas.BatchCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    existing = db.query(models.Batch).filter(
        models.Batch.batch_no == batch.batch_no
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="试配批号已存在")

    recipe = db.query(models.Recipe).filter(
        models.Recipe.id == batch.recipe_id
    ).first()
    if not recipe:
        raise HTTPException(status_code=400, detail="配方不存在")

    if batch.responsible_id:
        user = db.query(models.User).filter(
            models.User.id == batch.responsible_id
        ).first()
        if not user:
            raise HTTPException(status_code=400, detail="责任人不存在")

    db_batch = models.Batch(**batch.model_dump())
    db.add(db_batch)
    db.commit()
    db.refresh(db_batch)
    return db_batch


@router.get("/", response_model=List[schemas.BatchResponse])
def list_batches(
    skip: int = 0,
    limit: int = 100,
    batch_no: Optional[str] = None,
    recipe_id: Optional[int] = None,
    recipe_name: Optional[str] = None,
    recipe_version: Optional[str] = None,
    status: Optional[BatchStatus] = None,
    round_no: Optional[int] = None,
    responsible_id: Optional[int] = None,
    exclude_terminated: bool = True,
    exclude_finalized: bool = False,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    query = db.query(models.Batch)
    if batch_no:
        query = query.filter(models.Batch.batch_no.contains(batch_no))
    if recipe_id:
        query = query.filter(models.Batch.recipe_id == recipe_id)
    if recipe_name or recipe_version:
        query = query.join(models.Recipe)
        if recipe_name:
            query = query.filter(models.Recipe.name.contains(recipe_name))
        if recipe_version:
            query = query.filter(models.Recipe.version == recipe_version)
    if status:
        query = query.filter(models.Batch.status == status)
    if exclude_terminated:
        query = query.filter(models.Batch.status != BatchStatus.TERMINATED)
    if exclude_finalized:
        query = query.filter(models.Batch.status != BatchStatus.FINALIZED)
    if round_no:
        query = query.filter(models.Batch.round_no == round_no)
    if responsible_id:
        query = query.filter(models.Batch.responsible_id == responsible_id)
    if start_date:
        query = query.filter(models.Batch.created_at >= start_date)
    if end_date:
        query = query.filter(models.Batch.created_at <= end_date)

    batches = query.order_by(models.Batch.created_at.desc()).offset(skip).limit(limit).all()
    return batches


@router.get("/{batch_id}", response_model=schemas.BatchResponse)
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    batch = db.query(models.Batch).filter(
        models.Batch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="试配批次不存在")
    return batch


@router.put("/{batch_id}", response_model=schemas.BatchResponse)
def update_batch(
    batch_id: int,
    batch_update: schemas.BatchUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    batch = db.query(models.Batch).filter(
        models.Batch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="试配批次不存在")

    update_data = batch_update.model_dump(exclude_unset=True)
    if "responsible_id" in update_data and update_data["responsible_id"]:
        user = db.query(models.User).filter(
            models.User.id == update_data["responsible_id"]
        ).first()
        if not user:
            raise HTTPException(status_code=400, detail="责任人不存在")

    for key, value in update_data.items():
        setattr(batch, key, value)

    db.commit()
    db.refresh(batch)
    return batch


@router.delete("/{batch_id}")
def delete_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    batch = db.query(models.Batch).filter(
        models.Batch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="试配批次不存在")

    db.delete(batch)
    db.commit()
    return {"message": "删除成功"}


@router.post("/{batch_id}/start-review", response_model=schemas.BatchResponse)
def start_review_round(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    batch = db.query(models.Batch).filter(
        models.Batch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="试配批次不存在")

    if batch.status not in [BatchStatus.PENDING_REVIEW, BatchStatus.NEED_ADJUST]:
        if batch.status == BatchStatus.PENDING_TRIAL:
            raise HTTPException(status_code=400, detail="请先完成试配")
        raise HTTPException(status_code=400, detail=f"当前状态 {batch.status.value} 不可开启评审")

    if batch.status == BatchStatus.NEED_ADJUST:
        batch.round_no += 1

    batch.status = BatchStatus.REVIEWING
    db.commit()
    db.refresh(batch)
    return batch


@router.post("/{batch_id}/finish-trial", response_model=schemas.BatchResponse)
def finish_trial(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    batch = db.query(models.Batch).filter(
        models.Batch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="试配批次不存在")

    if batch.status != BatchStatus.PENDING_TRIAL:
        raise HTTPException(status_code=400, detail=f"当前状态 {batch.status.value} 不可操作")

    batch.status = BatchStatus.PENDING_REVIEW
    batch.trial_date = datetime.utcnow()
    db.commit()
    db.refresh(batch)
    return batch


@router.post("/{batch_id}/finalize", response_model=schemas.BatchResponse)
def finalize_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    batch = db.query(models.Batch).filter(
        models.Batch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="试配批次不存在")

    if batch.status != BatchStatus.REVIEWING:
        raise HTTPException(status_code=400, detail=f"当前状态 {batch.status.value} 不可定版")

    batch.status = BatchStatus.FINALIZED
    db.commit()
    db.refresh(batch)
    return batch


@router.post("/{batch_id}/terminate", response_model=schemas.BatchResponse)
def terminate_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    batch = db.query(models.Batch).filter(
        models.Batch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="试配批次不存在")

    if batch.status in [BatchStatus.FINALIZED, BatchStatus.TERMINATED]:
        raise HTTPException(status_code=400, detail=f"当前状态 {batch.status.value} 不可终止")

    batch.status = BatchStatus.TERMINATED
    db.commit()
    db.refresh(batch)
    return batch
