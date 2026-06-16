from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from . import models
from .models import BatchStatus, TaskStage, TaskPriority, RiskStatus
import statistics


def calc_avg_score(review: models.Review) -> float:
    return (review.sweetness + review.consistency + review.melt_speed) / 3


def get_defect_distribution(
    db: Session,
    recipe_id: Optional[int] = None,
    ingredient_group_id: Optional[int] = None,
    start_date=None,
    end_date=None,
    exclude_terminated: bool = True
) -> List[dict]:
    query = db.query(
        models.Review.defect_reason,
        func.count(models.Review.id).label('count')
    ).join(models.Batch).filter(
        models.Review.is_valid == True,
        models.Review.defect_reason.isnot(None),
        models.Review.defect_reason != ''
    )

    if exclude_terminated:
        query = query.filter(models.Batch.status != BatchStatus.TERMINATED)
    if recipe_id:
        query = query.filter(models.Batch.recipe_id == recipe_id)
    if ingredient_group_id:
        query = query.join(models.Recipe).filter(
            models.Recipe.ingredient_group_id == ingredient_group_id
        )
    if start_date:
        query = query.filter(models.Review.submitted_at >= start_date)
    if end_date:
        query = query.filter(models.Review.submitted_at <= end_date)

    results = query.group_by(models.Review.defect_reason).order_by(
        func.count(models.Review.id).desc()
    ).all()

    return [{"defect_reason": r[0], "count": r[1]} for r in results]


def get_pending_batches_stats(db: Session) -> dict:
    pending_statuses = [
        BatchStatus.PENDING_TRIAL,
        BatchStatus.PENDING_REVIEW,
        BatchStatus.REVIEWING,
        BatchStatus.NEED_ADJUST
    ]
    total_pending = db.query(models.Batch).filter(
        models.Batch.status.in_(pending_statuses)
    ).count()

    by_status = {}
    statuses = db.query(
        models.Batch.status,
        func.count(models.Batch.id)
    ).filter(
        models.Batch.status.in_(pending_statuses)
    ).group_by(models.Batch.status).all()
    for s, cnt in statuses:
        by_status[s.value] = cnt

    return {"total": total_pending, "by_status": by_status}


def get_recipe_stability(db: Session, recipe_id: Optional[int] = None, exclude_terminated: bool = True) -> List[dict]:
    query = db.query(models.Recipe)
    if recipe_id:
        query = query.filter(models.Recipe.id == recipe_id)

    recipes = query.all()
    result = []

    for recipe in recipes:
        review_query = db.query(models.Review).join(models.Batch).filter(
            models.Batch.recipe_id == recipe.id,
            models.Review.is_valid == True
        )
        if exclude_terminated:
            review_query = review_query.filter(models.Batch.status != BatchStatus.TERMINATED)
        reviews = review_query.all()

        if not reviews:
            continue

        scores = [calc_avg_score(r) for r in reviews]
        avg_score = sum(scores) / len(scores)
        score_std = statistics.stdev(scores) if len(scores) > 1 else 0.0

        if score_std < 0.5:
            stability = "高"
        elif score_std < 1.0:
            stability = "中"
        else:
            stability = "低"

        result.append({
            "recipe_id": recipe.id,
            "recipe_name": recipe.name,
            "version": recipe.version,
            "avg_score": round(avg_score, 2),
            "score_std": round(score_std, 2),
            "review_count": len(scores),
            "stability_level": stability
        })

    result.sort(key=lambda x: x["score_std"])
    return result


def detect_score_dispersion(db: Session) -> List[dict]:
    anomalies = []
    reviewing_batches = db.query(models.Batch).filter(
        models.Batch.status == BatchStatus.REVIEWING
    ).all()

    for batch in reviewing_batches:
        reviews = db.query(models.Review).filter(
            models.Review.batch_id == batch.id,
            models.Review.round_no == batch.round_no,
            models.Review.is_valid == True
        ).all()

        if len(reviews) < 3:
            continue

        scores = [calc_avg_score(r) for r in reviews]
        std = statistics.stdev(scores) if len(scores) > 1 else 0.0

        if std > 1.5:
            anomalies.append({
                "type": "评分离散过大",
                "severity": "warning",
                "description": f"批次 {batch.batch_no} 第{batch.round_no}轮评审评分离散度为 {std:.2f}，超过阈值1.5",
                "related_ids": [batch.id]
            })

    return anomalies


