from datetime import datetime
from itertools import groupby
from operator import itemgetter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db

from app.utils.auth_helper import get_current_user

from app.utils.http_return_helper import (
    returnSuccess,
    returnException
)

from app.db.models import (
    CudosMapCoursetoStudent,
    IEMSCourses,
    LMSIssuesObservations,
    LMSIssuesObservationsHistory,
    IEMStudents,
    IEMSUsers,
    IEMSAcademicBatch,
    IEMSemester,
    LMSMentorsGroupTerms,
    LMSGroupMentees
)

from .lms_stud_issues_observations_report_schema import *

router = APIRouter()

# ==========================================================
# GET STUDENT DETAILS BY USN
# ==========================================================
@router.get("/get_student_by_usn/{student_usn}")
def get_student_by_usn(
    student_usn: str,
    db: Session = Depends(get_db)
):
    try:
        # Find the student in the database using their USN.
        # Note: Adjust 'IEMStudents' and 'student_usn' to match your actual model and column name.
        student = db.query(IEMStudents).filter(
            IEMStudents.student_usn == student_usn
        ).first()

        if not student:
            # If no student is found, return an error.
            return returnException(f"Student with USN '{student_usn}' not found.", 404)

        # The frontend expects data in a specific format.
        # Create a dictionary that matches the 'IssueObservationStudent' type in your React code.
        result = {
            "student_id": student.student_id,  # Or student.id, student.ssd_id etc.
            "student_name": student.student_name,
            "student_usn": student.student_usn,
            "academic_batch_id": student.academic_batch_id,
            "semester_id": student.semester_id,
            "email": student.email,
            "mobile": student.mobile,
        }

        return returnSuccess(result)

    except Exception as e:
        return returnException(str(e))

# ==========================================================
# GET STUDENT ISSUE & OBSERVATION REPORTS
# ==========================================================
@router.get("/get_student_issue_observations/{student_id}")
def get_student_issue_observations(
    student_id: int,
    db: Session = Depends(get_db)
):

    try:

        reports = db.query(
            LMSIssuesObservations
        ).filter(
            LMSIssuesObservations.ssd_id == student_id,
            LMSIssuesObservations.is_deleted == 0
        ).order_by(
            LMSIssuesObservations.created_date.desc()
        ).all()

        result = []

        for report in reports:

            mentor = db.query(
                IEMSUsers
            ).filter(
                IEMSUsers.id == report.mentor_users_id
            ).first()

            # Report Status
            if report.mentor_status == 2 and report.mentee_status == 1:
                report_status = "Finalized"
            else:
                report_status = "In Progress"

            # Show Agree Button
            can_agree = (
                report.mentor_status == 2 and
                report.mentee_status == 0
            )

            result.append({

                "lms_isnob_id": report.lms_isnob_id,

                "report_title": report.report_title,

                "counselling_date": report.counselling_date,

                "mentor_name": (
                    mentor.first_name if mentor else ""
                ),

                "mentor_status": report.mentor_status,

                "mentee_status": report.mentee_status,

                "report_status": report_status,

                "can_agree": can_agree

            })

        return returnSuccess(result)

    except Exception as e:

        return returnException(str(e))
    
    # ==========================================================
# GET STUDENT ISSUE & OBSERVATION DETAILS
# ==========================================================
@router.get("/get_student_issue_observation/{lms_isnob_id}/{student_id}")
def get_student_issue_observation(
    lms_isnob_id: int,
    student_id: int,
    db: Session = Depends(get_db)
):

    try:

        report = db.query(
            LMSIssuesObservations
        ).filter(
            LMSIssuesObservations.lms_isnob_id == lms_isnob_id,
            LMSIssuesObservations.ssd_id == student_id,
            LMSIssuesObservations.is_deleted == 0
        ).first()

        if not report:

            return returnException(
                "Issue & Observation Report not found."
            )

        mentor = db.query(
            IEMSUsers
        ).filter(
            IEMSUsers.id == report.mentor_users_id
        ).first()

        # ----------------------------------------
        # Report Status
        # ----------------------------------------
        if report.mentor_status == 2 and report.mentee_status == 1:
            report_status = "Finalized"
        else:
            report_status = "In Progress"

        # ----------------------------------------
        # Show Agree Button
        # ----------------------------------------
        can_agree = (
            report.mentor_status == 2 and
            report.mentee_status == 0
        )

        result = {

            "lms_isnob_id": report.lms_isnob_id,

            "academic_batch_id": report.academic_batch_id,

            "semester_id": report.semester_id,

            "ssd_id": report.ssd_id,

            "student_usn": report.student_usn,

            "report_title": report.report_title,

            "counselling_date": report.counselling_date,

            "mentor_users_id": report.mentor_users_id,

            "mentor_name": mentor.first_name if mentor else "",

            "purpose_of_meeting_desc": report.purpose_of_meeting_desc,

            "observation_desc": report.observation_desc,

            "comm_parent_flag": report.comm_parent_flag,

            "comm_high_auth_flag": report.comm_high_auth_flag,

            "mentor_status": report.mentor_status,

            "mentee_status": report.mentee_status,

            "report_status": report_status,

            "can_agree": can_agree,

            "created_date": report.created_date,

            "modified_date": report.modified_date

        }

        return returnSuccess(result)

    except Exception as e:

        return returnException(str(e))
    
    # ==========================================================
