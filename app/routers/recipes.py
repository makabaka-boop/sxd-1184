from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas, auth
from ..database import get_db

router = APIRouter(prefix="/recipes", tags=["配方版本"])


@router.post("/", response_model=schemas.RecipeResponse)
def create_recipe(
    recipe: schemas.RecipeCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    group = db.query(models.IngredientGroup).filter(
        models.IngredientGroup.id == recipe.ingredient_group_id
    ).first()
    if not group:
        raise HTTPException(status_code=400, detail="原料组不存在")

    db_recipe = models.Recipe(**recipe.model_dump())
    db.add(db_recipe)
    db.commit()
    db.refresh(db_recipe)
    return db_recipe


@router.get("/", response_model=List[schemas.RecipeResponse])
def list_recipes(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    version: Optional[str] = None,
    ingredient_group_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    query = db.query(models.Recipe)
    if name:
        query = query.filter(models.Recipe.name.contains(name))
    if version:
        query = query.filter(models.Recipe.version == version)
    if ingredient_group_id:
        query = query.filter(models.Recipe.ingredient_group_id == ingredient_group_id)

    recipes = query.offset(skip).limit(limit).all()
    return recipes


@router.get("/{recipe_id}", response_model=schemas.RecipeResponse)
def get_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    recipe = db.query(models.Recipe).filter(
        models.Recipe.id == recipe_id
    ).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="配方不存在")
    return recipe


@router.put("/{recipe_id}", response_model=schemas.RecipeResponse)
def update_recipe(
    recipe_id: int,
    recipe_update: schemas.RecipeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    recipe = db.query(models.Recipe).filter(
        models.Recipe.id == recipe_id
    ).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="配方不存在")

    update_data = recipe_update.model_dump(exclude_unset=True)
    if "ingredient_group_id" in update_data:
        group = db.query(models.IngredientGroup).filter(
            models.IngredientGroup.id == update_data["ingredient_group_id"]
        ).first()
        if not group:
            raise HTTPException(status_code=400, detail="原料组不存在")

    for key, value in update_data.items():
        setattr(recipe, key, value)

    db.commit()
    db.refresh(recipe)
    return recipe


@router.delete("/{recipe_id}")
def delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user)
):
    recipe = db.query(models.Recipe).filter(
        models.Recipe.id == recipe_id
    ).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="配方不存在")

    db.delete(recipe)
    db.commit()
    return {"message": "删除成功"}
