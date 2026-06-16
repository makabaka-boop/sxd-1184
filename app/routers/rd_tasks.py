from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from .. import models, schemas, auth
from ..database import get_db
from ..models import TaskStage, TaskPriority, BatchStatus

router = APIRouter(prefix="/rd-tasks", tags=["研发任务看板"])


def _enrich_task(task: models.RdTask, db: Session) -> schemas.RdTaskResponse:
    is_overdue = (
        task.target_date is not None
        and task.stage not in [TaskStage.FINALIZED, TaskStage.CLOSED]
        and task.target_date < datetime.utcnow()
    )
    task_batches_out = []
    for tb in task.task_batches:
        batch = tb.batch
        task_batches_out.append(schemas.RdTaskBatchBrief(
            id=tb.id,
            batch_id=batch.id,
            batch_no=batch.batch_no,
            batch_status=batch.status,
            round_no=batch.round_no,
        ))
    return schemas.RdTaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        priority=task.priority,
        stage=task.stage,
        ingredient_group_id=task.ingredient_group_id,
        recipe_id=task.recipe_id,
        responsible_id=task.responsible_id,
        target_date=task.target_date,
        close_reason=task.close_reason,
        created_at=task.created_at,
        updated_at=task.updated_at,
        is_overdue=is_overdue,
        ingredient_group=task.ingredient_group,
        recipe=task.recipe,
        responsible_person=task.responsible_person,
        task_batches=task_batches_out,
    )


