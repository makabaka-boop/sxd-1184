from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas, auth
from ..database import get_db
from ..models import BatchStatus

router = APIRouter(tags=["评审管理"])


@router.post("/reviews", response_model=schemas.ReviewResponse)
def submit_review(
    review: schemas.ReviewCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    batch = db.query(models.Batch).filter(
        models.Batch.id == review.batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="试配批次不存在")

    if batch.status != BatchStatus.REVIEWING:
        raise HTTPException(
            status_code=400,
            detail=f"当前批次状态为 {batch.status.value}，不可提交评审"
        )

    current_round = batch.round_no

    if review.is_valid:
        existing_valid = db.query(models.Review).join(models.Batch).filter(
            models.Batch.recipe_id == batch.recipe_id,
            models.Review.reviewer_id == current_user.id,
            models.Review.round_no == current_round,
            models.Review.is_valid == True
        ).first()
        if existing_valid:
            raise HTTPException(
                status_code=400,
                detail="您在该配方版本当前轮次已提交过有效评审，不可重复提交"
            )

    db_review = models.Review(
        **review.model_dump(exclude_unset=True),
        reviewer_id=current_user.id,
        round_no=current_round
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review


@router.get("/batches/{batch_id}/reviews", response_model=List[schemas.ReviewResponse])
def list_batch_reviews(
    batch_id: int,
    round_no: Optional[int] = None,
    is_valid: Optional[bool] = None,
    reviewer_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    batch = db.query(models.Batch).filter(
        models.Batch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="试配批次不存在")

    query = db.query(models.Review).filter(models.Review.batch_id == batch_id)
    if round_no:
        query = query.filter(models.Review.round_no == round_no)
    if is_valid is not None:
        query = query.filter(models.Review.is_valid == is_valid)
    if reviewer_id:
        query = query.filter(models.Review.reviewer_id == reviewer_id)

    reviews = query.order_by(models.Review.submitted_at.desc()).all()
    return reviews


@router.get("/reviews", response_model=List[schemas.ReviewResponse])
def list_reviews(
    skip: int = 0,
    limit: int = 100,
    batch_id: Optional[int] = None,
    recipe_id: Optional[int] = None,
    recipe_version: Optional[str] = None,
    batch_status: Optional[BatchStatus] = None,
    reviewer_id: Optional[int] = None,
    round_no: Optional[int] = None,
    is_valid: Optional[bool] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    exclude_terminated: bool = True,
    exclude_finalized: bool = False,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    query = db.query(models.Review).join(models.Batch).join(models.Recipe)

    if batch_id:
        query = query.filter(models.Review.batch_id == batch_id)
    if recipe_id:
        query = query.filter(models.Batch.recipe_id == recipe_id)
    if recipe_version:
        query = query.filter(models.Recipe.version == recipe_version)
    if batch_status:
        query = query.filter(models.Batch.status == batch_status)
    if reviewer_id:
        query = query.filter(models.Review.reviewer_id == reviewer_id)
    if round_no:
        query = query.filter(models.Review.round_no == round_no)
    if is_valid is not None:
        query = query.filter(models.Review.is_valid == is_valid)
    if exclude_terminated:
        query = query.filter(models.Batch.status != BatchStatus.TERMINATED)
    if exclude_finalized:
        query = query.filter(models.Batch.status != BatchStatus.FINALIZED)
    if start_date:
        query = query.filter(models.Review.submitted_at >= start_date)
    if end_date:
        query = query.filter(models.Review.submitted_at <= end_date)

    if min_score is not None:
        avg_score = (models.Review.sweetness + models.Review.consistency + models.Review.melt_speed) / 3
        query = query.filter(avg_score >= min_score)
    if max_score is not None:
        avg_score = (models.Review.sweetness + models.Review.consistency + models.Review.melt_speed) / 3
        query = query.filter(avg_score <= max_score)

    reviews = query.order_by(models.Review.submitted_at.desc()).offset(skip).limit(limit).all()
    return reviews


@router.get("/reviews/{review_id}", response_model=schemas.ReviewResponse)
def get_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    review = db.query(models.Review).filter(
        models.Review.id == review_id
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="评审记录不存在")
    return review


@router.post("/batches/{batch_id}/adjustments", response_model=schemas.AdjustmentResponse)
def submit_adjustment(
    batch_id: int,
    adj: schemas.AdjustmentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    batch = db.query(models.Batch).filter(
        models.Batch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="试配批次不存在")

    if batch.status not in [BatchStatus.REVIEWING, BatchStatus.NEED_ADJUST]:
        raise HTTPException(
            status_code=400,
            detail=f"当前状态 {batch.status.value}，不可提交调整"
        )

    db_adj = models.AdjustmentRecord(
        batch_id=batch_id,
        round_no=batch.round_no,
        adjustment_details=adj.adjustment_details,
        adjuster_id=current_user.id,
        next_round_scheduled=adj.next_round_scheduled
    )
    db.add(db_adj)

    if batch.status == BatchStatus.REVIEWING:
        batch.status = BatchStatus.NEED_ADJUST

    db.commit()
    db.refresh(db_adj)
    return db_adj


@router.get("/batches/{batch_id}/adjustments", response_model=List[schemas.AdjustmentResponse])
def list_adjustments(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    batch = db.query(models.Batch).filter(
        models.Batch.id == batch_id
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="试配批次不存在")

    adjustments = db.query(models.AdjustmentRecord).filter(
        models.AdjustmentRecord.batch_id == batch_id
    ).order_by(models.AdjustmentRecord.adjusted_at.desc()).all()
    return adjustments


@router.get("/users", response_model=List[schemas.UserResponse])
def list_users(
    skip: int = 0,
    limit: int = 100,
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    query = db.query(models.User).filter(models.User.is_active == True)
    if role:
        query = query.filter(models.User.role == role)
    users = query.offset(skip).limit(limit).all()
    return users
