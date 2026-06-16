from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .models import Base
from .database import engine, SessionLocal
from . import auth
from .models import User
from .routers import auth_router, ingredient_groups, recipes, batches, reviews, stats, rd_tasks

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="冷饮研发管理系统 API",
    description="冷饮研发团队试配批次、口感评审和配方调整记录管理系统",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(ingredient_groups.router)
app.include_router(recipes.router)
app.include_router(batches.router)
app.include_router(reviews.router)
app.include_router(stats.router)
app.include_router(rd_tasks.router)


@app.on_event("startup")
def create_default_user():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            hashed = auth.get_password_hash("admin123")
            admin_user = User(
                username="admin",
                email="admin@example.com",
                full_name="系统管理员",
                role="admin",
                hashed_password=hashed
            )
            db.add(admin_user)

        taster = db.query(User).filter(User.username == "taster1").first()
        if not taster:
            hashed = auth.get_password_hash("taster123")
            taster_user = User(
                username="taster1",
                email="taster1@example.com",
                full_name="品鉴师甲",
                role="taster",
                hashed_password=hashed
            )
            db.add(taster_user)

        taster2 = db.query(User).filter(User.username == "taster2").first()
        if not taster2:
            hashed = auth.get_password_hash("taster123")
            taster_user2 = User(
                username="taster2",
                email="taster2@example.com",
                full_name="品鉴师乙",
                role="taster",
                hashed_password=hashed
            )
            db.add(taster_user2)

        taster3 = db.query(User).filter(User.username == "taster3").first()
        if not taster3:
            hashed = auth.get_password_hash("taster123")
            taster_user3 = User(
                username="taster3",
                email="taster3@example.com",
                full_name="品鉴师丙",
                role="taster",
                hashed_password=hashed
            )
            db.add(taster_user3)

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"创建默认用户出错: {e}")
    finally:
        db.close()


@app.get("/")
def root():
    return {
        "name": "冷饮研发管理系统 API",
        "version": "1.0.0",
        "docs": "/docs",
        "default_admin": "admin / admin123"
    }