def detect_insufficient_reviewers(db: Session, min_reviewers: int = 3) -> List[dict]:
    anomalies = []
    reviewing_batches = db.query(models.Batch).filter(
        models.Batch.status == BatchStatus.REVIEWING
    ).all()

    for batch in reviewing_batches:
        valid_review_count = db.query(models.Review).filter(
            models.Review.batch_id == batch.id,
            models.Review.round_no == batch.round_no,
            models.Review.is_valid == True
        ).count()

        if valid_review_count < min_reviewers:
            anomalies.append({
                "type": "评审人数不足",
                "severity": "info",
                "description": f"批次 {batch.batch_no} 第{batch.round_no}轮有效评审仅 {valid_review_count} 人，不足 {min_reviewers} 人",
                "related_ids": [batch.id]
            })

    return anomalies


def detect_missing_next_round(db: Session) -> List[dict]:
    anomalies = []
    adjust_batches = db.query(models.Batch).filter(
        models.Batch.status == BatchStatus.NEED_ADJUST
    ).all()

    for batch in adjust_batches:
        last_adjust = db.query(models.AdjustmentRecord).filter(
            models.AdjustmentRecord.batch_id == batch.id
        ).order_by(models.AdjustmentRecord.adjusted_at.desc()).first()

        if last_adjust and not last_adjust.next_round_scheduled:
            anomalies.append({
                "type": "调整后未开启新轮次",
                "severity": "warning",
                "description": f"批次 {batch.batch_no} 已提交调整但未安排新一轮评审",
                "related_ids": [batch.id]
            })

    return anomalies


def detect_ingredient_group_defects(db: Session, threshold: int = 5, exclude_terminated: bool = True) -> List[dict]:
    anomalies = []

    query = db.query(
        models.IngredientGroup.id,
        models.IngredientGroup.name,
        func.count(models.Review.id).label('defect_count')
    ).join(
        models.Recipe, models.Recipe.ingredient_group_id == models.IngredientGroup.id
    ).join(
        models.Batch, models.Batch.recipe_id == models.Recipe.id
    ).join(
        models.Review, and_(
            models.Review.batch_id == models.Batch.id,
            models.Review.is_valid == True,
            models.Review.defect_reason.isnot(None),
            models.Review.defect_reason != ''
        )
    )

    if exclude_terminated:
        query = query.filter(models.Batch.status != BatchStatus.TERMINATED)

    results = query.group_by(
        models.IngredientGroup.id
    ).having(
        func.count(models.Review.id) >= threshold
    ).all()

    for group_id, group_name, defect_count in results:
        anomalies.append({
            "type": "原料组缺陷偏多",
            "severity": "warning",
            "description": f"原料组 {group_name} 关联缺陷记录 {defect_count} 条，超过阈值 {threshold}",
            "related_ids": [group_id]
        })

    return anomalies


def detect_all_anomalies(db: Session) -> List[dict]:
    anomalies = []
    anomalies.extend(detect_score_dispersion(db))
    anomalies.extend(detect_insufficient_reviewers(db))
    anomalies.extend(detect_missing_next_round(db))
    anomalies.extend(detect_ingredient_group_defects(db))
    return anomalies


def get_task_stats_overview(db: Session) -> dict:
    from datetime import datetime

    all_tasks = db.query(models.RdTask).all()
    total = len(all_tasks)

    closed_stages = [TaskStage.FINALIZED, TaskStage.CLOSED]
    pending_tasks = [t for t in all_tasks if t.stage not in closed_stages]
    pending = len(pending_tasks)

    overdue = len([
        t for t in pending_tasks
        if t.target_date and t.target_date < datetime.utcnow()
    ])

    by_stage = {}
    for t in all_tasks:
        key = t.stage.value
        by_stage[key] = by_stage.get(key, 0) + 1

    by_priority = {}
    for t in all_tasks:
        key = t.priority.value
        by_priority[key] = by_priority.get(key, 0) + 1

    return {
        "total": total,
        "pending": pending,
        "overdue": overdue,
        "by_stage": by_stage,
        "by_priority": by_priority,
    }


