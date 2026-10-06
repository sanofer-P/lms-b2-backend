from sqlalchemy import Column, Integer, String
from app.core.database import Base


class User(Base):
    __tablename__ = "iems_users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String(255), index=True, nullable=False)

    # 🔹 Required fields for your sync
    emp_id = Column(Integer, nullable=True)
    Grety_HR_Sync = Column(Integer, default=0)  # 0 = not synced, 1 = synced