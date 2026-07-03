from app.database import Base, engine
from app import models  # noqa: F401


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("Database tables are ready.")

