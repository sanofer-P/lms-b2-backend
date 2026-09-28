from datetime import datetime

from fastapi import APIRouter, Depends, Form, UploadFile, File, Query 
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db
from app.utils.auth_helper import get_current_user
from app.utils.http_return_helper import (
    returnSuccess,
    returnException
)

from app.db.models import (
    IEMSAcademicBatch,
    IEMSemester,
    LMSMentorsGroup,
    LMSMentorsGroupTerms,
    LMSGroupMentors,
    LMSGroupMentees,
    LMSMentoringSchedule,
    LMSMentoringSubGroup,
    LMSMentoringSubGrpDate,
    LMSMapMenteeSchedule,

    LMSMenteeQuestionnaireResponse,
    LMSMenteeQuestionnaireResponseQue,
    LMSMenteeQuestionnaireResponseOption,

    LMSMMPSessionSuggestion,
    LMSMMPSessionSuggestionGenericComments,
    LMSMMPSessionSuggestionIndividualComments,

    LMSQuestionnairesQuestions,
    LMSQuestionnairesOptions,

    IEMStudents,
    IEMSUsers
)

from .lms_mentoring_session_schema import *

import uuid
import shutil
import os
UPLOAD_DIR = "uploads/mentoring_comments"

os.makedirs(
    UPLOAD_DIR,
    exist_ok=True
)

ALLOWED_EXTENSIONS = [
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "jpg",
    "jpeg",
    "png"
]

MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB

def validate_attachment(file):

    if not file:
        return

    ext = file.filename.split(".")[-1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise Exception(
            "Only pdf, doc, docx, xls, xlsx, jpg, jpeg, png allowed"
        )

    content = file.file.read()

    if len(content) > MAX_FILE_SIZE:
        raise Exception(
            "Maximum file size allowed is 2 MB"
        )

    file.file.seek(0)

def save_uploaded_file(file):

    if not file:
        return None

    ext = file.filename.split(".")[-1]

    file_name = (
        str(uuid.uuid4())
        + "."
        + ext
    )

    file_path = os.path.join(
        UPLOAD_DIR,
        file_name
    )

    with open(
        file_path,
        "wb"
    ) as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )

    return file_name

router = APIRouter()


