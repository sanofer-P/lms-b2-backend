# curriculum_routes.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

# Adjust these imports based on repository layout
from ...db import models
from app.access_control.schemas.curriculum_schemas import (
    CurriculumOut, TermOut, SectionOut, 
    TimeTableOut, ScheduledClassOut, ScheduledClassUpdate
)
from app.api.v1.ems_module.comman_functions.comman_function import (
    list_batch_sections,
    list_course_types,
    list_courses,
)

from ...core.database import get_db

router = APIRouter(tags=["Curriculum & Scheduling"])

# --- 1. List Curriculum API ---
@router.get("/timetable/curriculums", response_model=List[CurriculumOut])
def get_curriculums(db: Session = Depends(get_db)):
    curriculums = db.query(models.IEMSCurriculum).all()
    return curriculums

# --- 2. List Terms Based on Curriculum API ---
@router.get("/timetable/curriculums/{crclm_id}/terms", response_model=List[TermOut])
def get_terms_by_curriculum(crclm_id: int, db: Session = Depends(get_db)):
    terms = db.query(models.IEMSCrclmTerm).filter(
        models.IEMSCrclmTerm.crclm_id == crclm_id
    ).all()
    # Return an empty list when no terms found to match the declared List response_model
    if not terms:
        return []
    return terms

# List Section Based on Curriculum & Term
@router.get("/timetable/curriculums/{crclm_id}/terms/{term_name}/sections", response_model=List[SectionOut])
def get_sections(crclm_id: int, term_name: str, db: Session = Depends(get_db)):
    sections = db.query(models.IEMSemTimeTable.section).filter(
        models.IEMSemTimeTable.term == term_name
    ).distinct().all()
    return [{"section": sec[0]} for sec in sections if sec[0]]


# ============= NEW META ENDPOINTS FOR TIMETABLE DROPDOWNS =============

# 1. Get curriculums for timetable dropdown (reuses existing data)
@router.get("/timetable/meta/curriculums")
def get_timetable_curriculums(db: Session = Depends(get_db)):
    """
    Get all curriculums for timetable dropdown.
    Returns empty array if no data exists.
    """
    try:
        curriculums = db.query(
            models.IEMSCurriculum.crclm_id,
            models.IEMSCurriculum.start_year,
            models.IEMSCurriculum.pgm_id,
            models.IEMSCurriculum.dept_id
        ).all()
        
        # Format the response
        result = []
        for c in curriculums:
            # Try to get program and department names if available
            pgm_name = db.query(models.IEMSProgram.pgm_name).filter(
                models.IEMSProgram.pgm_id == c.pgm_id
            ).first() if hasattr(models, 'IEMSProgram') else None
            
            dept_name = db.query(models.IEMSDepartment.dept_name).filter(
                models.IEMSDepartment.dept_id == c.dept_id
            ).first() if hasattr(models, 'IEMSDepartment') else None
            
            name_parts = []
            if pgm_name:
                name_parts.append(pgm_name[0])
            if c.start_year:
                name_parts.append(str(c.start_year))
            if dept_name:
                name_parts.append(f"({dept_name[0]})")
            
            result.append({
                "id": c.crclm_id,
                "name": " ".join(name_parts) or f"Curriculum {c.crclm_id}",
                "code": f"C{c.crclm_id}",
                "description": f"Start Year: {c.start_year}" if c.start_year else None
            })
        
        return result
    except Exception as e:
        print(f"Error fetching timetable curriculums: {e}")
        return []

# 2. Get terms for timetable dropdown
@router.get("/timetable/meta/terms")
def get_timetable_terms(
    crclm_id: Optional[int] = Query(default=None, description="Filter by curriculum ID"),
    db: Session = Depends(get_db)
):
    """
    Get all terms for timetable dropdown.
    Returns empty array if no data exists.
    """
    try:
        query = db.query(
            models.IEMSCrclmTerm.crclm_term_id,
            models.IEMSCrclmTerm.term_name,
            models.IEMSCrclmTerm.crclm_id,
            models.IEMSCrclmTerm.term_min_credits,
            models.IEMSCrclmTerm.term_max_credits
        )
        
        if crclm_id is not None:
            query = query.filter(models.IEMSCrclmTerm.crclm_id == crclm_id)
        
        terms = query.order_by(models.IEMSCrclmTerm.term_name).all()
        
        result = []
        for t in terms:
            result.append({
                "id": t.crclm_term_id,
                "name": f"Semester {t.term_name}" if t.term_name else f"Term {t.crclm_term_id}",
                "semester": str(t.term_name) if t.term_name else None,
                "code": f"T{t.crclm_term_id}",
                "curriculum_id": t.crclm_id
            })
        
        return result
    except Exception as e:
        print(f"Error fetching timetable terms: {e}")
        return []

# 3. Get sections for timetable dropdown
@router.get("/timetable/meta/sections")
def get_timetable_sections(
    crclm_id: Optional[int] = Query(default=None, description="Filter by curriculum ID"),
    term_id: Optional[int] = Query(default=None, description="Filter by term ID"),
    db: Session = Depends(get_db)
):
    """
    Get all sections for timetable dropdown.
    Returns empty array if no data exists.
    """
    try:
        # Query sections from IEMSemTimeTable or IEMSection
        query = db.query(
            models.IEMSemTimeTable.section,
            models.IEMSemTimeTable.id
        ).distinct()
        
        if crclm_id is not None:
            query = query.filter(models.IEMSemTimeTable.crclm_id == crclm_id)
        
        if term_id is not None:
            # Try to get term name from term_id
            term = db.query(models.IEMSCrclmTerm.term_name).filter(
                models.IEMSCrclmTerm.crclm_term_id == term_id
            ).first()
            if term:
                query = query.filter(models.IEMSemTimeTable.term == term[0])
        
        sections = query.all()
        
        result = []
        for s in sections:
            result.append({
                "id": s.id or len(result) + 1,
                "name": s.section,
                "code": s.section,
                "display_name": f"Section {s.section}"
            })
        
        # If no sections found, return default sections
        if not result:
            return [
                {"id": 1, "name": "A", "code": "A", "display_name": "Section A"},
                {"id": 2, "name": "B", "code": "B", "display_name": "Section B"},
                {"id": 3, "name": "C", "code": "C", "display_name": "Section C"},
            ]
        
        return result
    except Exception as e:
        print(f"Error fetching timetable sections: {e}")
        # Return default sections on error
        return [
            {"id": 1, "name": "A", "code": "A", "display_name": "Section A"},
            {"id": 2, "name": "B", "code": "B", "display_name": "Section B"},
            {"id": 3, "name": "C", "code": "C", "display_name": "Section C"},
        ]


router.add_api_route("/comman_function/course-types", list_course_types, methods=["GET"])
router.add_api_route("/comman_function/courses", list_courses, methods=["POST"])
router.add_api_route("/comman_function/batch-sections", list_batch_sections, methods=["POST"])