# STUDENT AGREE TO ISSUE & OBSERVATION REPORT
# ==========================================================
@router.put("/student_agree/{lms_isnob_id}/{student_id}")
def student_agree(
    lms_isnob_id: int,
    student_id: int,
    db: Session = Depends(get_db)
):

    try:

        report = db.query(
            LMSIssuesObservations
        ).filter(
            LMSIssuesObservations.lms_isnob_id == lms_isnob_id,
            LMSIssuesObservations.ssd_id == student_id,
            LMSIssuesObservations.is_deleted == 0
        ).first()

        if not report:

            return returnException(
                "Issue & Observation Report not found."
            )

        # ---------------------------------------------
        # Mentor should have clicked Save & Agree
        # ---------------------------------------------
        if report.mentor_status != 2:

            return returnException(
                "Mentor has not agreed yet."
            )

        # ---------------------------------------------
        # Already agreed
        # ---------------------------------------------
        if report.mentee_status == 1:

            return returnException(
                "Report already agreed."
            )

        # ---------------------------------------------
        # Update Student Agreement
        # ---------------------------------------------
        report.mentee_status = 1

        report.modified_by = student_id

        report.modified_date = datetime.now()

        # Uncomment if you add this column
        # report.mentee_agree_date = datetime.now()

        db.commit()

        db.refresh(report)

        return returnSuccess({
            "lms_isnob_id": report.lms_isnob_id,
            "message": "Report agreed successfully."
        })

    except Exception as e:

        db.rollback()

        return returnException(str(e))
    
# ==========================================================
# GET ACADEMIC BATCHES MAPPED TO STUDENT
# ==========================================================
@router.get("/get_student_academic_batches/{student_id}")
def get_student_academic_batches(
    student_id: int,
    db: Session = Depends(get_db)
):
    try:

        batches = (
            db.query(IEMSAcademicBatch)
            .join(
                LMSMentorsGroupTerms,
                LMSMentorsGroupTerms.academic_batch_id == IEMSAcademicBatch.academic_batch_id
            )
            .join(
                LMSGroupMentees,
                LMSGroupMentees.mentors_group_terms_id == LMSMentorsGroupTerms.mentors_group_terms_id
            )
            .filter(
                LMSGroupMentees.student_id == student_id
            )
            .distinct()
            .order_by(IEMSAcademicBatch.academic_batch_desc)
            .all()
        )

        result = []

        for batch in batches:
            result.append({
                "academic_batch_id": batch.academic_batch_id,
                "academic_batch_code": batch.academic_batch_code,
                "academic_batch_desc": batch.academic_batch_desc
            })

        return returnSuccess(result)

    except Exception as e:
        return returnException(str(e))
# ==========================================================
# GET SEMESTERS MAPPED TO STUDENT
# ==========================================================
@router.get("/get_student_semesters/{student_id}/{academic_batch_id}")
def get_student_semesters(
    student_id: int,
    academic_batch_id: int,
    db: Session = Depends(get_db)
):
    try:

        semesters = (
            db.query(IEMSemester)
            .join(
                LMSMentorsGroupTerms,
                LMSMentorsGroupTerms.semester_id == IEMSemester.semester_id
            )
            .join(
                LMSGroupMentees,
                LMSGroupMentees.mentors_group_terms_id == LMSMentorsGroupTerms.mentors_group_terms_id
            )
            .filter(
                LMSGroupMentees.student_id == student_id,
                LMSMentorsGroupTerms.academic_batch_id == academic_batch_id
            )
            .distinct()
            .order_by(IEMSemester.semester_id)
            .all()
        )

        result = []

        for semester in semesters:
            result.append({
                "semester_id": semester.semester_id,
                "semester": semester.semester
            })

        return returnSuccess(result)

    except Exception as e:
        return returnException(str(e))
    
    # ==========================================================
# MENTOR SAVE & AGREE
# ==========================================================
@router.put("/mentor_save_agree/{lms_isnob_id}")
def mentor_save_agree(
    lms_isnob_id: int,
    db: Session = Depends(get_db)
):

    try:

        report = db.query(
            LMSIssuesObservations
        ).filter(
            LMSIssuesObservations.lms_isnob_id == lms_isnob_id,
            LMSIssuesObservations.is_deleted == 0
        ).first()

        if not report:

            return returnException(
                "Issue & Observation Report not found."
            )

        # Already agreed
        if report.mentor_status == 2:

            return returnException(
                "Report is already agreed by mentor."
            )

        # Save & Agree
        report.mentor_status = 2

        report.modified_by = report.mentor_users_id

        report.modified_date = datetime.now()

        db.commit()

        db.refresh(report)

        return returnSuccess({

            "lms_isnob_id": report.lms_isnob_id,

            "mentor_status": report.mentor_status,

            "message": "Report saved and agreed successfully."

        })

    except Exception as e:

        db.rollback()

        return returnException(str(e))
    
    # ==========================================================
