from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean, Enum
)
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()


class BatchStatus(str, enum.Enum):
    PENDING_TRIAL = "待试配"
    PENDING_REVIEW = "待评审"
    REVIEWING = "评审中"
    NEED_ADJUST = "需调整"
    FINALIZED = "已定版"
    TERMINATED = "已终止"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(String(50), default="taster")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    reviews_submitted = relationship("Review", back_populates="reviewer", foreign_keys="Review.reviewer_id")
    responsible_batches = relationship("Batch", back_populates="responsible_person", foreign_keys="Batch.responsible_id")


class IngredientGroup(Base):
    __tablename__ = "ingredient_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    ingredients = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recipes = relationship("Recipe", back_populates="ingredient_group")


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    ingredient_group_id = Column(Integer, ForeignKey("ingredient_groups.id"), nullable=False)
    description = Column(Text)
    formula_details = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    ingredient_group = relationship("IngredientGroup", back_populates="recipes")
    batches = relationship("Batch", back_populates="recipe")

    __mapper_args__ = {"confirm_deleted_rows": False}


class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, index=True)
    batch_no = Column(String(50), unique=True, nullable=False, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False)
    status = Column(Enum(BatchStatus), default=BatchStatus.PENDING_TRIAL, nullable=False)
    round_no = Column(Integer, default=1, nullable=False)
    responsible_id = Column(Integer, ForeignKey("users.id"))
    trial_date = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recipe = relationship("Recipe", back_populates="batches")
    responsible_person = relationship("User", back_populates="responsible_batches", foreign_keys=[responsible_id])
    reviews = relationship("Review", back_populates="batch")
    adjustments = relationship("AdjustmentRecord", back_populates="batch")


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    round_no = Column(Integer, nullable=False)
    sweetness = Column(Float, nullable=False)
    consistency = Column(Float, nullable=False)
    melt_speed = Column(Float, nullable=False)
    taste_description = Column(Text)
    defect_reason = Column(String(200))
    suggested_action = Column(Text)
    is_valid = Column(Boolean, default=True, nullable=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    batch = relationship("Batch", back_populates="reviews")
    reviewer = relationship("User", back_populates="reviews_submitted", foreign_keys=[reviewer_id])


class AdjustmentRecord(Base):
    __tablename__ = "adjustment_records"

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    round_no = Column(Integer, nullable=False)
    adjustment_details = Column(Text, nullable=False)
    adjuster_id = Column(Integer, ForeignKey("users.id"))
    adjusted_at = Column(DateTime, default=datetime.utcnow)
    next_round_scheduled = Column(Boolean, default=False)

    batch = relationship("Batch", back_populates="adjustments")
