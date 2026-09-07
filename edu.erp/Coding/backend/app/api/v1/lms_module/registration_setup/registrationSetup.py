from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.db.models import (
    CudosMapCoursetoStudent,
    IEMProgram,
    IEMSAcademicBatch,
    IEMSCourses,
    IEMSCourseType,
    IEMSDepartment,
    IEMSemester,
    LMSAcademicBatchSemesterCrsStructure,
)
from app.utils.auth_helper import get_current_user
from app.utils.http_return_helper import returnException, returnSuccess

from .registrationSetup_schema import RegistrationSetupSave

router = APIRouter()


def active_courses_for_term(db: Session, academic_batch_id: int, semester: IEMSemester):
    query = db.query(IEMSCourses).filter(IEMSCourses.academic_batch_id == academic_batch_id)
    if semester.semester is not None:
        query = query.filter(IEMSCourses.semester == semester.semester)
    return query.filter(IEMSCourses.status == 1)


@router.get("/departments")
def get_departments(current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(IEMSDepartment).filter(IEMSDepartment.status.is_(True)).order_by(IEMSDepartment.dept_name).all()
    return returnSuccess([{"dept_id": row.dept_id, "dept_name": row.dept_name} for row in rows])


@router.get("/programs/{department_id}")
def get_programs(department_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(IEMProgram).filter(IEMProgram.dept_id == department_id, IEMProgram.status == 1).order_by(IEMProgram.pgm_title).all()
    return returnSuccess([{"pgm_id": row.pgm_id, "program_name": row.pgm_title} for row in rows])


@router.get("/curriculums/{program_id}")
def get_curriculums(program_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(IEMSAcademicBatch).filter(IEMSAcademicBatch.pgm_id == program_id, IEMSAcademicBatch.status == 1).order_by(IEMSAcademicBatch.academic_batch_desc).all()
    return returnSuccess([{"curriculum_id": row.academic_batch_id, "curriculum_name": row.academic_batch_desc} for row in rows])


@router.get("/terms/{academic_batch_id}")
def get_terms(academic_batch_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(IEMSemester).filter(IEMSemester.academic_batch_id == academic_batch_id, IEMSemester.status == 1).order_by(IEMSemester.semester).all()
    return returnSuccess([{"semester_id": row.semester_id, "term_name": row.term_name or row.semester_desc or row.semester_code} for row in rows])


@router.get("/registration-setup/{semester_id}")
def get_registration_setup(semester_id: int, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    semester = db.query(IEMSemester).filter(IEMSemester.semester_id == semester_id).first()
    if not semester:
        return returnException("Semester not found")

    structures = db.query(LMSAcademicBatchSemesterCrsStructure).filter(
        LMSAcademicBatchSemesterCrsStructure.academic_batch_id == semester.academic_batch_id,
        LMSAcademicBatchSemesterCrsStructure.semester_id == semester_id,
    ).all()

    course_structure = []
    for structure in structures:
        course_ids = [row.crs_id for row in active_courses_for_term(db, semester.academic_batch_id, semester).filter(IEMSCourses.course_type_id == structure.crs_type_id).all()]
        registered = 0
        if course_ids:
            registered = db.query(func.count(CudosMapCoursetoStudent.mcstd_id)).filter(
                CudosMapCoursetoStudent.academic_batch_id == semester.academic_batch_id,
                CudosMapCoursetoStudent.semester_id == semester_id,
                CudosMapCoursetoStudent.crs_id.in_(course_ids),
            ).scalar() or 0
        course_structure.append({
            "crs_type_id": structure.crs_type_id,
            "course_type": structure.course_type.course_type_desc,
            "total_credits": float(structure.crs_type_total or 0),
            "min_credits": float(structure.stud_min_crs_enroll or 0),
            "max_credits": float(structure.stud_max_crs_enroll or 0),
            "students_registered": registered,
        })

    return returnSuccess({
        "semester": {
            "academic_batch_id": semester.academic_batch_id,
            "start_date": semester.enroll_start_date.strftime("%d-%m-%Y") if semester.enroll_start_date else None,
            "start_time": semester.enroll_start_time.strftime("%I:%M %p") if semester.enroll_start_time else None,
            "end_date": semester.enroll_end_date.strftime("%d-%m-%Y") if semester.enroll_end_date else None,
            "end_time": semester.enroll_end_time.strftime("%I:%M %p") if semester.enroll_end_time else None,
            "min_credit": float(semester.sem_min_credits or 0),
            "max_credit": float(semester.total_crs_enroll or semester.sem_max_credits or 0),
            "own_elective": semester.own_crclm_elective or 0,
            "other_elective": semester.other_crclm_elective or 0,
        },
        "course_structure": course_structure,
    })


@router.get("/course-enroll-details/{semester_id}/{course_type}")
def get_course_enrollment_details(
    semester_id: int,
    course_type: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    semester = db.query(IEMSemester).filter(IEMSemester.semester_id == semester_id).first()
    if not semester:
        return returnException("Semester not found")

    course_type_row = db.query(IEMSCourseType).filter(
        IEMSCourseType.course_type_desc == course_type,
        IEMSCourseType.status == 1,
    ).first()
    if not course_type_row:
        return returnException("Course type not found")

    courses = active_courses_for_term(db, semester.academic_batch_id, semester).filter(
        IEMSCourses.course_type_id == course_type_row.course_type_id
    ).order_by(IEMSCourses.crs_code).all()

    result = []
    for course in courses:
        registered_count = db.query(func.count(CudosMapCoursetoStudent.mcstd_id)).filter(
            CudosMapCoursetoStudent.academic_batch_id == semester.academic_batch_id,
            CudosMapCoursetoStudent.semester_id == semester_id,
            CudosMapCoursetoStudent.crs_id == course.crs_id,
        ).scalar() or 0
        result.append({
            "crs_id": course.crs_id,
            "crs_code": course.crs_code,
            "crs_title": course.crs_title,
            "total_credits": float(course.total_credits or 0),
            "registered_count": registered_count,
        })

    return returnSuccess({
        "semester_id": semester_id,
        "course_type": course_type_row.course_type_desc,
        "course_type_id": course_type_row.course_type_id,
        "courses": result,
        "total_courses": len(result),
        "total_registered": sum(course["registered_count"] for course in result),
        "total_credits": sum(course["total_credits"] for course in result),
    })


@router.post("/update-registration-settings")
def update_registration_settings(payload: RegistrationSetupSave, current_user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = current_user.get("user_id")
    try:
        semester = db.query(IEMSemester).filter(
            IEMSemester.semester_id == payload.semester_id,
            IEMSemester.academic_batch_id == payload.academic_batch_id,
        ).first()
        if not semester:
            raise HTTPException(status_code=404, detail="Semester not found for the selected curriculum")

        semester.enroll_start_date = payload.enroll_start_date
        semester.enroll_start_time = payload.enroll_start_time
        semester.enroll_end_date = payload.enroll_end_date
        semester.enroll_end_time = payload.enroll_end_time
        semester.total_crs_enroll = payload.total_crs_enroll
        semester.own_crclm_elective = payload.own_crclm_elective
        semester.other_crclm_elective = payload.other_crclm_elective
        semester.modified_by = user_id
        semester.modify_date = datetime.now()

        for limit in payload.course_limits:
            structure = db.query(LMSAcademicBatchSemesterCrsStructure).filter(
                LMSAcademicBatchSemesterCrsStructure.academic_batch_id == payload.academic_batch_id,
                LMSAcademicBatchSemesterCrsStructure.semester_id == payload.semester_id,
                LMSAcademicBatchSemesterCrsStructure.crs_type_id == limit.crs_type_id,
            ).first()
            if structure:
                structure.crs_type_total = limit.crs_type_total
                structure.stud_min_crs_enroll = limit.stud_min_crs_enroll
                structure.stud_max_crs_enroll = limit.stud_max_crs_enroll
                structure.modified_by = user_id
                structure.modified_date = datetime.now()
            else:
                db.add(LMSAcademicBatchSemesterCrsStructure(
                    academic_batch_id=payload.academic_batch_id,
                    semester_id=payload.semester_id,
                    crs_type_id=limit.crs_type_id,
                    crs_type_total=limit.crs_type_total,
                    stud_min_crs_enroll=limit.stud_min_crs_enroll,
                    stud_max_crs_enroll=limit.stud_max_crs_enroll,
                    created_by=user_id,
                    created_date=datetime.now(),
                ))
        db.commit()
        return returnSuccess({"message": "Registration setup updated successfully"})
    except HTTPException:
        db.rollback()
        raise
    except Exception as error:
        db.rollback()
        return returnException(str(error))