# GET STUDENT ISSUE & OBSERVATION HISTORY
# ==========================================================
@router.get("/get_student_issue_observation_history/{lms_isnob_id}/{student_id}")
def get_student_issue_observation_history(
    lms_isnob_id: int,
    student_id: int,
    db: Session = Depends(get_db)
):

    try:

        # Verify report belongs to student
        report = db.query(
            LMSIssuesObservations
        ).filter(
            LMSIssuesObservations.lms_isnob_id == lms_isnob_id,
            LMSIssuesObservations.ssd_id == student_id,
            LMSIssuesObservations.is_deleted == 0
        ).first()

        if not report:
            return returnException(
                "Issue & Observation Report not found."
            )

        history = db.query(
            LMSIssuesObservationsHistory
        ).filter(
            LMSIssuesObservationsHistory.lms_isnob_id == lms_isnob_id
        ).order_by(
            LMSIssuesObservationsHistory.action_timestamp.desc()
        ).all()

        result = []

        for item in history:

            mentor = db.query(IEMSUsers).filter(
                IEMSUsers.id == item.mentor_users_id
            ).first()

            result.append({

                "history_id": item.history_id,

                "action_type": item.action_type,

                "action_timestamp": item.action_timestamp,

                "report_title": item.report_title,

                "counselling_date": item.counselling_date,

                "purpose_of_meeting_desc": item.purpose_of_meeting_desc,

                "observation_desc": item.observation_desc,

                "comm_parent_flag": item.comm_parent_flag,

                "comm_high_auth_flag": item.comm_high_auth_flag,

                "mentor_status": item.mentor_status,

                "mentee_status": item.mentee_status,

                "mentor_name": mentor.first_name if mentor else None

            })

        return returnSuccess(result)

    except Exception as e:

        return returnException(str(e))

# =================================================================
# GET CURRICULUM TERMS BY USN (Pure Query & Grouping Logic)
# =================================================================
@router.get("/get_crclm_term/{student_usn}", response_model=List[CurriculumGroup])
def get_term_details_by_usn(
    student_usn: str,
    db: Session = Depends(get_db)
):
    """
    This endpoint fetches term and curriculum details for a given student,
    using the correct SQLAlchemy models as defined in models.py.
    """
    try:
        # --- SQLAlchemy ORM Query ---
        # This query directly translates your raw SQL into a type-safe ORM query.
        query_results = (
            db.query(
                IEMSAcademicBatch.academic_batch_id,
                IEMSAcademicBatch.academic_batch_code,
                IEMSemester.semester_id,
                IEMSemester.semester_code
            )
            .select_from(IEMStudents)
            # 1. JOIN map_courseto_student
            .join(
                CudosMapCoursetoStudent,
                CudosMapCoursetoStudent.student_id == IEMStudents.student_id
            )
            # 2. JOIN crclm_terms
            .join(
                IEMSemester,
                (IEMSemester.semester_id == CudosMapCoursetoStudent.semester_id) &
                (IEMSemester.academic_batch_id == CudosMapCoursetoStudent.academic_batch_id)
            )
            # 3. JOIN curriculum
            .join(
                IEMSAcademicBatch,
                IEMSAcademicBatch.academic_batch_id == CudosMapCoursetoStudent.academic_batch_id
            )
            .join(
                IEMSCourses,
                IEMSCourses.crs_id == CudosMapCoursetoStudent.crs_id
            )
            # WHERE clause
            .filter(IEMStudents.usno == student_usn)
            # ORDER BY for correct grouping
            .order_by(IEMSAcademicBatch.academic_batch_id)
            .all()
        )

        if not query_results:
            return returnSuccess([])

        # --- Grouping Logic to create nested JSON ---
        final_list = []
        # Group by curriculum ID (crclm_id)
        for key, group in groupby(query_results, key=itemgetter(0)):
            group_list = list(group)
            first_item = group_list[0]
            
            curriculum_group = {
                "crclm_id": first_item.academic_batch_id,
                "crclm_name": first_item.academic_batch_code,
                "terms": [
                    {
                        "crclm_id": row.academic_batch_id,
                        "crclm_name": row.academic_batch_code,
                        "crclm_term_id": row.semester_id,
                        "term_name": row.semester_code,
                    }
                    for row in group_list
                ]
            }
            final_list.append(curriculum_group)
            
        return returnSuccess(final_list)

    except Exception as e:
        return returnException(str(e))
