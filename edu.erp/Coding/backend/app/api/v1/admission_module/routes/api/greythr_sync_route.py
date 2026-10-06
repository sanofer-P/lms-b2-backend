from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.v1.admission_module.models.api.greythr_sync_model import User
from app.api.v1.admission_module.services.api.greythr_sync_service import sync_emp_bulk

router = APIRouter()


@router.get("/sync-emp-id")
def sync_emp_id(db: Session = Depends(get_db)):
    return sync_emp_bulk(db)