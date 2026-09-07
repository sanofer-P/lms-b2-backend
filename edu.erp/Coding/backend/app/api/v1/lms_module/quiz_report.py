"""Read-only quiz report for the migrated IEMS/Cudos schema."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.utils.auth_helper import get_current_user
from app.utils.http_return_helper import returnSuccess

router = APIRouter(tags=["Student Quiz Report"])


def context(
    academic_batch_id: int = Query(..., gt=0),
    semester_id: int = Query(..., gt=0),
    crs_id: int = Query(..., gt=0),
    section_id: int = Query(..., gt=0),
):
    return dict(academic_batch_id=academic_batch_id, semester_id=semester_id,
                crs_id=crs_id, section_id=section_id)


def quiz_options(db, params, user):
    sql = """
        SELECT DISTINCT q.quiz_id, q.quiz_title
        FROM lms_manage_quiz q
        JOIN lms_quiz_section_mapping qs ON qs.quiz_id = q.quiz_id
        WHERE q.academic_batch_id = :academic_batch_id
          AND q.semester_id = :semester_id AND q.crs_id = :crs_id
          AND qs.section_id = :section_id
    """
    params = dict(params)
    if not (user.get("super_admin") or user.get("technical_admin")):
        sql += """ AND EXISTS (
            SELECT 1 FROM lms_quiz_topic_mapping qt
            JOIN lms_map_instructor_topic lit ON lit.topic_id = qt.topic_id
            WHERE qt.quiz_id = q.quiz_id AND lit.instructor_id = :user_id
              AND lit.academic_batch_id = q.academic_batch_id
              AND lit.semester_id = q.semester_id AND lit.crs_id = q.crs_id
              AND lit.section_id = :section_id
        )"""
        params["user_id"] = user["user_id"]
    return db.execute(text(sql + " ORDER BY q.quiz_id"), params).mappings().all()


@router.get("/quizzes")
def quizzes(params: dict = Depends(context), db: Session = Depends(get_db),
            user: dict = Depends(get_current_user)):
    return returnSuccess(quiz_options(db, params, user))


@router.get("/students")
def students(quiz_id: int = Query(..., gt=0), params: dict = Depends(context),
             db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    if not any(row["quiz_id"] == quiz_id for row in quiz_options(db, params, user)):
        raise HTTPException(404, "Quiz is unavailable for the selected course and section")
    params = {**params, "quiz_id": quiz_id}
    # Lab sections can map to a parent lecture section, as in CodeIgniter.
    parent = db.execute(text("""
        SELECT parent_id FROM cudos_master_type_details
        WHERE mt_details_id = :section_id
    """), params).scalar()
    params["registration_section_id"] = parent or params["section_id"]
    columns = {row[0] for row in db.execute(text("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'cudos_map_courseto_student'
    """))}
    student_batch = "std_academic_batch_id" if "std_academic_batch_id" in columns else "std_crclm_id"
    has_legacy_status = db.execute(text("""
        SELECT COUNT(*) FROM cudos_master_type
        WHERE master_type_name = 'student_registration_status'
    """)).scalar()
    status_filter = """EXISTS (
        SELECT 1 FROM cudos_master_type_details d
        JOIN cudos_master_type t ON t.master_type_id = d.master_type_id
        WHERE d.mt_details_id = cms.status
          AND t.master_type_name = 'student_registration_status'
          AND d.mt_details_name <> 'Unregistered'
    )""" if has_legacy_status else "cms.status = 1"
    rows = db.execute(text(f"""
        SELECT DISTINCT s.student_id, s.usno AS student_usn,
               TRIM(CONCAT_WS(' ', s.first_name, s.last_name)) AS student_name,
               COALESCE(qsm.q_secured_marks, qsm.secured_marks) AS secured_marks
        FROM iems_students s
        JOIN lms_quiz_student_mapping qsm
          ON qsm.ssd_id = s.student_id AND qsm.quiz_id = :quiz_id
        WHERE EXISTS (
            SELECT 1 FROM cudos_map_courseto_student cms
            WHERE cms.student_id = s.student_id
              AND (cms.academic_batch_id = :academic_batch_id
                   OR cms.{student_batch} = :academic_batch_id)
              AND cms.semester_id = :semester_id AND cms.crs_id = :crs_id
              AND cms.section_id = :registration_section_id
              AND {status_filter}
        )
        ORDER BY student_usn, student_name
    """), params).mappings().all()
    return returnSuccess(rows)