@router.post("/", response_model=schemas.RdTaskResponse)
def create_rd_task(
    task_in: schemas.RdTaskCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    if task_in.ingredient_group_id:
        ig = db.query(models.IngredientGroup).filter(
            models.IngredientGroup.id == task_in.ingredient_group_id
        ).first()
        if not ig:
            raise HTTPException(status_code=400, detail="原料组不存在")

    if task_in.recipe_id:
        recipe = db.query(models.Recipe).filter(
            models.Recipe.id == task_in.recipe_id
        ).first()
        if not recipe:
            raise HTTPException(status_code=400, detail="配方不存在")

    if task_in.responsible_id:
        user = db.query(models.User).filter(
            models.User.id == task_in.responsible_id
        ).first()
        if not user:
            raise HTTPException(status_code=400, detail="责任人不存在")

    batch_ids = task_in.batch_ids or []
    for bid in batch_ids:
        batch = db.query(models.Batch).filter(models.Batch.id == bid).first()
        if not batch:
            raise HTTPException(status_code=400, detail=f"批次 {bid} 不存在")

    task_data = task_in.model_dump(exclude={"batch_ids"})
    db_task = models.RdTask(**task_data)
    db.add(db_task)
    db.flush()

    for bid in batch_ids:
        tb = models.RdTaskBatch(task_id=db_task.id, batch_id=bid)
        db.add(tb)

    db.commit()
    db.refresh(db_task)

    task = db.query(models.RdTask).options(
        joinedload(models.RdTask.ingredient_group),
        joinedload(models.RdTask.recipe),
        joinedload(models.RdTask.responsible_person),
        joinedload(models.RdTask.task_batches).joinedload(models.RdTaskBatch.batch),
    ).filter(models.RdTask.id == db_task.id).first()

    return _enrich_task(task, db)


@router.get("/", response_model=List[schemas.RdTaskResponse])
def list_rd_tasks(
    skip: int = 0,
    limit: int = 100,
    responsible_id: Optional[int] = None,
    stage: Optional[TaskStage] = None,
    priority: Optional[TaskPriority] = None,
    recipe_id: Optional[int] = None,
    ingredient_group_id: Optional[int] = None,
    is_overdue: Optional[bool] = None,
    is_closed: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    query = db.query(models.RdTask).options(
        joinedload(models.RdTask.ingredient_group),
        joinedload(models.RdTask.recipe),
        joinedload(models.RdTask.responsible_person),
        joinedload(models.RdTask.task_batches).joinedload(models.RdTaskBatch.batch),
    )

    if responsible_id is not None:
        query = query.filter(models.RdTask.responsible_id == responsible_id)
    if stage is not None:
        query = query.filter(models.RdTask.stage == stage)
    if priority is not None:
        query = query.filter(models.RdTask.priority == priority)
    if recipe_id is not None:
        query = query.filter(models.RdTask.recipe_id == recipe_id)
    if ingredient_group_id is not None:
        query = query.filter(models.RdTask.ingredient_group_id == ingredient_group_id)

    if is_closed is not None:
        if is_closed:
            query = query.filter(models.RdTask.stage.in_([TaskStage.FINALIZED, TaskStage.CLOSED]))
        else:
            query = query.filter(models.RdTask.stage.notin_([TaskStage.FINALIZED, TaskStage.CLOSED]))

    if is_overdue is not None and is_overdue:
        query = query.filter(
            models.RdTask.target_date.isnot(None),
            models.RdTask.target_date < datetime.utcnow(),
            models.RdTask.stage.notin_([TaskStage.FINALIZED, TaskStage.CLOSED]),
        )

    tasks = query.order_by(models.RdTask.created_at.desc()).offset(skip).limit(limit).all()
    return [_enrich_task(t, db) for t in tasks]


@router.get("/{task_id}", response_model=schemas.RdTaskDetail)
def get_rd_task_detail(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    task = db.query(models.RdTask).options(
        joinedload(models.RdTask.ingredient_group),
        joinedload(models.RdTask.recipe),
        joinedload(models.RdTask.responsible_person),
        joinedload(models.RdTask.task_batches).joinedload(models.RdTaskBatch.batch),
    ).filter(models.RdTask.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail="研发任务不存在")

    base = _enrich_task(task, db)

    batch_status_transitions = []
    current_round_review_summary = None
    recent_adjustments = []
    anomaly_alerts = []

    linked_batch_ids = [tb.batch_id for tb in task.task_batches]

    if linked_batch_ids:
        batches = db.query(models.Batch).filter(
            models.Batch.id.in_(linked_batch_ids)
        ).all()

        for batch in batches:
            batch_status_transitions.append({
                "batch_id": batch.id,
                "batch_no": batch.batch_no,
                "status": batch.status.value,
                "round_no": batch.round_no,
                "updated_at": batch.updated_at.isoformat() if batch.updated_at else None,
            })

        active_batches = [b for b in batches if b.status == BatchStatus.REVIEWING]
        if active_batches:
            total_reviews = 0
            total_score = 0.0
            valid_reviews = 0
            defect_counts = {}
            for ab in active_batches:
                reviews = db.query(models.Review).filter(
                    models.Review.batch_id == ab.id,
                    models.Review.round_no == ab.round_no,
                    models.Review.is_valid == True,
                ).all()
                for r in reviews:
                    total_reviews += 1
                    score = (r.sweetness + r.consistency + r.melt_speed) / 3
                    total_score += score
                    valid_reviews += 1
                    if r.defect_reason:
                        defect_counts[r.defect_reason] = defect_counts.get(r.defect_reason, 0) + 1

            current_round_review_summary = {
                "total_reviews": total_reviews,
                "avg_score": round(total_score / valid_reviews, 2) if valid_reviews > 0 else None,
                "defect_distribution": defect_counts,
                "active_batch_count": len(active_batches),
            }

        all_adj = db.query(models.AdjustmentRecord).filter(
            models.AdjustmentRecord.batch_id.in_(linked_batch_ids)
        ).order_by(models.AdjustmentRecord.adjusted_at.desc()).limit(10).all()

        recent_adjustments = [
            schemas.AdjustmentResponse(
                id=a.id,
                batch_id=a.batch_id,
                round_no=a.round_no,
                adjustment_details=a.adjustment_details,
                adjuster_id=a.adjuster_id,
                next_round_scheduled=a.next_round_scheduled,
                adjusted_at=a.adjusted_at,
            )
            for a in all_adj
        ]

        for batch in batches:
            if batch.status == BatchStatus.REVIEWING:
                reviews = db.query(models.Review).filter(
                    models.Review.batch_id == batch.id,
                    models.Review.round_no == batch.round_no,
                    models.Review.is_valid == True,
                ).all()
                if len(reviews) < 3:
                    anomaly_alerts.append({
                        "type": "评审人数不足",
                        "severity": "warning",
                        "description": f"批次 {batch.batch_no} 当前轮次有效评审仅 {len(reviews)} 人",
                    })
                if len(reviews) >= 3:
                    import statistics
                    scores = [(r.sweetness + r.consistency + r.melt_speed) / 3 for r in reviews]
                    std = statistics.stdev(scores) if len(scores) > 1 else 0.0
                    if std > 1.5:
                        anomaly_alerts.append({
                            "type": "评分离散过大",
                            "severity": "warning",
                            "description": f"批次 {batch.batch_no} 评分离散度 {std:.2f}，超过阈值1.5",
                        })

            if batch.status == BatchStatus.NEED_ADJUST:
                last_adj = db.query(models.AdjustmentRecord).filter(
                    models.AdjustmentRecord.batch_id == batch.id
                ).order_by(models.AdjustmentRecord.adjusted_at.desc()).first()
                if last_adj and not last_adj.next_round_scheduled:
                    anomaly_alerts.append({
                        "type": "调整后未开启新轮次",
                        "severity": "info",
                        "description": f"批次 {batch.batch_no} 已提交调整但未安排新一轮评审",
                    })

    if base.is_overdue:
        anomaly_alerts.append({
            "type": "任务逾期",
            "severity": "critical",
            "description": f"任务「{task.title}」已超过目标完成时间",
        })

    return schemas.RdTaskDetail(
        **base.model_dump(),
        batch_status_transitions=batch_status_transitions,
        current_round_review_summary=current_round_review_summary,
        recent_adjustments=recent_adjustments,
        anomaly_alerts=anomaly_alerts,
    )


@router.put("/{task_id}", response_model=schemas.RdTaskResponse)
def update_rd_task(
    task_id: int,
    task_update: schemas.RdTaskUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    task = db.query(models.RdTask).filter(models.RdTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="研发任务不存在")

    update_data = task_update.model_dump(exclude_unset=True)

    if "ingredient_group_id" in update_data and update_data["ingredient_group_id"]:
        ig = db.query(models.IngredientGroup).filter(
            models.IngredientGroup.id == update_data["ingredient_group_id"]
        ).first()
        if not ig:
            raise HTTPException(status_code=400, detail="原料组不存在")

    if "recipe_id" in update_data and update_data["recipe_id"]:
        recipe = db.query(models.Recipe).filter(
            models.Recipe.id == update_data["recipe_id"]
        ).first()
        if not recipe:
            raise HTTPException(status_code=400, detail="配方不存在")

    if "responsible_id" in update_data and update_data["responsible_id"]:
        user = db.query(models.User).filter(
            models.User.id == update_data["responsible_id"]
        ).first()
        if not user:
            raise HTTPException(status_code=400, detail="责任人不存在")

    for key, value in update_data.items():
        setattr(task, key, value)

    db.commit()
    db.refresh(task)

    refreshed = db.query(models.RdTask).options(
        joinedload(models.RdTask.ingredient_group),
        joinedload(models.RdTask.recipe),
        joinedload(models.RdTask.responsible_person),
        joinedload(models.RdTask.task_batches).joinedload(models.RdTaskBatch.batch),
    ).filter(models.RdTask.id == task_id).first()

    return _enrich_task(refreshed, db)


@router.delete("/{task_id}")
def delete_rd_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    task = db.query(models.RdTask).filter(models.RdTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="研发任务不存在")

    db.delete(task)
    db.commit()
    return {"message": "删除成功"}


@router.post("/{task_id}/batches/{batch_id}", response_model=schemas.RdTaskResponse)
def link_batch_to_task(
    task_id: int,
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    task = db.query(models.RdTask).filter(models.RdTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="研发任务不存在")

    batch = db.query(models.Batch).filter(models.Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")

    existing = db.query(models.RdTaskBatch).filter(
        models.RdTaskBatch.task_id == task_id,
        models.RdTaskBatch.batch_id == batch_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该批次已关联到此任务")

    tb = models.RdTaskBatch(task_id=task_id, batch_id=batch_id)
    db.add(tb)
    db.commit()

    refreshed = db.query(models.RdTask).options(
        joinedload(models.RdTask.ingredient_group),
        joinedload(models.RdTask.recipe),
        joinedload(models.RdTask.responsible_person),
        joinedload(models.RdTask.task_batches).joinedload(models.RdTaskBatch.batch),
    ).filter(models.RdTask.id == task_id).first()

    return _enrich_task(refreshed, db)


@router.delete("/{task_id}/batches/{batch_id}", response_model=schemas.RdTaskResponse)
def unlink_batch_from_task(
    task_id: int,
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    tb = db.query(models.RdTaskBatch).filter(
        models.RdTaskBatch.task_id == task_id,
        models.RdTaskBatch.batch_id == batch_id,
    ).first()
    if not tb:
        raise HTTPException(status_code=404, detail="关联关系不存在")

    db.delete(tb)
    db.commit()

    refreshed = db.query(models.RdTask).options(
        joinedload(models.RdTask.ingredient_group),
        joinedload(models.RdTask.recipe),
        joinedload(models.RdTask.responsible_person),
        joinedload(models.RdTask.task_batches).joinedload(models.RdTaskBatch.batch),
    ).filter(models.RdTask.id == task_id).first()

    return _enrich_task(refreshed, db)
