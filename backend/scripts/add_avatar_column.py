import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text

from app.platform.database.session import SessionLocal


def main():
    db = SessionLocal()
    try:
        print("Executing ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar TEXT...")
        db.execute(text("SET ROLE postgres"))
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar TEXT;"))
        db.commit()
        print("Column avatar added successfully or already exists!")
    except Exception as e:
        print("Error altering table users:", e)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()