def get_responsible_load(db: Session) -> List[dict]:
    from datetime import datetime

    closed_stages = [TaskStage.FINALIZED, TaskStage.CLOSED]

    all_tasks = db.query(models.RdTask).all()

    load_map = {}
    for t in all_tasks:
        rid = t.responsible_id
        if rid is None:
            continue
        if rid not in load_map:
            user = db.query(models.User).filter(models.User.id == rid).first()
            load_map[rid] = {
                "responsible_id": rid,
                "responsible_name": user.full_name if user else None,
                "total": 0,
                "pending": 0,
                "overdue": 0,
            }
        load_map[rid]["total"] += 1
        if t.stage not in closed_stages:
            load_map[rid]["pending"] += 1
            if t.target_date and t.target_date < datetime.utcnow():
                load_map[rid]["overdue"] += 1

    return list(load_map.values())


def _get_valid_review_count(db: Session, batch: models.Batch) -> int:
    return db.query(models.Review).filter(
        models.Review.batch_id == batch.id,
        models.Review.round_no == batch.round_no,
        models.Review.is_valid == True
    ).count()


def _get_review_std(db: Session, batch: models.Batch) -> float:
    reviews = db.query(models.Review).filter(
        models.Review.batch_id == batch.id,
        models.Review.round_no == batch.round_no,
        models.Review.is_valid == True
    ).all()
    if len(reviews) < 2:
        return 0.0
    scores = [calc_avg_score(r) for r in reviews]
    return statistics.stdev(scores)


def _get_days_in_status(db: Session, batch: models.Batch) -> int:
    last_log = db.query(models.BatchStatusLog).filter(
        models.BatchStatusLog.batch_id == batch.id,
        models.BatchStatusLog.to_status == batch.status
    ).order_by(models.BatchStatusLog.created_at.desc()).first()
    if not last_log:
        return 0
    delta = datetime.utcnow() - last_log.created_at
    return delta.days


def _has_scheduled_next_round(db: Session, batch: models.Batch) -> bool:
    last_adj = db.query(models.AdjustmentRecord).filter(
        models.AdjustmentRecord.batch_id == batch.id
    ).order_by(models.AdjustmentRecord.adjusted_at.desc()).first()
    return last_adj is not None and last_adj.next_round_scheduled


def calculate_task_risk(db: Session, task: models.RdTask) -> Tuple[RiskStatus, str]:
    if task.stage in [TaskStage.FINALIZED, TaskStage.CLOSED]:
        return RiskStatus.NORMAL, "任务已完成/关闭"

    now = datetime.utcnow()
    lagging_reasons = []
    attention_reasons = []

    if task.target_date and task.target_date < now:
        lagging_reasons.append(f"任务已超过目标完成日期 {(now - task.target_date).days} 天")

    linked_batch_ids = [tb.batch_id for tb in task.task_batches]
    if not linked_batch_ids:
        if task.target_date and (task.target_date - now).days <= 7:
            attention_reasons.append("任务临近目标日期但尚未关联批次")
        else:
            attention_reasons.append("任务尚未关联批次")
    else:
        batches = db.query(models.Batch).filter(
            models.Batch.id.in_(linked_batch_ids)
        ).all()

        for batch in batches:
            if batch.status in [BatchStatus.FINALIZED, BatchStatus.TERMINATED]:
                continue

            days_in_status = _get_days_in_status(db, batch)

            if batch.status == BatchStatus.NEED_ADJUST:
                has_scheduled = _has_scheduled_next_round(db, batch)
                if not has_scheduled:
                    if days_in_status > 3:
                        lagging_reasons.append(
                            f"批次 {batch.batch_no} 调整后超过{days_in_status}天未安排下一轮"
                        )
                    else:
                        attention_reasons.append(
                            f"批次 {batch.batch_no} 已提交调整尚未安排下一轮"
                        )

            if batch.status == BatchStatus.REVIEWING:
                valid_count = _get_valid_review_count(db, batch)
                if valid_count < 3:
                    if days_in_status > 5:
                        lagging_reasons.append(
                            f"批次 {batch.batch_no} 评审中超过{days_in_status}天，有效评审仅{valid_count}人"
                        )
                    else:
                        attention_reasons.append(
                            f"批次 {batch.batch_no} 当前轮有效评审仅{valid_count}人，不足3人"
                        )

                if valid_count >= 3:
                    std = _get_review_std(db, batch)
                    if std > 1.5:
                        attention_reasons.append(
                            f"批次 {batch.batch_no} 评分离散度 {std:.2f}，超过阈值1.5"
                        )

            if batch.status == BatchStatus.PENDING_REVIEW and days_in_status > 5:
                attention_reasons.append(
                    f"批次 {batch.batch_no} 待评审超过{days_in_status}天未启动"
                )

    if task.target_date and task.target_date >= now:
        days_to_target = (task.target_date - now).days
        if days_to_target <= 7:
            attention_reasons.append(f"距离目标完成日期仅剩 {days_to_target} 天")

    if lagging_reasons:
        return RiskStatus.LAGGING, "；".join(lagging_reasons)
    elif attention_reasons:
        return RiskStatus.ATTENTION, "；".join(attention_reasons)
    else:
        return RiskStatus.NORMAL, "进度正常"


