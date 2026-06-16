from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from .models import BatchStatus


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class UserBase(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = "taster"


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class IngredientGroupBase(BaseModel):
    name: str
    description: Optional[str] = None
    ingredients: Optional[str] = None


class IngredientGroupCreate(IngredientGroupBase):
    pass


class IngredientGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    ingredients: Optional[str] = None


class IngredientGroupResponse(IngredientGroupBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RecipeBase(BaseModel):
    name: str
    version: str
    ingredient_group_id: int
    description: Optional[str] = None
    formula_details: Optional[str] = None


class RecipeCreate(RecipeBase):
    pass


class RecipeUpdate(BaseModel):
    name: Optional[str] = None
    version: Optional[str] = None
    ingredient_group_id: Optional[int] = None
    description: Optional[str] = None
    formula_details: Optional[str] = None


class RecipeResponse(RecipeBase):
    id: int
    created_at: datetime
    updated_at: datetime
    ingredient_group: Optional[IngredientGroupResponse] = None

    class Config:
        from_attributes = True


class BatchBase(BaseModel):
    batch_no: str
    recipe_id: int
    responsible_id: Optional[int] = None
    trial_date: Optional[datetime] = None
    notes: Optional[str] = None


class BatchCreate(BatchBase):
    pass


class BatchUpdate(BaseModel):
    status: Optional[BatchStatus] = None
    responsible_id: Optional[int] = None
    trial_date: Optional[datetime] = None
    notes: Optional[str] = None
    round_no: Optional[int] = None


class BatchResponse(BatchBase):
    id: int
    status: BatchStatus
    round_no: int
    created_at: datetime
    updated_at: datetime
    recipe: Optional[RecipeResponse] = None
    responsible_person: Optional[UserResponse] = None

    class Config:
        from_attributes = True


class ReviewBase(BaseModel):
    sweetness: float = Field(ge=0, le=10)
    consistency: float = Field(ge=0, le=10)
    melt_speed: float = Field(ge=0, le=10)
    taste_description: Optional[str] = None
    defect_reason: Optional[str] = None
    suggested_action: Optional[str] = None
    is_valid: bool = True


class ReviewCreate(ReviewBase):
    batch_id: int


class ReviewResponse(ReviewBase):
    id: int
    batch_id: int
    reviewer_id: int
    round_no: int
    submitted_at: datetime
    reviewer: Optional[UserResponse] = None

    class Config:
        from_attributes = True


class AdjustmentRecordBase(BaseModel):
    batch_id: int
    round_no: int
    adjustment_details: str
    adjuster_id: Optional[int] = None
    next_round_scheduled: bool = False


class AdjustmentCreate(BaseModel):
    adjustment_details: str
    next_round_scheduled: bool = False


class AdjustmentResponse(AdjustmentRecordBase):
    id: int
    adjusted_at: datetime

    class Config:
        from_attributes = True


class DefectDistributionItem(BaseModel):
    defect_reason: str
    count: int


class PendingBatchesStats(BaseModel):
    total: int
    by_status: dict[str, int]


class RecipeStabilityItem(BaseModel):
    recipe_id: int
    recipe_name: str
    version: str
    avg_score: float
    score_std: float
    review_count: int
    stability_level: str


class AnomalyDetectionResult(BaseModel):
    type: str
    severity: str
    description: str
    related_ids: Optional[List[int]] = None