def _as_text(value):
    """Make DATE/TIME/Decimal values safe for JSON responses."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _student_value(student, *names):
    for name in names:
        value = getattr(student, name, None)
        if value not in (None, ""):
            return value
    return None


# ==========================================================
# GET CURRICULUM LIST
# ==========================================================
@router.get("/get_academic_batch_list")
def get_academic_batch_list(
    db: Session = Depends(get_db)
):
    try:

        batches = db.query(
            IEMSAcademicBatch
        ).filter(
            IEMSAcademicBatch.status == 1
        ).all()

        result = []

        for row in batches:
            result.append({
                "academic_batch_id": row.academic_batch_id,
                "academic_batch_code": row.academic_batch_code,
                "academic_batch_desc": row.academic_batch_desc,
                "curriculum_name": (
                    f"{row.academic_batch_code} - "
                    f"{row.academic_batch_desc}"
                )
            })

        return returnSuccess(result)

    except Exception as e:
        return returnException(str(e))


# ==========================================================
# GET SEMESTERS BY CURRICULUM
# ==========================================================
@router.get("/get_semesters_by_academic_batch/{academic_batch_id}")
def get_semesters_by_academic_batch(
    academic_batch_id: int,
    mentors_group_id: int = Query(None),
    db: Session = Depends(get_db)
):
    try:
        semesters_query = db.query(IEMSemester).filter(
            IEMSemester.academic_batch_id == academic_batch_id
        )

        if mentors_group_id is not None:
            mapped_semester_ids = db.query(
                LMSMentorsGroupTerms.semester_id
            ).filter(
                LMSMentorsGroupTerms.mentors_group_id == mentors_group_id,
                LMSMentorsGroupTerms.academic_batch_id == academic_batch_id
            )
            semesters_query = semesters_query.filter(
                IEMSemester.semester_id.in_(mapped_semester_ids)
            )

        semesters = semesters_query.order_by(
            IEMSemester.semester
        ).all()

        result = []

        for sem in semesters:
            result.append({
                "semester_id": sem.semester_id,
                "semester": sem.semester,
                "semester_desc": sem.semester_desc,
                "term_name": sem.term_name
            })

        return returnSuccess(result)

    except Exception as e:
        return returnException(str(e))


# ==========================================================
# GET GROUPS BY CURRICULUM
# ==========================================================
@router.get("/get_groups_by_academic_batch/{academic_batch_id}")
def get_groups_by_academic_batch(
    academic_batch_id: int,
    db: Session = Depends(get_db)
):
    try:

        groups = db.query(
            LMSMentorsGroup
        ).filter(
            LMSMentorsGroup.academic_batch_id == academic_batch_id
        ).all()

        result = []

        for grp in groups:

            result.append({
                "mentors_group_id": grp.mentors_group_id,
                "group_name": grp.mentors_pgm_title,
                "mentors_pgm_title": grp.mentors_pgm_title,
                "questionnaire_id": grp.questionnaire_id
            })

        return returnSuccess(result)

    except Exception as e:
        return returnException(str(e))


# ==========================================================
# GET GROUP MENTEES
# ==========================================================
@router.get("/get_group_mentees/{mentors_group_id}/{semester_id}")
def get_group_mentees(
    mentors_group_id: int,
    semester_id: int,
    db: Session = Depends(get_db)
):
    try:

        term = db.query(
            LMSMentorsGroupTerms
        ).filter(
            LMSMentorsGroupTerms.mentors_group_id == mentors_group_id,
            LMSMentorsGroupTerms.semester_id == semester_id
        ).first()

        if not term:
            return returnSuccess([])

        mentees = db.query(
            LMSGroupMentees,
            IEMStudents
        ).join(
            IEMStudents,
            IEMStudents.student_id ==
            LMSGroupMentees.student_id
        ).filter(
            LMSGroupMentees.mentors_group_terms_id ==
            term.mentors_group_terms_id
        ).all()

        result = []

        for mentee, student in mentees:

            result.append({
                "student_id": student.student_id,
                "usn": student.usno,
                "student_usn": student.usno,
                "student_name": student.name,
                "email": student.email,
                "student_email": student.email,
                "mobile": student.mobile
            })

        return returnSuccess(result)

    except Exception as e:
        return returnException(str(e))


@router.get("/get_group_mentees/{mentors_group_id}")
def get_group_mentees_without_semester(
    mentors_group_id: int,
    db: Session = Depends(get_db)
):
    try:
        terms = db.query(
            LMSMentorsGroupTerms
        ).filter(
            LMSMentorsGroupTerms.mentors_group_id == mentors_group_id
        ).all()

        if not terms:
            return returnSuccess([])

        term_ids = [t.mentors_group_terms_id for t in terms]

        mentees = db.query(
            LMSGroupMentees,
            IEMStudents
        ).join(
            IEMStudents,
            IEMStudents.student_id ==
            LMSGroupMentees.student_id
        ).filter(
            LMSGroupMentees.mentors_group_terms_id.in_(term_ids)
        ).all()

        result = []
        seen_student_ids = set()

        for mentee, student in mentees:
            if student.student_id not in seen_student_ids:
                seen_student_ids.add(student.student_id)
                result.append({
                    "student_id": student.student_id,
                    "usn": student.usno,
                    "student_usn": student.usno,
                    "student_name": student.name,
                    "email": student.email,
                    "student_email": student.email,
                    "mobile": student.mobile
                })

        return returnSuccess(result)

    except Exception as e:
        return returnException(str(e))
    
@router.post("/save_mentoring_session")
def save_mentoring_session(
    req: MentoringSessionCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    try:

        user_id = current_user.get("user_id")

        # --------------------------------------------------
        # Validate Group
        # --------------------------------------------------
        group = db.query(
            LMSMentorsGroup
        ).filter(
            LMSMentorsGroup.mentors_group_id ==
            req.mentors_group_id
        ).first()

        if not group:
            return returnException(
                "Invalid mentoring group selected"
            )

        # --------------------------------------------------
        # Validate Semester Mapping
        # --------------------------------------------------
        group_term = db.query(
            LMSMentorsGroupTerms
        ).filter(
            LMSMentorsGroupTerms.mentors_group_id ==
            req.mentors_group_id,

            LMSMentorsGroupTerms.semester_id ==
            req.semester_id
        ).first()

        if not group_term:
            return returnException(
                "Selected semester is not mapped to selected group"
            )

        # --------------------------------------------------
        # Get Allowed Mentees
        # --------------------------------------------------
        group_mentees = db.query(
            LMSGroupMentees.student_id
        ).filter(
            LMSGroupMentees.mentors_group_terms_id ==
            group_term.mentors_group_terms_id
        ).all()

        allowed_students = {
            row.student_id
            for row in group_mentees
        }

        # --------------------------------------------------
        # Duplicate Session Validation
        # --------------------------------------------------
        all_mentees = []

        for subgroup in req.sub_groups:
            all_mentees.extend(
                subgroup.mentee_ids
            )

        duplicate_students = db.query(
            LMSMapMenteeSchedule.student_id
        ).filter(
            LMSMapMenteeSchedule.student_id.in_(
                all_mentees
            )
        ).all()

        if duplicate_students:

            duplicate_ids = [
                row.student_id
                for row in duplicate_students
            ]

            return returnException(
                f"Mentees already mapped to another session : {duplicate_ids}"
            )

        # --------------------------------------------------
        # Create Schedule
        # --------------------------------------------------
        schedule = LMSMentoringSchedule(
            mentors_group_terms_id=
                group_term.mentors_group_terms_id,

            questionnaire_id=
                group.questionnaire_id,

            session_agenda=
                req.session_agenda,

            created_by=
                current_user["user_id"]
        )

        db.add(schedule)
        db.flush()

        # --------------------------------------------------
        # Create Sub Groups
        # --------------------------------------------------
        for subgroup in req.sub_groups:

            db_subgroup = LMSMentoringSubGroup(

                schedule_id=
                schedule.schedule_id,

                sub_group_name=
                subgroup.sub_group_name,

                location=
                subgroup.location,

                created_by=
                user_id
            )

            db.add(db_subgroup)
            db.flush()

            # ----------------------------------------------
            # Save Dates
            # ----------------------------------------------
            for dt in subgroup.dates:

                if dt.start_date > dt.end_date:

                    db.rollback()

                    return returnException(
                        "Start date cannot be greater than end date"
                    )

                if dt.start_time >= dt.end_time:

                    db.rollback()

                    return returnException(
                        "Start time must be less than end time"
                    )

                db_date = LMSMentoringSubGrpDate(

                    sub_group_id=
                    db_subgroup.sub_group_id,

                    start_date=
                    dt.start_date,

                    end_date=
                    dt.end_date,

                    start_time=
                    dt.start_time,

                    end_time=
                    dt.end_time,

                    created_by=
                    user_id
                )

                db.add(db_date)

            # ----------------------------------------------
            # Save Mentees
            # ----------------------------------------------
            for student_id in subgroup.mentee_ids:

                if student_id not in allowed_students:

                    db.rollback()

                    return returnException(
                        f"Student {student_id} is not part of selected mentoring group"
                    )

                db_mentee = LMSMapMenteeSchedule(

                    schedule_id=
                    schedule.schedule_id,

                    student_id=
                    student_id,

                    sub_group_id=
                    db_subgroup.sub_group_id
                )

                db.add(db_mentee)

        db.commit()

        return returnSuccess({
            "schedule_id":
            schedule.schedule_id
        })

    except Exception as e:

        db.rollback()

        return returnException(
            str(e)
        )
    
@router.get("/get_mentoring_sessions")
def get_mentoring_sessions(
    academic_batch_id: Optional[int] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db)
):

    result = []

    groups_query = db.query(LMSMentorsGroup)
    if academic_batch_id is not None:
        groups_query = groups_query.filter(
            LMSMentorsGroup.academic_batch_id == academic_batch_id
        )
    groups = groups_query.all()

    for group in groups:

        group_terms = db.query(
            LMSMentorsGroupTerms
        ).filter(
            LMSMentorsGroupTerms.mentors_group_id ==
            group.mentors_group_id
        ).all()

        for term in group_terms:

            schedules = db.query(
                LMSMentoringSchedule
            ).filter(
                LMSMentoringSchedule.mentors_group_terms_id ==
                term.mentors_group_terms_id
            ).all()

            for schedule in schedules:

                sub_groups = db.query(
                    LMSMentoringSubGroup
                ).filter(
                    LMSMentoringSubGroup.schedule_id ==
                    schedule.schedule_id
                ).all()

                subgroup_list = []

                include_schedule = False

                for subgroup in sub_groups:

                    dates = db.query(
                        LMSMentoringSubGrpDate
                    ).filter(
                        LMSMentoringSubGrpDate.sub_group_id ==
                        subgroup.sub_group_id
                    ).all()

                    date_list = []

                    for dt in dates:

                        if (month is None or dt.start_date.month == month) and (year is None or dt.start_date.year == year):

                            include_schedule = True

                            mentee_count = db.query(
                                LMSMapMenteeSchedule
                            ).filter(
                                LMSMapMenteeSchedule.sub_group_id ==
                                subgroup.sub_group_id
                            ).count()

                            date_list.append({

                                "sub_group_date_id":
                                dt.sub_group_date_id,

                                "start_date":
                                dt.start_date,

                                "end_date":
                                dt.end_date,

                                "start_time":
                                dt.start_time,

                                "end_time":
                                dt.end_time,

                                "status":
                                dt.status,

                                "mentee_count":
                                mentee_count
                            })

                    if date_list or (month is None and year is None):
                        include_schedule = True
                        subgroup_list.append({

                            "sub_group_id":
                            subgroup.sub_group_id,

                            "sub_group_name":
                            subgroup.sub_group_name,

                            "location":
                            subgroup.location,

                            "dates":
                            date_list
                        })

                if include_schedule or (month is None and year is None):

                    result.append({

                        "schedule_id":
                        schedule.schedule_id,

                        "academic_batch_id":
                        group.academic_batch_id,

                        "mentors_group_id":
                        group.mentors_group_id,

                        "group_name":
                        group.mentors_pgm_title,

                        "semester_id":
                        term.semester_id,

                        "questionnaire_id":
                        schedule.questionnaire_id,

                        "session_agenda":
                        schedule.session_agenda,

                        "sub_groups":
                        subgroup_list
                    })

    return returnSuccess(result)

@router.get("/get_session_mentees/{schedule_id}")
def get_session_mentees(
    schedule_id: int,
    db: Session = Depends(get_db)
):

    mappings = db.query(
        LMSMapMenteeSchedule
    ).filter(
        LMSMapMenteeSchedule.schedule_id == schedule_id
    ).all()

    result = []

    for row in mappings:

        student = db.query(
            IEMStudents
        ).filter(
            IEMStudents.student_id == row.student_id
        ).first()

        subgroup = db.query(
            LMSMentoringSubGroup
        ).filter(
            LMSMentoringSubGroup.sub_group_id ==
            row.sub_group_id
        ).first()

        result.append({
            "map_mentee_schedule_id":
                row.map_mentee_schedule_id,

            "student_id":
                row.student_id,

            "student_name":
                student.name if student else None,

            "regno":
                student.regno if student else None,

            "sub_group_id":
                row.sub_group_id,

            "sub_group_name":
                subgroup.sub_group_name if subgroup else None
        })

    return returnSuccess(result)

@router.put("/update_mentoring_session/{schedule_id}")
def update_mentoring_session(
    schedule_id: int,
    req: MentoringSessionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    try:
        user_id = current_user.get("user_id")

        # --------------------------------------------------
        # 1. Fetch and Validate Existing Schedule
        # --------------------------------------------------
        schedule = db.query(LMSMentoringSchedule).filter(
            LMSMentoringSchedule.schedule_id == schedule_id
        ).first()

        if not schedule:
            return returnException("Session not found")

        # --------------------------------------------------
        # 2. Validate Group & Semester Mapping
        # --------------------------------------------------
        group = db.query(LMSMentorsGroup).filter(
            LMSMentorsGroup.mentors_group_id == req.mentors_group_id
        ).first()

        if not group:
            return returnException("Invalid mentoring group selected")

        group_term = db.query(LMSMentorsGroupTerms).filter(
            LMSMentorsGroupTerms.mentors_group_id == req.mentors_group_id,
            LMSMentorsGroupTerms.semester_id == req.semester_id
        ).first()

        if not group_term:
            return returnException("Selected semester is not mapped to selected group")

        # --------------------------------------------------
        # 3. Fetch Allowed Group Mentees
        # --------------------------------------------------
        group_mentees = db.query(LMSGroupMentees.student_id).filter(
            LMSGroupMentees.mentors_group_terms_id == group_term.mentors_group_terms_id
        ).all()
        allowed_students = {row.student_id for row in group_mentees}

        # --------------------------------------------------
        # 4. Update Core Schedule Fields
        # --------------------------------------------------
        schedule.session_agenda = req.session_agenda
        schedule.questionnaire_id = group.questionnaire_id
        schedule.mentors_group_terms_id = group_term.mentors_group_terms_id
        schedule.modified_by = user_id
        db.flush()

        # --------------------------------------------------
        # 5. Clear Out Existing Mappings (Teardown for Sync)
        # --------------------------------------------------
        # Fetch current sub-groups linked to this schedule to delete their dates safely
        existing_subgroups = db.query(LMSMentoringSubGroup).filter(
            LMSMentoringSubGroup.schedule_id == schedule_id
        ).all()
        existing_subgroup_ids = [sg.sub_group_id for sg in existing_subgroups]

        if existing_subgroup_ids:
            # Delete old mapped dates
            db.query(LMSMentoringSubGrpDate).filter(
                LMSMentoringSubGrpDate.sub_group_id.in_(existing_subgroup_ids)
            ).delete(synchronize_session=False)

        # Delete old mapped mentees
        db.query(LMSMapMenteeSchedule).filter(
            LMSMapMenteeSchedule.schedule_id == schedule_id
        ).delete(synchronize_session=False)

        # Delete old sub-groups
        db.query(LMSMentoringSubGroup).filter(
            LMSMentoringSubGroup.schedule_id == schedule_id
        ).delete(synchronize_session=False)
        db.flush()

        # --------------------------------------------------
        # 6. Re-create / Add Updated Sub-Groups, Dates, and Mentees
        # --------------------------------------------------
        for subgroup in req.sub_groups:
            db_subgroup = LMSMentoringSubGroup(
                schedule_id=schedule.schedule_id,
                sub_group_name=subgroup.sub_group_name,
                location=subgroup.location,
                created_by=user_id,
                modified_by=user_id
            )
            db.add(db_subgroup)
            db.flush()

            # Save Dates
            for dt in subgroup.dates:
                if dt.start_date > dt.end_date:
                    db.rollback()
                    return returnException("Start date cannot be greater than end date")
                if dt.start_time >= dt.end_time:
                    db.rollback()
                    return returnException("Start time must be less than end time")

                db_date = LMSMentoringSubGrpDate(
                    sub_group_id=db_subgroup.sub_group_id,
                    start_date=dt.start_date,
                    end_date=dt.end_date,
                    start_time=dt.start_time,
                    end_time=dt.end_time,
                    created_by=user_id
                )
                db.add(db_date)

            # Save Mentees
            for student_id in subgroup.mentee_ids:
                if student_id not in allowed_students:
                    db.rollback()
                    return returnException(
                        f"Student {student_id} is not part of the selected mentoring group"
                    )

                db_mentee = LMSMapMenteeSchedule(
                    schedule_id=schedule.schedule_id,
                    student_id=student_id,
                    sub_group_id=db_subgroup.sub_group_id
                )
                db.add(db_mentee)

        db.commit()
        return returnSuccess("Session and sub-groups updated successfully")

    except Exception as e:
        db.rollback()
        return returnException(str(e))

@router.delete(
    "/delete_mentoring_session/{schedule_id}"
)
def delete_mentoring_session(
    schedule_id: int,
    db: Session = Depends(get_db)
):

    session = db.query(
        LMSMentoringSchedule
    ).filter(
        LMSMentoringSchedule.schedule_id ==
        schedule_id
    ).first()

    if not session:
        return returnException(
            "Session not found"
        )

    db.delete(session)
    db.commit()

    return returnSuccess(
        "Session deleted successfully"
    )

@router.get("/sessions/{schedule_id}/mentees")
def get_mentoring_session_mentees(
    schedule_id: int,
    # 🌟 BACKEND FIX: Accept the sub_group_id query parameter
    sub_group_id: int = Query(...), 
    db: Session = Depends(get_db)
):
    try:
        # Join the Mapping table with Students table
        query = (
            db.query(
                LMSMapMenteeSchedule.student_id,
                IEMStudents.usno.label("student_usn"),  # Ensure column names match your DB
                IEMStudents.name.label("student_name"),
                IEMStudents.email.label("student_email"),
                IEMStudents.mobile.label("contact_number"),
                LMSMapMenteeSchedule.sub_group_id
            )
            .join(
                IEMStudents,
                IEMStudents.student_id == LMSMapMenteeSchedule.student_id
            )
            .filter(
                LMSMapMenteeSchedule.schedule_id == schedule_id,
                # 🌟 Filter explicitly by the requested subgroup
                LMSMapMenteeSchedule.sub_group_id == sub_group_id
            )
        )
        
        # Execute query
        data = query.all()

        # Format results as clean JSON dictionaries for React
        result = [
            {
                "student_id": row.student_id,
                "student_usn": row.student_usn,
                "student_name": row.student_name,
                "student_email": row.student_email,
                "contact_number": row.contact_number,
                "sub_group_id": row.sub_group_id
            }
            for row in data
        ]

        return returnSuccess(result)

    except Exception as e:
        return returnException(f"Failed to fetch mentees: {str(e)}")
    
@router.post("/get_mentee_questionnaire_response")
def get_mentee_questionnaire_response(
    req: MenteeResponseRequest,
    db: Session = Depends(get_db)
):
    try:

        response = (
            db.query(
                LMSMenteeQuestionnaireResponse
            )
            .filter(
                LMSMenteeQuestionnaireResponse.schedule_id ==
                req.schedule_id,
                LMSMenteeQuestionnaireResponse.student_id ==
                req.student_id
            )
            .first()
        )

        if not response:
            return returnSuccess([])

        result = []

        answers = (
            db.query(
                LMSMenteeQuestionnaireResponseQue,
                LMSQuestionnairesQuestions
            )
            .join(
                LMSQuestionnairesQuestions,
                LMSQuestionnairesQuestions.questionnaire_que_id ==
                LMSMenteeQuestionnaireResponseQue.questionnaire_que_id
            )
            .filter(
                LMSMenteeQuestionnaireResponseQue.questionnaire_response_id ==
                response.questionnaire_response_id
            )
            .all()
        )

        for ans, que in answers:

            options = (
                db.query(
                    LMSMenteeQuestionnaireResponseOption,
                    LMSQuestionnairesOptions
                )
                .join(
                    LMSQuestionnairesOptions,
                    LMSQuestionnairesOptions.questionnaire_options_id ==
                    LMSMenteeQuestionnaireResponseOption.questionnaire_options_id
                )
                .filter(
                    LMSMenteeQuestionnaireResponseOption.questionnaire_response_que_id ==
                    ans.questionnaire_response_que_id
                )
                .all()
            )

            selected_options = []

            for op, opt in options:
                selected_options.append({
                    "option_id": opt.questionnaire_options_id,
                    "option_name": opt.que_option,
                    "specification": op.specification
                })

            result.append({
                "question_id": que.questionnaire_que_id,
                "question": que.question,
                "text_answer": ans.text_answer,
                "selected_options": selected_options
            })

        return returnSuccess(result)

    except Exception as e:
        return returnException(str(e))
    
@router.post(
    "/save_generic_comment"
)
def save_generic_comment(
    schedule_id: int = Form(...),
    comment: str = Form(...),
    suggestion_type: int = Form(0),
    user_type: int = Form(0),
    attachment: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        validate_attachment(
            attachment
        )

        file_name = save_uploaded_file(
            attachment
        )

        suggestion = db.query(
            LMSMMPSessionSuggestion
        ).filter(
            LMSMMPSessionSuggestion.schedule_id ==
            schedule_id
        ).first()

        if not suggestion:

            suggestion = LMSMMPSessionSuggestion(
                schedule_id=schedule_id,
                created_by=current_user["user_id"]
            )

            db.add(suggestion)
            db.flush()

        db_comment = (
            LMSMMPSessionSuggestionGenericComments(
                session_suggestion_id=
                    suggestion.session_suggestion_id,

                comment=comment,

                attachment=file_name,

                suggestion_type=suggestion_type,

                user_type=user_type,

                created_by=
                    current_user["user_id"]
            )
        )

        db.add(db_comment)

        db.commit()

        return returnSuccess(
            "Comment Saved Successfully"
        )

    except Exception as e:

        db.rollback()

        return returnException(
            str(e)
        )
    
@router.post("/save_individual_comment")
def save_individual_comment(
    schedule_id: int = Form(...),
    mentee_id: int = Form(...),
    comment: str = Form(...),
    suggestion_type: int = Form(0),
    attachment: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):

    try:

        validate_attachment(
            attachment
        )

        file_name = save_uploaded_file(
            attachment
        )

        suggestion = db.query(
            LMSMMPSessionSuggestion
        ).filter(
            LMSMMPSessionSuggestion.schedule_id ==
            schedule_id
        ).first()

        if not suggestion:

            suggestion = LMSMMPSessionSuggestion(
                schedule_id=schedule_id,
                created_by=current_user["user_id"]
            )

            db.add(suggestion)
            db.flush()

        db_comment = (
            LMSMMPSessionSuggestionIndividualComments(
                session_suggestion_id=
                    suggestion.session_suggestion_id,

                comment=comment,

                attachment=file_name,

                suggestion_type=
                    suggestion_type,

                from_user_id=
                    current_user["user_id"],

                mentee_id=
                    mentee_id,

                from_user_type=1,

                created_by=
                    current_user["user_id"]
            )
        )

        db.add(db_comment)

        db.commit()

        return returnSuccess(
            "Individual Comment Saved Successfully"
        )

    except Exception as e:

        db.rollback()

        return returnException(
            str(e)
        )
    
@router.get("/get_generic_comments/{schedule_id}")
def get_generic_comments(
    schedule_id: int,
    db: Session = Depends(get_db)
):
    try:

        data = db.query(
            LMSMMPSessionSuggestionGenericComments,
            IEMSUsers.first_name
        ).join(
            LMSMMPSessionSuggestion,
            LMSMMPSessionSuggestion.session_suggestion_id ==
            LMSMMPSessionSuggestionGenericComments.session_suggestion_id
        ).outerjoin(
            IEMSUsers,
            IEMSUsers.id ==
            LMSMMPSessionSuggestionGenericComments.created_by
        ).filter(
            LMSMMPSessionSuggestion.schedule_id ==
            schedule_id
        ).all()

        result = []

        for row, user in data:

            result.append({
                "generic_comment_id":
                    row.generic_comment_id,

                "comment":
                    row.comment,

                "attachment":
                    row.attachment,

                "created_by":
                    user,

                "created_date":
                    row.created_date
            })

        return returnSuccess(result)

    except Exception as e:

        return returnException(str(e))
    
@router.get(
    "/get_individual_comments/{schedule_id}/{mentee_id}"
)
def get_individual_comments(
    schedule_id: int,
    mentee_id: int,
    db: Session = Depends(get_db)
):
    try:

        data = db.query(
            LMSMMPSessionSuggestionIndividualComments
        ).join(
            LMSMMPSessionSuggestion,
            LMSMMPSessionSuggestion.session_suggestion_id ==
            LMSMMPSessionSuggestionIndividualComments.session_suggestion_id
        ).filter(
            LMSMMPSessionSuggestion.schedule_id ==
            schedule_id,

            LMSMMPSessionSuggestionIndividualComments.mentee_id ==
            mentee_id
        ).all()

        result = []

        for row in data:

            result.append({
                "individual_comment_id":
                    row.individual_comment_id,

                "comment":
                    row.comment,

                "attachment":
                    row.attachment,

                "mentee_id":
                    row.mentee_id,

                "from_user_id":
                    row.from_user_id,

                "created_date":
                    row.created_date
            })

        return returnSuccess(result)

    except Exception as e:

        return returnException(str(e))

# ==========================================================
# CHANGE STATUS ROUTE
# ==========================================================
@router.get("/get_mmp_report")
def get_mmp_report(
    academic_batch_id: int,
    mentors_group_id: int,
    semester_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Return the complete MMP report in one request.

    This is the FastAPI equivalent of CodeIgniter's get_student_details(): the
    selected curriculum, group, term and student are validated together before
    any report data is returned.
    """
    try:
        group = db.query(LMSMentorsGroup).filter(
            LMSMentorsGroup.mentors_group_id == mentors_group_id,
            LMSMentorsGroup.academic_batch_id == academic_batch_id
        ).first()
        if not group:
            return returnException("Mentoring group not found for the selected curriculum.")

        group_term = db.query(LMSMentorsGroupTerms).filter(
            LMSMentorsGroupTerms.mentors_group_id == mentors_group_id,
            LMSMentorsGroupTerms.semester_id == semester_id
        ).first()
        if not group_term:
            return returnException("Term is not mapped to the selected mentoring group.")

        mentee_mapping = db.query(LMSGroupMentees).filter(
            LMSGroupMentees.mentors_group_terms_id == group_term.mentors_group_terms_id,
            LMSGroupMentees.student_id == student_id
        ).first()
        if not mentee_mapping:
            return returnException("Student is not mapped to the selected group and term.")

        student = db.query(IEMStudents).filter(
            IEMStudents.student_id == student_id
        ).first()
        if not student:
            return returnException("Student not found.")

        mentor_rows = db.query(LMSGroupMentors, IEMSUsers).join(
            IEMSUsers,
            IEMSUsers.id == LMSGroupMentors.mentor_id
        ).filter(
            LMSGroupMentors.mentors_group_terms_id == group_term.mentors_group_terms_id
        ).all()
        mentors = [
            {
                "mentor_id": mentor.mentor_id,
                "mentor_name": " ".join(filter(None, [
                    getattr(user, "title", None),
                    getattr(user, "first_name", None),
                    getattr(user, "last_name", None)
                ])) or getattr(user, "username", "")
            }
            for mentor, user in mentor_rows
        ]

        schedules = db.query(LMSMentoringSchedule).filter(
            LMSMentoringSchedule.mentors_group_terms_id == group_term.mentors_group_terms_id
        ).order_by(LMSMentoringSchedule.schedule_id).all()

        sessions = []
        questionnaire_responses = []
        suggestions = []

        for schedule in schedules:
            schedule_mapping = db.query(LMSMapMenteeSchedule).filter(
                LMSMapMenteeSchedule.schedule_id == schedule.schedule_id,
                LMSMapMenteeSchedule.student_id == student_id
            ).first()
            if not schedule_mapping:
                continue

            subgroup = db.query(LMSMentoringSubGroup).filter(
                LMSMentoringSubGroup.sub_group_id == schedule_mapping.sub_group_id
            ).first()
            date_rows = []
            if subgroup:
                dates = db.query(LMSMentoringSubGrpDate).filter(
                    LMSMentoringSubGrpDate.sub_group_id == subgroup.sub_group_id
                ).order_by(LMSMentoringSubGrpDate.start_date).all()
                date_rows = [{
                    "start_date": _as_text(row.start_date),
                    "end_date": _as_text(row.end_date),
                    "start_time": _as_text(row.start_time),
                    "end_time": _as_text(row.end_time),
                    "status": row.status
                } for row in dates]

            response = db.query(LMSMenteeQuestionnaireResponse).filter(
                LMSMenteeQuestionnaireResponse.student_id == student_id,
                LMSMenteeQuestionnaireResponse.schedule_id == schedule.schedule_id
            ).first()
            response_data = None
            if response:
                answers = []
                response_questions = db.query(LMSMenteeQuestionnaireResponseQue).filter(
                    LMSMenteeQuestionnaireResponseQue.questionnaire_response_id ==
                    response.questionnaire_response_id
                ).all()
                for response_question in response_questions:
                    question = db.query(LMSQuestionnairesQuestions).filter(
                        LMSQuestionnairesQuestions.questionnaire_que_id ==
                        response_question.questionnaire_que_id
                    ).first()
                    option_rows = db.query(
                        LMSMenteeQuestionnaireResponseOption,
                        LMSQuestionnairesOptions
                    ).join(
                        LMSQuestionnairesOptions,
                        LMSQuestionnairesOptions.questionnaire_options_id ==
                        LMSMenteeQuestionnaireResponseOption.questionnaire_options_id
                    ).filter(
                        LMSMenteeQuestionnaireResponseOption.questionnaire_response_que_id ==
                        response_question.questionnaire_response_que_id
                    ).all()
                    selected_options = [{
                        "questionnaire_options_id": option.questionnaire_options_id,
                        "option_text": getattr(option_detail, "que_option", None),
                        "specification": (
                            getattr(option, "specification", None)
                            or getattr(option_detail, "specification", None)
                            or ""
                        )
                    } for option, option_detail in option_rows]
                    answer = {
                        "questionnaire_que_id": response_question.questionnaire_que_id,
                        "question_text": question.question if question else "",
                        "text_answer": response_question.text_answer,
                        "selected_options": selected_options
                    }
                    answers.append(answer)
                    questionnaire_responses.append({
                        **answer,
                        "schedule_id": schedule.schedule_id,
                        "submitted_at": _as_text(response.created_date)
                    })
                response_data = {
                    "submitted_at": _as_text(response.created_date),
                    "answers": answers
                }

            suggestion = db.query(LMSMMPSessionSuggestion).filter(
                LMSMMPSessionSuggestion.schedule_id == schedule.schedule_id
            ).first()
            comments = []
            if suggestion:
                generic = db.query(LMSMMPSessionSuggestionGenericComments).filter(
                    LMSMMPSessionSuggestionGenericComments.session_suggestion_id ==
                    suggestion.session_suggestion_id
                ).all()
                individual = db.query(LMSMMPSessionSuggestionIndividualComments).filter(
                    LMSMMPSessionSuggestionIndividualComments.session_suggestion_id ==
                    suggestion.session_suggestion_id,
                    LMSMMPSessionSuggestionIndividualComments.mentee_id == student_id
                ).all()
                for scope, rows in (("common", generic), ("individual", individual)):
                    for row in rows:
                        sender = db.query(IEMSUsers).filter(
                            IEMSUsers.id == row.created_by
                        ).first()
                        item = {
                            "scope": scope,
                            "sender_name": " ".join(filter(None, [
                                getattr(sender, "first_name", None),
                                getattr(sender, "last_name", None)
                            ])) if sender else "Student",
                            "comment": row.comment,
                            "attachment": row.attachment,
                            "created_date": _as_text(row.created_date)
                        }
                        comments.append(item)
                        suggestions.append({**item, "schedule_id": schedule.schedule_id})
                comments.sort(key=lambda row: row.get("created_date") or "")

            sessions.append({
                "schedule_id": schedule.schedule_id,
                "curriculum_id": academic_batch_id,
                "mentors_group_id": mentors_group_id,
                "group_name": group.mentors_pgm_title,
                "semester_id": semester_id,
                "questionnaire_id": schedule.questionnaire_id,
                "session_agenda": schedule.session_agenda,
                "sub_groups": [{
                    "sub_group_name": subgroup.sub_group_name,
                    "location": subgroup.location,
                    "dates": date_rows
                }] if subgroup else [],
                "response": response_data,
                "comments": comments
            })

        batch = db.query(IEMSAcademicBatch).filter(
            IEMSAcademicBatch.academic_batch_id == academic_batch_id
        ).first()
        semester = db.query(IEMSemester).filter(
            IEMSemester.semester_id == semester_id
        ).first()

        return returnSuccess({
            "student": {
                "student_id": student.student_id,
                "student_usn": _student_value(student, "usno", "regno"),
                "student_name": _student_value(student, "name"),
                "student_email": _student_value(student, "email"),
                "mobile": _student_value(student, "mobile")
            },
            "curriculum": {
                "academic_batch_id": academic_batch_id,
                "academic_batch_code": getattr(batch, "academic_batch_code", None),
                "academic_batch_desc": getattr(batch, "academic_batch_desc", None)
            },
            "group": {
                "mentors_group_id": mentors_group_id,
                "mentors_pgm_title": group.mentors_pgm_title
            },
            "term": {
                "semester_id": semester_id,
                "semester_desc": getattr(semester, "semester_desc", None),
                "term_name": getattr(semester, "term_name", None)
            },
            "mentors": mentors,
            "sessions": sessions,
            "questionnaire_responses": questionnaire_responses,
            "suggestions": suggestions
        })
    except Exception as e:
        return returnException(str(e))


@router.post("/change_status")
def change_status(
    sgd: int = Form(...),                  # Matches post parameter $this->input->post('sgd')
    status: str = Form(...),               # Matches post parameter $this->input->post('status')
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user) # Included to guard authorization secure check
):
    try:
        # 1. Prepare query criteria equivalent to $where
        date_record = db.query(LMSMentoringSubGrpDate).filter(
            LMSMentoringSubGrpDate.sub_group_date_id == sgd
        ).first()

        if not date_record:
            return returnException("Sub-group date slot not found.")

        # 2. Update status value
        date_record.status = status
        
        # 3. Commit transaction to the database
        db.commit()

        # 4. Return success response format
        return returnSuccess("Status updated successfully.")

    except Exception as e:
        db.rollback()
        return returnException(f"Failed to update status, try again. Error: {str(e)}")