def update_task_risk(db: Session, task_id: int) -> None:
    task = db.query(models.RdTask).filter(models.RdTask.id == task_id).first()
    if not task:
        return
    risk_status, risk_reason = calculate_task_risk(db, task)
    task.risk_status = risk_status
    task.risk_reason = risk_reason
    task.risk_calculated_at = datetime.utcnow()


def recalc_task_risk_for_batch(db: Session, batch_id: int) -> None:
    task_links = db.query(models.RdTaskBatch).filter(
        models.RdTaskBatch.batch_id == batch_id
    ).all()
    for tl in task_links:
        update_task_risk(db, tl.task_id)


def recalc_all_tasks_risk(db: Session) -> None:
    tasks = db.query(models.RdTask).all()
    for task in tasks:
        update_task_risk(db, task.id)


def get_risk_stats_by_responsible(db: Session) -> List[dict]:
    all_tasks = db.query(models.RdTask).all()
    result_map = {}

    for task in all_tasks:
        rid = task.responsible_id
        if rid is None:
            key = "未分配"
            name = "未分配"
        else:
            key = str(rid)
            user = db.query(models.User).filter(models.User.id == rid).first()
            name = user.full_name if user else f"用户{rid}"

        if key not in result_map:
            result_map[key] = {
                "category": "负责人",
                "category_value": name,
                "normal_count": 0,
                "attention_count": 0,
                "lagging_count": 0,
                "total_count": 0,
            }

        result_map[key]["total_count"] += 1
        if task.risk_status == RiskStatus.NORMAL:
            result_map[key]["normal_count"] += 1
        elif task.risk_status == RiskStatus.ATTENTION:
            result_map[key]["attention_count"] += 1
        elif task.risk_status == RiskStatus.LAGGING:
            result_map[key]["lagging_count"] += 1

    return list(result_map.values())


def get_risk_stats_by_stage(db: Session) -> List[dict]:
    all_tasks = db.query(models.RdTask).all()
    result_map = {}

    for task in all_tasks:
        stage_value = task.stage.value
        if stage_value not in result_map:
            result_map[stage_value] = {
                "category": "任务阶段",
                "category_value": stage_value,
                "normal_count": 0,
                "attention_count": 0,
                "lagging_count": 0,
                "total_count": 0,
            }

        result_map[stage_value]["total_count"] += 1
        if task.risk_status == RiskStatus.NORMAL:
            result_map[stage_value]["normal_count"] += 1
        elif task.risk_status == RiskStatus.ATTENTION:
            result_map[stage_value]["attention_count"] += 1
        elif task.risk_status == RiskStatus.LAGGING:
            result_map[stage_value]["lagging_count"] += 1

    return list(result_map.values())


def get_risk_stats_by_priority(db: Session) -> List[dict]:
    all_tasks = db.query(models.RdTask).all()
    result_map = {}

    for task in all_tasks:
        priority_value = task.priority.value
        if priority_value not in result_map:
            result_map[priority_value] = {
                "category": "优先级",
                "category_value": priority_value,
                "normal_count": 0,
                "attention_count": 0,
                "lagging_count": 0,
                "total_count": 0,
            }

        result_map[priority_value]["total_count"] += 1
        if task.risk_status == RiskStatus.NORMAL:
            result_map[priority_value]["normal_count"] += 1
        elif task.risk_status == RiskStatus.ATTENTION:
            result_map[priority_value]["attention_count"] += 1
        elif task.risk_status == RiskStatus.LAGGING:
            result_map[priority_value]["lagging_count"] += 1

    return list(result_map.values())


def get_risk_stats_overview(db: Session) -> dict:
    return {
        "by_responsible": get_risk_stats_by_responsible(db),
        "by_stage": get_risk_stats_by_stage(db),
        "by_priority": get_risk_stats_by_priority(db),
    }
