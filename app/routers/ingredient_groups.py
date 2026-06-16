from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/ingredient-groups", tags=["原料组"])


@router.post("/", response_model=schemas.IngredientGroupResponse)
def create_ingredient_group(
    group: schemas.IngredientGroupCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    existing = db.query(models.IngredientGroup).filter(
        models.IngredientGroup.name == group.name
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="原料组名称已存在")

    db_group = models.IngredientGroup(**group.model_dump())
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group


@router.get("/", response_model=List[schemas.IngredientGroupResponse])
def list_ingredient_groups(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    groups = db.query(models.IngredientGroup).offset(skip).limit(limit).all()
    return groups


@router.get("/{group_id}", response_model=schemas.IngredientGroupResponse)
def get_ingredient_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    group = db.query(models.IngredientGroup).filter(
        models.IngredientGroup.id == group_id
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="原料组不存在")
    return group


@router.put("/{group_id}", response_model=schemas.IngredientGroupResponse)
def update_ingredient_group(
    group_id: int,
    group_update: schemas.IngredientGroupUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    group = db.query(models.IngredientGroup).filter(
        models.IngredientGroup.id == group_id
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="原料组不存在")

    update_data = group_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(group, key, value)

    db.commit()
    db.refresh(group)
    return group


@router.delete("/{group_id}")
def delete_ingredient_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    group = db.query(models.IngredientGroup).filter(
        models.IngredientGroup.id == group_id
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="原料组不存在")

    db.delete(group)
    db.commit()
    return {"message": "删除成功"}
