from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from .. import models, schemas, auth
from ..database import get_db
from .. import stats_service

router = APIRouter(prefix="/stats", tags=["统计分析"])


@router.get("/defect-distribution")
def get_defect_distribution(
    recipe_id: Optional[int] = None,
    ingredient_group_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    exclude_terminated: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return stats_service.get_defect_distribution(
        db, recipe_id, ingredient_group_id, start_date, end_date, exclude_terminated
    )


@router.get("/pending-batches")
def get_pending_batches_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return stats_service.get_pending_batches_stats(db)


@router.get("/recipe-stability")
def get_recipe_stability(
    recipe_id: Optional[int] = None,
    exclude_terminated: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return stats_service.get_recipe_stability(db, recipe_id, exclude_terminated)


@router.get("/anomalies")
def detect_anomalies(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return stats_service.detect_all_anomalies(db)


@router.get("/anomalies/score-dispersion")
def detect_score_dispersion(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return stats_service.detect_score_dispersion(db)


@router.get("/anomalies/insufficient-reviewers")
def detect_insufficient_reviewers(
    min_reviewers: int = Query(3, ge=1),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return stats_service.detect_insufficient_reviewers(db, min_reviewers)


@router.get("/anomalies/missing-next-round")
def detect_missing_next_round(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return stats_service.detect_missing_next_round(db)


@router.get("/anomalies/ingredient-group-defects")
def detect_ingredient_group_defects(
    threshold: int = Query(5, ge=1),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return stats_service.detect_ingredient_group_defects(db, threshold)


@router.get("/tasks/overview", response_model=schemas.TaskStatsOverview)
def get_task_stats_overview(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return stats_service.get_task_stats_overview(db)


@router.get("/tasks/responsible-load", response_model=List[schemas.ResponsibleLoadItem])
def get_responsible_load(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    return stats_service.get_responsible_load(db)
