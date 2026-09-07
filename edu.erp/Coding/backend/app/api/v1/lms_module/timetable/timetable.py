from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, distinct, text, bindparam
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
from io import BytesIO
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.core.database import get_db
from app.db.models import (
    LMSTimetableDetails,
    LMSTimetable,
    LMSTimetableDayMapping,
    LMSTimetableBatchMap,
    LMSWeekDay,
    IEMSCourses,
    IEMSAcademicBatch,
    IEMSemester,
    MasterTypeDetails,
    CudosMapCoursetoCourseInstructor,
    IEMSUsers,
    CudosCourseCloOwner,

)
from app.api.v1.lms_module.timetable.timetable_schema import *
from app.utils.auth_helper import get_current_user
from app.utils.http_return_helper import returnException, returnSuccess

logger = logging.getLogger(__name__)
router = APIRouter(tags=["LMS-Timetable"])

print("TIMETABLE MODULE LOADED")


@router.get("/fetch_curriculum")
def fetch_curriculum(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Fetch curriculum list for Manage Timetable.
    """

    try:

        curriculums = (
            db.query(IEMSAcademicBatch)
            .order_by(
                IEMSAcademicBatch.academic_batch_id.desc()
            )
            .all()
        )

        data = []

        for curriculum in curriculums:

            data.append({
                "academic_batch_id":
                    curriculum.academic_batch_id,

                "academic_batch_desc":
                    curriculum.academic_batch_desc
            })

        return returnSuccess(data)

    except Exception as e:

        logger.error(
            f"Error fetching curriculum: {str(e)}"
        )

        return returnException(
            str(e)
        )
# ============================================================================
# CURRICULUM & TERM APIs
# ============================================================================

@router.post("/fetch_term_design")
def fetch_term_design(
    request: FetchTermRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        terms = db.query(IEMSemester).filter(
            IEMSemester.academic_batch_id == request.academic_batch_id
        ).order_by(IEMSemester.semester_id.asc()).all()

        data = [
            {
                "semester_id": term.semester_id,
                "semester": term.semester
            }
            for term in terms
        ]

        return returnSuccess(data)
    except Exception as e:
        logger.error(f"Error fetching terms: {str(e)}")
        return returnException(str(e))
    
@router.post("/get_section_details")
def get_section_details(
    request: GetSectionRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Fetch sections using ORM pattern similar to /meta/sections
        sections = (
            db.query(
                CudosMapCoursetoCourseInstructor.section_id,
                MasterTypeDetails.mt_details_name,
            )
            .join(
                MasterTypeDetails,
                MasterTypeDetails.mt_details_id == CudosMapCoursetoCourseInstructor.section_id,
            )
            .filter(
                CudosMapCoursetoCourseInstructor.academic_batch_id == request.academic_batch_id
            )
            .filter(
                CudosMapCoursetoCourseInstructor.semester_id == request.semester_id
            )
            .filter(
                CudosMapCoursetoCourseInstructor.section_id.isnot(None)
            )
            .distinct()
            .order_by(
                MasterTypeDetails.mt_details_name.asc()
            )
            .all()
        )

        # Format response
        data = [
            {
                "section_id": section_id,
                "section_name": section_name
            }
            for section_id, section_name in sections
        ]

        return returnSuccess(data)

    except Exception as e:
        logger.error(f"Error fetching sections: {str(e)}")
        return returnException(str(e))

@router.post("/set_dept_pgm_session")
def set_dept_pgm_session(
    crclm_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Backtrace dept_id and pgm_id when curriculum changed
    Original PHP: set_dept_pgm_session()
    """
    try:
        curriculum = db.query(IEMSAcademicBatch).filter(
            IEMSAcademicBatch.academic_batch_id == crclm_id
        ).first()

        if curriculum:
            data = {
                'dept_id': curriculum.dept_id,
                'pgm_id': curriculum.pgm_id
            }
        else:
            data = {}

        return returnSuccess(data)
    except Exception as e:
        logger.error(f"Error setting dept/pgm session: {str(e)}")
        return returnException(str(e))

@router.post("/select_course")
def select_course(
    request: SelectCourseRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        query = db.query(IEMSCourses).filter(
            IEMSCourses.semester == request.term_id, 
            IEMSCourses.state_id == 4,
            IEMSCourses.status == 1
        )

        if request.crs_mode:
            if 3 in request.crs_mode:
                query = query.filter(IEMSCourses.tutorial == 1)
            else:
                query = query.filter(IEMSCourses.crs_mode.in_(request.crs_mode))

        courses = query.order_by(IEMSCourses.crs_code.asc()).all()

        data = [
            {
                "crs_id": 0,
                "crs_code": "Break",
                "crs_title": "Break",
                "crs_mode": 0
            }
        ]

        for course in courses:
            data.append({
                "crs_id": course.crs_id,
                "crs_code": course.crs_code,
                "crs_title": course.crs_title,
                "crs_mode": course.crs_mode
            })

        return returnSuccess(data)
    except Exception as e:
        logger.error(f"Error fetching courses: {str(e)}")
        return returnException(str(e))

@router.post("/select_batch")
def select_batch(
    request: SelectBatchRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the selected section and its child batches for the supplied courses.

    cudos_master_type_details hierarchy:
    - parent_id = 0: section
    - parent_id > 0: batch belonging to that parent section
    """

    try:
        if not request.crs_id:
            return returnSuccess([])

        if not request.crclm_id:
            return returnSuccess([])

        if not request.sec_id:
            return returnSuccess([])

        result = (
            db.query(
                CudosMapCoursetoCourseInstructor.crs_id.label("crs_id"),
                IEMSCourses.crs_code.label("crs_code"),
                IEMSCourses.crs_title.label("crs_title"),
                MasterTypeDetails.mt_details_id.label("batch_id"),
                MasterTypeDetails.mt_details_name.label("batch_name"),
                MasterTypeDetails.parent_id.label("parent_id"),
            )
            .join(
                IEMSCourses,
                IEMSCourses.crs_id
                == CudosMapCoursetoCourseInstructor.crs_id,
            )
            .join(
                MasterTypeDetails,
                or_(
                    # The section directly mapped to the course
                    MasterTypeDetails.mt_details_id
                    == CudosMapCoursetoCourseInstructor.section_id,

                    # Batches belonging to the mapped section
                    MasterTypeDetails.parent_id
                    == CudosMapCoursetoCourseInstructor.section_id,
                ),
            )
            .filter(
                CudosMapCoursetoCourseInstructor.academic_batch_id
                == request.crclm_id,

                CudosMapCoursetoCourseInstructor.crs_id.in_(
                    request.crs_id
                ),

                CudosMapCoursetoCourseInstructor.section_id.isnot(None),

                # Return the selected section and its child batches
                or_(
                    MasterTypeDetails.mt_details_id == request.sec_id,
                    MasterTypeDetails.parent_id == request.sec_id,
                ),

                MasterTypeDetails.mtd_status == 1,
            )
            .distinct()
            .order_by(
                IEMSCourses.crs_code.asc(),
                MasterTypeDetails.parent_id.asc(),
                MasterTypeDetails.mt_details_id.asc(),
            )
            .all()
        )

        data = [
            {
                "batch_id": row.batch_id,
                "batch_name": row.batch_name,
                "crs_id": row.crs_id,
                "crs_code": row.crs_code,
                "crs_title": row.crs_title,
                "parent_id": row.parent_id,
                "item_type": (
                    "section"
                    if not row.parent_id or row.parent_id == 0
                    else "batch"
                ),
            }
            for row in result
        ]

        return returnSuccess(data)

    except Exception as exc:
        logger.exception(
            "Failed to fetch sections/batches for "
            "curriculum=%s, courses=%s, section=%s",
            request.crclm_id,
            request.crs_id,
            request.sec_id,
        )
        return returnException(str(exc))
    
# @router.post("/select_batch")
# def select_batch(
#     request: SelectBatchRequest,
#     current_user: dict = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Fetch list of batches
#     Original PHP: select_batch()
#     """
#     try:
#         if not request.crs_id:
#             return returnSuccess([])

#         result = (
#         db.query(
#             CudosMapCoursetoCourseInstructor.crs_id.label("crs_id"),
#             IEMSCourses.crs_code.label("crs_code"),
#             IEMSCourses.crs_title.label("crs_title"),
#             MasterTypeDetails.parent_id.label("parent_id"),
#             MasterTypeDetails.mt_details_id.label("id"),
#             MasterTypeDetails.mt_details_name.label("name"),
#         )
#         .join(
#            MasterTypeDetails,
#            MasterTypeDetails.mt_details_id
#            == CudosMapCoursetoCourseInstructor.section_id,
#         )
#         .join(
#             IEMSCourses,
#             IEMSCourses.crs_id == CudosMapCoursetoCourseInstructor.crs_id,
#         )
#     .filter(
#         CudosMapCoursetoCourseInstructor.crs_id.in_(request.crs_id),
#         or_(
#             MasterTypeDetails.parent_id == request.sec_id,
#             MasterTypeDetails.mt_details_id == request.sec_id,
#         ),
#         MasterTypeDetails.org_type.in_([
#             "SECTION",
#             "BATCHWISE_SECTION",
#         ]),
#     )
#     .order_by(
#         IEMSCourses.crs_code,
#         MasterTypeDetails.mt_details_id,
#     )
#     .all()
# )

#         data = []
#         for batch in result:
#             data.append({
#                 "batch_id": batch.id,
#                 "batch_name": batch.name,
#                 "crs_id": batch.crs_id,
#                 "crs_code": batch.crs_code,
#                 "parent_id": batch.parent_id
#             })

#         return returnSuccess(data)
#     except Exception as e:
#         logger.error(f"Error fetching batches: {str(e)}")
#         return returnException(str(e))


@router.post("/get_edit_class_course")
def get_edit_class_course(
    request: EditClassCourseRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get list of courses and selected course for edit
    Original PHP: get_edit_class_course()
    """
    try:
        query = db.query(IEMSCourses).filter(
            IEMSCourses.crclm_term_id == request.term_id,
            IEMSCourses.state_id == 4,
            IEMSCourses.status == 1
        )

        if request.crs_mode == 3:
            query = query.filter(IEMSCourses.tutorial == 1)
        else:
            query = query.filter(IEMSCourses.crs_mode == request.crs_mode)

        courses = query.order_by(IEMSCourses.crs_code.asc()).all()

        data = [
            {
                "crs_id": 0,
                "crs_code": "Break",
                "crs_title": "Break",
                "selected": request.crs_id == 0
            }
        ]

        for course in courses:
            data.append({
                "crs_id": course.crs_id,
                "crs_code": course.crs_code,
                "crs_title": course.crs_title,
                "selected": course.crs_id == request.crs_id
            })

        return returnSuccess(data)
    except Exception as e:
        logger.error(f"Error fetching edit course: {str(e)}")
        return returnException(str(e))


# ============================================================================
# TIMETABLE GENERATION APIs
# ============================================================================

# @router.post("/generate_time_table_grid")
# def generate_time_table_grid(
#     request: GenerateTimetableRequest,
#     current_user: dict = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     """
#     Generate timetable grid
#     Original PHP: generate_time_table_grid()
#     """
#     try:
#         user_id = current_user.get("user_id")

#         # Check if tt_detail_id exists for update
#         if request.tt_detail_id:
#             # Delete existing time tables and mappings
#             db.query(LMSTimetable).filter(
#                 LMSTimetable.tt_detail_id == request.tt_detail_id
#             ).delete()
#             db.query(LMSTimetableDayMapping).filter(
#                 LMSTimetableDayMapping.tt_detail_id == request.tt_detail_id
#             ).delete()

#             # Update timetable details
#             db.query(LMSTimetableDetails).filter(
#                 LMSTimetableDetails.tt_detail_id == request.tt_detail_id
#             ).update({
#                 'tt_start_date': request.start_date,
#                 'tt_end_date': request.end_date,
#                 'tt_start_time': request.start_time,
#                 'tt_end_time': request.end_time,
#                 'lms_reg_byp_flag': request.lms_reg_byp_flag,
#                 'modified_by': user_id,
#                 'modified_date': datetime.now()
#             })
#             db.commit()

#             tt_detail = db.query(LMSTimetableDetails).filter(
#                 LMSTimetableDetails.tt_detail_id == request.tt_detail_id
#             ).first()
#         else:
#             # Create new timetable details
#             tt_detail = LMSTimetableDetails(
#                 crclm_id=request.crclm_id,
#                 crclm_term_id=request.term_id,
#                 section_id=request.sec_id,
#                 tt_start_date=request.start_date,
#                 tt_end_date=request.end_date,
#                 tt_start_time=request.start_time,
#                 tt_end_time=request.end_time,
#                 tt_time_slot_gap=5,
#                 lms_reg_byp_flag=request.lms_reg_byp_flag,
#                 created_by=user_id,
#                 modified_by=user_id,
#                 created_date=datetime.now(),
#                 modified_date=datetime.now()
#             )
#             db.add(tt_detail)
#             db.commit()
#             db.refresh(tt_detail)

#         # Get days
#         days = db.query(LMSWeekDay).order_by(LMSWeekDay.days_order).all()
#         days_array = [
#             {
#                 "day_id": d.day_id,
#                 "week_day_name": d.week_day_name
#             }
#             for d in days
#         ]

#         # Generate time slots
#         time_slots = generate_time_slots(
#             request.start_time,
#             request.end_time,
#             5
#         )

#         # Get all timetables for dropdown
#         all_tt = db.query(LMSTimetableDetails).filter(
#             LMSTimetableDetails.crclm_id == request.crclm_id,
#             LMSTimetableDetails.crclm_term_id == request.term_id,
#             LMSTimetableDetails.section_id == request.sec_id
#         ).order_by(LMSTimetableDetails.tt_detail_id.desc()).all()

#         # Build dropdown data
#         tt_options = [
#             {
#                 "tt_detail_id": None,
#                 "label": "New Timetable",
#                 "selected": False
#             }
#         ]
#         for tt in all_tt:
#             tt_options.append({
#                 "tt_detail_id": tt.tt_detail_id,
#                 "label": f"{tt.tt_start_date} to {tt.tt_end_date}",
#                 "selected": tt.tt_detail_id == tt_detail.tt_detail_id
#             })

#         # Get week days
#         week_days = get_week_days(request.start_date, request.end_date)

#         # Get existing classes if any
#         classes = db.query(LMSTimetable).filter(
#             LMSTimetable.tt_detail_id == tt_detail.tt_detail_id,
#             LMSTimetable.extra_class_flag == 0
#         ).all()

#         class_list = []
#         for cls in classes:
#             class_list.append({
#                 "time_table_id": cls.time_table_id,
#                 "tt_detail_id": cls.tt_detail_id,
#                 "day_id": cls.day_id,
#                 "week_day_name": cls.week_day_name,
#                 "crs_id": cls.crs_id,
#                 "crs_code": cls.crs_code,
#                 "class_start_time": cls.class_start_time,
#                 "class_end_time": cls.class_end_time,
#                 "extra_class_flag": cls.extra_class_flag,
#                 "batch_names": []
#             })

#         # Get distinct course IDs
#         crs_ids = []
#         if classes:
#             distinct_crs = set([c.crs_id for c in classes])
#             crs_ids = [{"crs_id": cid} for cid in distinct_crs]

#         data = {
#             'status': 1,
#             'tt_detail_id': tt_detail.tt_detail_id,
#             'tt_start_date': request.start_date,
#             'tt_end_date': request.end_date,
#             'tt_start_time': request.start_time,
#             'tt_end_time': request.end_time,
#             'tt_time_slot_gap': 5,
#             'lms_reg_byp_flag': request.lms_reg_byp_flag,
#             'tt_options': tt_options,
#             'week_days': week_days,
#             'days': days_array,
#             'time_slots': time_slots,
#             'tt_details': {
#                 'tt_detail_id': tt_detail.tt_detail_id,
#                 'tt_start_date': tt_detail.tt_start_date,
#                 'tt_end_date': tt_detail.tt_end_date,
#                 'tt_start_time': tt_detail.tt_start_time,
#                 'tt_end_time': tt_detail.tt_end_time,
#                 'lms_reg_byp_flag': tt_detail.lms_reg_byp_flag
#             },
#             'classes': class_list,
#             'crs_ids': crs_ids
#         }

#         return returnSuccess(data)
#     except Exception as e:
#         db.rollback()
#         logger.error(f"Error generating timetable: {str(e)}")
#         return returnException(str(e))


@router.post("/generate_time_table_grid")
def generate_time_table_grid(
    request: GenerateTimetableRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate timetable grid
    Original PHP: generate_time_table_grid()
    """
    try:
        user_id = current_user.get("user_id")

        # Check if tt_detail_id exists for update
        if request.tt_detail_id:
            # Delete existing time tables and mappings
            db.query(LMSTimetable).filter(
                LMSTimetable.tt_detail_id == request.tt_detail_id
            ).delete()
            db.query(LMSTimetableDayMapping).filter(
                LMSTimetableDayMapping.tt_detail_id == request.tt_detail_id
            ).delete()

            # Update timetable details - using correct field names
            db.query(LMSTimetableDetails).filter(
                LMSTimetableDetails.tt_detail_id == request.tt_detail_id
            ).update({
                'academic_batch_id': request.crclm_id,  # Changed
                'semester_id': request.term_id,         # Changed
                'section_id': request.section_id,
                'tt_start_date': request.start_date,
                'tt_end_date': request.end_date,
                'tt_start_time': request.start_time,
                'tt_end_time': request.end_time,
                'tt_time_slot_gap': '5',                # Changed to String
                'lms_reg_byp_flag': request.lms_reg_byp_flag,
                'modified_by': user_id,
                'modified_date': datetime.now()
            })
            db.commit()

            tt_detail = db.query(LMSTimetableDetails).filter(
                LMSTimetableDetails.tt_detail_id == request.tt_detail_id
            ).first()
        else:
            # Create new timetable details - using correct field names
            tt_detail = LMSTimetableDetails(
                academic_batch_id=request.academic_batch_id, 
                semester_id=request.semester_id,         
                section_id=request.section_id,
                tt_start_date=request.start_date,
                tt_end_date=request.end_date,
                tt_start_time=request.start_time,
                tt_end_time=request.end_time,
                tt_time_slot_gap='5',                # Changed to String
                lms_reg_byp_flag=request.lms_reg_byp_flag,
                created_by=user_id,
                modified_by=user_id,
                created_date=datetime.now(),
                modified_date=datetime.now()
            )
            db.add(tt_detail)
            db.commit()
            db.refresh(tt_detail)

        # Get days
        days = db.query(LMSWeekDay).order_by(LMSWeekDay.days_order).all()
        days_array = [
            {
                "day_id": d.day_id,
                "week_day_name": d.week_day_name
            }
            for d in days
        ]

        # Generate time slots
        time_slots = generate_time_slots(
            request.start_time,
            request.end_time,
            5
        )

        all_tt = db.query(LMSTimetableDetails).filter(
            LMSTimetableDetails.academic_batch_id == request.academic_batch_id,
            LMSTimetableDetails.semester_id == request.semester_id,
            LMSTimetableDetails.section_id == request.section_id,
        ).order_by(LMSTimetableDetails.tt_detail_id.desc()).all()

        # Build dropdown data
        tt_options = [
            {
                "tt_detail_id": None,
                "label": "New Timetable",
                "selected": False
            }
        ]
        for tt in all_tt:
            tt_options.append({
                "tt_detail_id": tt.tt_detail_id,
                "label": f"{tt.tt_start_date} to {tt.tt_end_date}",
                "selected": tt.tt_detail_id == tt_detail.tt_detail_id
            })

        # Get week days
        week_days = get_week_days(request.start_date, request.end_date)

        # Get existing classes if any
        classes = db.query(LMSTimetable).filter(
            LMSTimetable.tt_detail_id == tt_detail.tt_detail_id
            # LMSTimetable.extra_class_flag == 0
        ).all()

        class_list = []
        for cls in classes:
            class_list.append({
                "time_table_id": cls.time_table_id,
                "tt_detail_id": cls.tt_detail_id,
                "day_id": cls.day_id,
                "week_day_name": cls.week_day_name,
                "crs_id": cls.crs_id,
                "crs_code": cls.crs_code,
                "class_start_time": cls.class_start_time,
                "class_end_time": cls.class_end_time,
                "extra_class_flag": cls.extra_class_flag,
                "batch_names": []
            })

        # Get distinct course IDs
        crs_ids = []
        if classes:
            distinct_crs = set([c.crs_id for c in classes])
            crs_ids = [{"crs_id": cid} for cid in distinct_crs]

        data = {
            'status': 1,
            'tt_detail_id': tt_detail.tt_detail_id,
            'tt_start_date': request.start_date,
            'tt_end_date': request.end_date,
            'tt_start_time': request.start_time,
            'tt_end_time': request.end_time,
            'tt_time_slot_gap': 5,
            'lms_reg_byp_flag': request.lms_reg_byp_flag,
            'tt_options': tt_options,
            'week_days': week_days,
            'days': days_array,
            'time_slots': time_slots,
            'tt_details': {
                'tt_detail_id': tt_detail.tt_detail_id,
                'tt_start_date': tt_detail.tt_start_date,
                'tt_end_date': tt_detail.tt_end_date,
                'tt_start_time': tt_detail.tt_start_time,
                'tt_end_time': tt_detail.tt_end_time,
                'lms_reg_byp_flag': tt_detail.lms_reg_byp_flag
            },
            'classes': class_list,
            'crs_ids': crs_ids
        }

        return returnSuccess(data)
    except Exception as e:
        db.rollback()
        logger.error(f"Error generating timetable: {str(e)}")
        return returnException(str(e))

def _full_name(user) -> str:
    if not user:
        return ""

    return " ".join(
        part for part in [
            getattr(user, "title", None),
            getattr(user, "first_name", None),
            getattr(user, "last_name", None),
        ]
        if part
    ).strip()


def _unique_values(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _get_class_people_and_allocation(
    cls: LMSTimetable,
    timetable: LMSTimetableDetails,
    db: Session,
) -> dict:
    """
    Resolve batches, course owner, and course instructors for one scheduled class.

    Instructors can be mapped either to:
    - a batch, or
    - the timetable section.
    """

    batch_rows = (
        db.query(
            LMSTimetableBatchMap.batch_id,
            MasterTypeDetails.mt_details_name,
        )
        .outerjoin(
            MasterTypeDetails,
            MasterTypeDetails.mt_details_id == LMSTimetableBatchMap.batch_id,
        )
        .filter(
            LMSTimetableBatchMap.time_table_id == cls.time_table_id,
        )
        .all()
    )

    batch_ids = _unique_values([
        str(row.batch_id)
        for row in batch_rows
        if row.batch_id is not None
    ])

    batch_names = _unique_values([
        row.mt_details_name
        for row in batch_rows
        if row.mt_details_name
    ])

    # Course owner
    owner_rows = (
        db.query(IEMSUsers)
        .join(
            CudosCourseCloOwner,
            CudosCourseCloOwner.clo_owner_id == IEMSUsers.id,
        )
        .filter(CudosCourseCloOwner.crs_id == cls.crs_id)
        .all()
    )
    owner_names = _unique_values([_full_name(owner) for owner in owner_rows])

    # A course instructor may be assigned to the timetable section or a batch.
    instructor_scope_ids = [str(timetable.section_id)] + batch_ids

    instructor_rows = (
        db.query(IEMSUsers)
        .join(
            CudosMapCoursetoCourseInstructor,
            CudosMapCoursetoCourseInstructor.course_instructor_id == IEMSUsers.id,
        )
        .filter(
            CudosMapCoursetoCourseInstructor.crs_id == cls.crs_id,
            CudosMapCoursetoCourseInstructor.section_id.in_(instructor_scope_ids),
        )
        .all()
    )
    instructor_names = _unique_values([
        _full_name(instructor)
        for instructor in instructor_rows
    ])

    allocation_label = (
        ", ".join(batch_names)
        if batch_names
        else f"Section {timetable.section_id}"
    )

    return {
        "batch_ids": batch_ids,
        "batch_names": batch_names,
        "allocation_label": allocation_label,
        "course_instructor": ", ".join(instructor_names),
        "crs_owner": ", ".join(owner_names),
    }


def __schedule_class(tt_detail_id: int, db: Session) -> Dict:
    timetable = (
        db.query(LMSTimetableDetails)
        .filter(LMSTimetableDetails.tt_detail_id == tt_detail_id)
        .first()
    )

    if not timetable:
        return returnSuccess({"status": 0})

    # Include flag 0 regular classes and flag 2 copied/compensated classes.
    time_tables = (
        db.query(LMSTimetable)
        .filter(LMSTimetable.tt_detail_id == tt_detail_id)
        .order_by(
            LMSTimetable.day_id.asc(),
            LMSTimetable.class_start_time.asc(),
        )
        .all()
    )

    days = (
        db.query(LMSWeekDay)
        .order_by(LMSWeekDay.days_order.asc())
        .all()
    )

    days_array = [
        {
            "day_id": day.day_id,
            "week_day_name": day.week_day_name,
        }
        for day in days
    ]

    time_gap = int(timetable.tt_time_slot_gap or 5)

    time_slots = generate_time_slots(
        timetable.tt_start_time,
        timetable.tt_end_time,
        time_gap,
    )

    all_tt = (
        db.query(LMSTimetableDetails)
        .filter(
            LMSTimetableDetails.academic_batch_id
            == timetable.academic_batch_id,
            LMSTimetableDetails.semester_id == timetable.semester_id,
            LMSTimetableDetails.section_id == timetable.section_id,
        )
        .order_by(LMSTimetableDetails.tt_detail_id.desc())
        .all()
    )

    tt_options = [
        {
            "tt_detail_id": None,
            "label": "New Timetable",
            "selected": False,
        }
    ]

    for tt in all_tt:
        tt_options.append({
            "tt_detail_id": tt.tt_detail_id,
            "label": f"{tt.tt_start_date} to {tt.tt_end_date}",
            "selected": tt.tt_detail_id == timetable.tt_detail_id,
        })

    class_list = []

    for cls in time_tables:
        people_and_allocation = _get_class_people_and_allocation(
            cls,
            timetable,
            db,
        )

        class_list.append({
            "time_table_id": cls.time_table_id,
            "tt_detail_id": cls.tt_detail_id,
            "day_id": cls.day_id,
            "week_day_name": cls.week_day_name,
            "crs_id": cls.crs_id,
            "crs_code": cls.crs_code,
            "class_start_time": cls.class_start_time,
            "class_end_time": cls.class_end_time,
            "extra_class_flag": cls.extra_class_flag,
            "batch_ids": people_and_allocation["batch_ids"],
            "batch_names": people_and_allocation["batch_names"],
            "allocation_label": people_and_allocation["allocation_label"],
            "course_instructor": people_and_allocation["course_instructor"],
            "crs_owner": people_and_allocation["crs_owner"],
        })

    distinct_course_ids = sorted({
        row.crs_id
        for row in time_tables
        if row.crs_id is not None
    })

    data = {
        "status": 1,
        "tt_detail_id": timetable.tt_detail_id,
        "tt_start_date": timetable.tt_start_date,
        "tt_end_date": timetable.tt_end_date,
        "tt_start_time": timetable.tt_start_time,
        "tt_end_time": timetable.tt_end_time,
        "tt_time_slot_gap": time_gap,
        "lms_reg_byp_flag": timetable.lms_reg_byp_flag,
        "tt_options": tt_options,
        "week_days": get_week_days(
            timetable.tt_start_date,
            timetable.tt_end_date,
        ),
        "days": days_array,
        "time_slots": time_slots,
        "tt_details": {
            "tt_detail_id": timetable.tt_detail_id,
            "tt_start_date": timetable.tt_start_date,
            "tt_end_date": timetable.tt_end_date,
            "tt_start_time": timetable.tt_start_time,
            "tt_end_time": timetable.tt_end_time,
            "tt_time_slot_gap": time_gap,
            "lms_reg_byp_flag": timetable.lms_reg_byp_flag,
        },
        "classes": class_list,
        "crs_ids": [{"crs_id": course_id} for course_id in distinct_course_ids],
    }

    return returnSuccess(data)

@router.post("/get_details")
def get_details(
    tt_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        if not tt_id:
            return returnSuccess({"status": -1})

        return __schedule_class(tt_id, db)
    except Exception as e:
        logger.error(f"Error fetching details: {str(e)}")
        return returnException(str(e))
    
@router.post("/get_schedule_class")
def get_schedule_class(
    request: TimetableFilterRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        if not request.section_id:
            return returnSuccess({"status": -1})

        timetable = (
            db.query(LMSTimetableDetails)
            .filter(
                LMSTimetableDetails.academic_batch_id
                == request.academic_batch_id,
                LMSTimetableDetails.semester_id == request.semester_id,
                LMSTimetableDetails.section_id == request.section_id,
            )
            .order_by(LMSTimetableDetails.tt_detail_id.desc())
            .first()
        )

        if not timetable:
            return returnSuccess({"status": 0})

        return __schedule_class(timetable.tt_detail_id, db)

    except Exception as exc:
        logger.exception("Error fetching schedule")
        return returnException(str(exc))


@router.post("/get_timetable_details")
def get_timetable_details(
    request: TimetableDetailsRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return __schedule_class(request.tt_detail_id, db)

    except Exception as exc:
        logger.exception("Error fetching timetable details")
        return returnException(str(exc))
    

# @router.post("/get_schedule_class")
# def get_schedule_class(
#     request: TimetableFilterRequest,
#     current_user: dict = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     try:
#         if not request.section_id:
#             return returnSuccess({"status": -1})

#         # Get timetable details - using correct field names
#         tt_details = db.query(LMSTimetableDetails).filter(
#             LMSTimetableDetails.academic_batch_id == request.academic_batch_id,  # Now this works
#             LMSTimetableDetails.semester_id == request.semester_id,         # Now this works
#             LMSTimetableDetails.section_id == request.section_id
#         ).order_by(LMSTimetableDetails.tt_detail_id.desc()).first()

#         if not tt_details:
#             return returnSuccess({"status": 0})

#         return __schedule_class(tt_details.tt_detail_id, db)
#     except Exception as e:
#         logger.error(f"Error fetching schedule: {str(e)}")
#         return returnException(str(e))

# @router.post("/get_details")
# def get_details(
#     tt_id: int,
#     current_user: dict = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     try:
#         if not tt_id:
#             return returnSuccess({"status": -1})

#         return __schedule_class(tt_id, db)
#     except Exception as e:
#         logger.error(f"Error fetching details: {str(e)}")
#         return returnException(str(e))


# def __schedule_class(tt_detail_id: int, db: Session) -> Dict:
#     tt_details = db.query(LMSTimetableDetails).filter(
#         LMSTimetableDetails.tt_detail_id == tt_detail_id
#     ).first()

#     if not tt_details:
#         return returnSuccess({"status": 0})

#     # Get time tables
#     time_tables = db.query(LMSTimetable).filter(
#         LMSTimetable.tt_detail_id == tt_detail_id
#         # LMSTimetable.extra_class_flag == 0
#     ).all()

#     # Get days
#     days = db.query(LMSWeekDay).order_by(LMSWeekDay.days_order).all()
#     days_array = [
#         {
#             "day_id": d.day_id,
#             "week_day_name": d.week_day_name
#         }
#         for d in days
#     ]

#     # Generate time slots
#     time_slot_gap = int(tt_details.tt_time_slot_gap or 5)

#     time_slots = generate_time_slots(
#        tt_details.tt_start_time,
#        tt_details.tt_end_time,
#        time_slot_gap,
#     )

#     # Get all timetables for dropdown
#     all_tt = db.query(LMSTimetableDetails).filter(
#         LMSTimetableDetails.academic_batch_id == tt_details.academic_batch_id,
#         LMSTimetableDetails.semester_id == tt_details.semester_id,
#         LMSTimetableDetails.section_id == tt_details.section_id
#     ).order_by(LMSTimetableDetails.tt_detail_id.desc()).all()

#     # Build dropdown data
#     tt_options = [
#         {
#             "tt_detail_id": None,
#             "label": "New Timetable",
#             "selected": False
#         }
#     ]
#     for tt in all_tt:
#         tt_options.append({
#             "tt_detail_id": tt.tt_detail_id,
#             "label": f"{tt.tt_start_date} to {tt.tt_end_date}",
#             "selected": tt.tt_detail_id == tt_details.tt_detail_id
#         })

#     # Build class data
#     class_list = []
#     for cls in time_tables:
#         # Get batch names
#         batches = db.query(LMSTimetableBatchMap).filter(
#             LMSTimetableBatchMap.time_table_id == cls.time_table_id
#         ).all()

#         batch_names = []
#         for batch in batches:
#             # Get batch name from master_type_details
#             batch_data = db.execute(
#                 "SELECT mt_details_name FROM master_type_details WHERE mt_details_id = :batch_id",
#                 {"batch_id": batch.batch_id}
#             ).first()
#             if batch_data:
#                 batch_names.append(batch_data.mt_details_name)

#         class_list.append({
#             "time_table_id": cls.time_table_id,
#             "tt_detail_id": cls.tt_detail_id,
#             "day_id": cls.day_id,
#             "week_day_name": cls.week_day_name,
#             "crs_id": cls.crs_id,
#             "crs_code": cls.crs_code,
#             "class_start_time": cls.class_start_time,
#             "class_end_time": cls.class_end_time,
#             "extra_class_flag": cls.extra_class_flag,
#             "batch_names": batch_names
#         })

#     # Get distinct course IDs
#     crs_ids = []
#     if time_tables:
#         distinct_crs = set([c.crs_id for c in time_tables])
#         crs_ids = [{"crs_id": cid} for cid in distinct_crs]

#     data = {
#         'status': 1,
#         'tt_detail_id': tt_details.tt_detail_id,
#         'tt_start_date': tt_details.tt_start_date,
#         'tt_end_date': tt_details.tt_end_date,
#         'tt_start_time': tt_details.tt_start_time,
#         'tt_end_time': tt_details.tt_end_time,
#         'tt_time_slot_gap': time_slot_gap,
#         'lms_reg_byp_flag': tt_details.lms_reg_byp_flag,
#         'tt_options': tt_options,
#         'week_days': get_week_days(tt_details.tt_start_date, tt_details.tt_end_date),
#         'days': days_array,
#         'time_slots': time_slots,
#         'tt_details': {
#             'tt_detail_id': tt_details.tt_detail_id,
#             'tt_start_date': tt_details.tt_start_date,
#             'tt_end_date': tt_details.tt_end_date,
#             'tt_start_time': tt_details.tt_start_time,
#             'tt_end_time': tt_details.tt_end_time,
#             'lms_reg_byp_flag': tt_details.lms_reg_byp_flag
#         },
#         'classes': class_list,
#         'crs_ids': crs_ids
#     }

#     return returnSuccess(data)


@router.post("/check_time_table_date_exist")
def check_time_table_date_exist(
    data: Dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check if timetable dates already exist
    Original PHP: check_time_table_date_exist()
    """
    try:
        count = db.query(LMSTimetableDetails).filter(
            LMSTimetableDetails.academic_batch_id == data.get('crclm_id'),
            LMSTimetableDetails.semester_id == data.get('term_id'),
            LMSTimetableDetails.section_id == data.get('section_id'),
            LMSTimetableDetails.tt_start_date == data.get('tt_start_date')
        ).count()

        return returnSuccess({"tt_count": count})
    except Exception as e:
        logger.error(f"Error checking date exists: {str(e)}")
        return returnException(str(e))


@router.post("/update_tt")
def update_tt(
    data: Dict,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update timetable details
    Original PHP: update_tt()
    """
    try:
        user_id = current_user.get("user_id")
        tt_detail_id = data.get('edit_tt_detail_id')

        update_data = {
            'modified_by': user_id,
            'modified_date': datetime.now()
        }

        start_date = data.get('edit_start_date')
        end_date = data.get('edit_end_date')
        if start_date and end_date:
            update_data['tt_start_date'] = start_date
            update_data['tt_end_date'] = end_date

        start_time = data.get('edit_tt_start_time')
        end_time = data.get('edit_tt_end_time')
        if start_time and end_time:
            update_data['tt_start_time'] = start_time
            update_data['tt_end_time'] = end_time

        result = db.query(LMSTimetableDetails).filter(
            LMSTimetableDetails.tt_detail_id == tt_detail_id
        ).update(update_data)
        db.commit()

        if result > 0:
            return returnSuccess({"status": True}, "Timetable updated successfully")
        else:
            return returnException("Failed to update timetable")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating timetable: {str(e)}")
        return returnException(str(e))


@router.post("/delete_tt")
def delete_tt(
    request: DeleteTimetableRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete timetable
    Original PHP: delete_tt()
    """
    try:
        # Verify password (simplified - in production, validate properly)
        # For now, just proceed with deletion

        # Delete day mappings
        db.query(LMSTimetableDayMapping).filter(
            LMSTimetableDayMapping.tt_detail_id == request.del_tt_detail_id
        ).delete()

        # Delete batch mappings
        db.query(LMSTimetableBatchMap).filter(
            LMSTimetableBatchMap.tt_detail_id == request.del_tt_detail_id
        ).delete()

        # Delete time tables
        db.query(LMSTimetable).filter(
            LMSTimetable.tt_detail_id == request.del_tt_detail_id
        ).delete()

        # Delete timetable details
        result = db.query(LMSTimetableDetails).filter(
            LMSTimetableDetails.tt_detail_id == request.del_tt_detail_id
        ).delete()

        db.commit()

        if result > 0:
            return returnSuccess({"status": True}, "Timetable deleted successfully")
        else:
            return returnException("Failed to delete timetable")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting timetable: {str(e)}")
        return returnException(str(e))


# ============================================================================
# CLASS MANAGEMENT APIs
# ============================================================================

@router.post("/save_classes")
def save_classes(
    request: ScheduleClassRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add timetable weekly class
    Original PHP: save_classes()
    """
    try:
        user_id = current_user.get("user_id")

        tt_detail = db.query(LMSTimetableDetails).filter(
            LMSTimetableDetails.tt_detail_id == request.tt_detail_id
        ).first()

        if not tt_detail:
            return returnException("Timetable not found")

        # Get days mapping
        days_map = {d.week_day_name: d.day_id for d in db.query(LMSWeekDay).all()}

        # Parse batch IDs
        batch_ids = {}
        if request.batch:
            for batch_str in request.batch:
                if '|' in batch_str:
                    parts = batch_str.split('|')
                    crs_id = int(parts[0])
                    batch_id = int(parts[1])
                    if crs_id not in batch_ids:
                        batch_ids[crs_id] = []
                    batch_ids[crs_id].append(batch_id)

        success = True
        for crs_id in request.crs_id:
            course = db.query(IEMSCourses).filter(IEMSCourses.crs_id == crs_id).first()
            crs_code = course.crs_code if course else 'Break'

            for i, day in enumerate(request.day_val_array):
                # Insert into time_table
                cls = LMSTimetable(
                    tt_detail_id=request.tt_detail_id,
                    day_id=days_map[day],
                    week_day_name=day,
                    crs_id=crs_id,
                    crs_code=crs_code,
                    class_start_time=request.class_start_time_array[i],
                    class_end_time=request.class_end_time_array[i],
                    created_by=user_id,
                    modified_by=user_id,
                    created_date=datetime.now(),
                    modified_date=datetime.now()
                )
                db.add(cls)
                db.flush()
                time_table_id = cls.time_table_id

                # Insert batch mappings
                if crs_id in batch_ids and batch_ids[crs_id]:
                    for batch_id in batch_ids[crs_id]:
                        batch_map = LMSTimetableBatchMap(
                            time_table_id=time_table_id,
                            tt_detail_id=request.tt_detail_id,
                            batch_id=batch_id,
                            crs_id=crs_id,
                            created_by=user_id,
                            created_date=datetime.now()
                        )
                        db.add(batch_map)

                # Generate day mappings for all dates in range
                date_range = get_date_range(tt_detail.tt_start_date, tt_detail.tt_end_date)
                for date_str in date_range:
                    if datetime.strptime(date_str, '%d-%m-%Y').strftime('%A') == day:
                        day_map = LMSTimetableDayMapping(
                            time_table_id=time_table_id,
                            tt_detail_id=request.tt_detail_id,
                            day_id=days_map[day],
                            week_day_name=day,
                            class_date=date_str,
                            created_by=user_id,
                            created_date=datetime.now()
                        )
                        db.add(day_map)

        db.commit()
        return returnSuccess({"status": "success"}, "Classes scheduled successfully")
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving classes: {str(e)}")
        return returnException(str(e))


@router.post("/update_class")
def update_class(
    request: UpdateClassRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update class
    Original PHP: update_class()
    """
    try:
        course = db.query(IEMSCourses).filter(IEMSCourses.crs_id == request.crs_id).first()
        crs_code = course.crs_code if course else 'Break'

        result = db.query(LMSTimetable).filter(
            LMSTimetable.time_table_id == request.time_table_id
        ).update({
            'crs_id': request.crs_id,
            'crs_code': crs_code,
            'class_start_time': request.class_start_time,
            'class_end_time': request.class_end_time,
            'modified_date': datetime.now()
        })
        db.commit()

        if result > 0:
            return returnSuccess({"status": True}, "Class updated successfully")
        else:
            return returnException("Failed to update class")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating class: {str(e)}")
        return returnException(str(e))


@router.post("/delete_class")
def delete_class(
    time_table_id: int,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete class from timetable
    Original PHP: delete_class()
    """
    try:
        # Get timetable details
        cls = db.query(LMSTimetable).filter(
            LMSTimetable.time_table_id == time_table_id
        ).first()

        if not cls:
            return returnException("Class not found")

        # Delete batch mappings
        db.query(LMSTimetableBatchMap).filter(
            LMSTimetableBatchMap.time_table_id == time_table_id
        ).delete()

        # Delete day mappings
        db.query(LMSTimetableDayMapping).filter(
            LMSTimetableDayMapping.time_table_id == time_table_id
        ).delete()

        # Delete timetable entry
        result = db.query(LMSTimetable).filter(
            LMSTimetable.time_table_id == time_table_id
        ).delete()

        db.commit()

        if result > 0:
            return returnSuccess({"status": True}, "Class deleted successfully")
        else:
            return returnException("Failed to delete class")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting class: {str(e)}")
        return returnException(str(e))


@router.post("/check_overlap_classes")
def check_overlap_classes(
    request: CheckOverlapRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check overlapping of classes
    Original PHP: check_overlap_classes()
    """
    try:
        crs_ids = request.crs_id
        crs_ids_str = ','.join(str(c) for c in crs_ids) if crs_ids else ''

        result = {
            'class_overlap_day': '',
            'class_overlap_time': '',
            'course': '',
            'faculty_name': '',
            'another_class': ''
        }

        if not crs_ids_str:
            return returnSuccess(result)

        # Check for overlapping classes
        overlaps = db.query(LMSTimetable).filter(
            LMSTimetable.tt_detail_id == request.tt_detail_id,
            LMSTimetable.crs_id.in_(crs_ids),
            LMSTimetable.week_day_name == request.day
        ).all()

        for overlap in overlaps:
            if overlap.week_day_name == request.day:
                result['class_overlap_day'] = request.day
                result['class_overlap_time'] = f"{overlap.class_start_time}-{overlap.class_end_time}"
                course = db.query(IEMSCourses).filter(IEMSCourses.crs_id == overlap.crs_id).first()
                result['course'] = f"{course.crs_code} {course.crs_title}" if course else ''
                break

        # Check faculty overlap
        if not result['course']:
            faculty_overlaps = db.execute(
                """
                SELECT tt.*, CONCAT(c.crs_code, ' ', c.crs_title) as crs_title,
                       mcci.course_instructor_id,
                       CONCAT(u.first_name, ' ', u.last_name) AS faculty_name
                FROM lms_tt_time_table AS tt 
                JOIN lms_tt_time_table_details AS ttd ON tt.tt_detail_id = ttd.tt_detail_id
                LEFT JOIN course AS c ON c.crs_id = tt.crs_id
                LEFT JOIN map_courseto_course_instructor AS mcci 
                    ON tt.crs_id = mcci.crs_id AND mcci.section_id = ttd.section_id
                LEFT JOIN users AS u ON u.id = mcci.course_instructor_id
                WHERE mcci.course_instructor_id IN (
                    SELECT course_instructor_id 
                    FROM map_courseto_course_instructor 
                    WHERE crs_id IN ({})
                )
                AND tt.crs_id IN ({})
                AND ttd.tt_start_date = :start_date
                AND ttd.tt_end_date = :end_date
                AND TIME_FORMAT(tt.class_start_time, '%T') = TIME_FORMAT(:start_time, '%T')
                AND TIME_FORMAT(tt.class_end_time, '%T') = TIME_FORMAT(:end_time, '%T')
                """.format(crs_ids_str, crs_ids_str),
                {
                    "start_date": request.start_date,
                    "end_date": request.end_date,
                    "start_time": request.class_start_time,
                    "end_time": request.class_end_time
                }
            ).fetchall()

            for fo in faculty_overlaps:
                if fo.week_day_name == request.day:
                    result['class_overlap_day'] = request.day
                    result['class_overlap_time'] = f"{fo.class_start_time}-{fo.class_end_time}"
                    result['course'] = fo.crs_title
                    result['faculty_name'] = fo.faculty_name
                    break

        return returnSuccess(result)
    except Exception as e:
        logger.error(f"Error checking overlap: {str(e)}")
        return returnException(str(e))


# ============================================================================
# COMPENSATE CLASS APIs
# ============================================================================

@router.post("/compensate_class")
def compensate_class(
    request: CompensateClassRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Compensate class from one day to another
    Original PHP: compensate_class()
    """
    try:
        user_id = current_user.get("user_id")
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        from_day = days[request.from_val - 1]
        to_day = days[request.to_val - 1]

        # Get current week dates
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        from_date = (start_of_week + timedelta(days=request.from_val - 1)).strftime('%d-%m-%Y')
        to_date = (start_of_week + timedelta(days=request.to_val - 1)).strftime('%d-%m-%Y')

        # Get classes from source day
        classes = db.query(LMSTimetable).filter(
            LMSTimetable.tt_detail_id == request.comp_tt_detail_id,
            LMSTimetable.week_day_name == from_day
            # LMSTimetable.extra_class_flag == 0
        ).all()

        if not classes:
            return returnException("No classes to copy")

        # Check if classes already exist on target day
        existing = db.query(LMSTimetable).filter(
            LMSTimetable.tt_detail_id == request.comp_tt_detail_id,
            LMSTimetable.week_day_name == to_day
        ).first()

        if existing and request.confirm == 0:
            return returnSuccess({
                "popup": True,
                "message": "Classes already exist on target day. Continue?"
            })

        # Copy classes
        records_created = 0
        for cls in classes:
            # Check if this specific class already exists on target day
            existing_class = db.query(LMSTimetable).filter(
                LMSTimetable.tt_detail_id == request.comp_tt_detail_id,
                LMSTimetable.week_day_name == to_day,
                LMSTimetable.crs_id == cls.crs_id,
                LMSTimetable.class_start_time == cls.class_start_time,
                LMSTimetable.class_end_time == cls.class_end_time
            ).first()

            if existing_class:
                continue

            new_class = LMSTimetable(
                tt_detail_id=cls.tt_detail_id,
                day_id=request.to_val,
                week_day_name=to_day,
                crs_id=cls.crs_id,
                crs_code=cls.crs_code,
                class_start_time=cls.class_start_time,
                class_end_time=cls.class_end_time,
                extra_class_flag=2,  # Copy class flag
                created_by=user_id,
                created_date=datetime.now()
            )
            db.add(new_class)
            db.flush()

            # Copy batch mappings
            batches = db.query(LMSTimetableBatchMap).filter(
                LMSTimetableBatchMap.time_table_id == cls.time_table_id
            ).all()
            for batch in batches:
                new_batch = LMSTimetableBatchMap(
                    time_table_id=new_class.time_table_id,
                    tt_detail_id=request.comp_tt_detail_id,
                    batch_id=batch.batch_id,
                    crs_id=batch.crs_id,
                    created_by=user_id,
                    created_date=datetime.now()
                )
                db.add(new_batch)

            # Copy day mapping
            day_map = LMSTimetableDayMapping(
                time_table_id=new_class.time_table_id,
                tt_detail_id=request.comp_tt_detail_id,
                day_id=request.to_val,
                week_day_name=to_day,
                class_date=to_date,
                extra_class_flag=2,
                created_by=user_id,
                created_date=datetime.now()
            )
            db.add(day_map)
            records_created += 1

        db.commit()
        return returnSuccess({
            "status": True,
            "records_created": records_created
        }, "Classes compensated successfully")
    except Exception as e:
        db.rollback()
        logger.error(f"Error compensating class: {str(e)}")
        return returnException(str(e))


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def generate_time_slots(start_time: str, end_time: str, time_gap: int) -> List[str]:
    """
    Generate time slots between start and end time
    Original PHP: generate_time_slots()
    """
    slots = []
    current = datetime.strptime(start_time, '%I:%M %p')
    end = datetime.strptime(end_time, '%I:%M %p')

    while current <= end:
        slots.append(current.strftime('%I:%M %p'))
        current += timedelta(minutes=time_gap)

    return slots


def get_week_days(startdate: str, enddate: str) -> List[str]:
    """
    Get names of week days from start & end date without duplicates
    Original PHP: get_week_days()
    """
    start = datetime.strptime(startdate, '%d-%m-%Y')
    end = datetime.strptime(enddate, '%d-%m-%Y')

    days = []
    current = start
    while current <= end and len(days) < 7:
        day_name = current.strftime('%A')
        if day_name not in days:
            days.append(day_name)
        current += timedelta(days=1)

    return days


def get_date_range(start_date: str, end_date: str) -> List[str]:
    """
    Get all dates between start and end date
    Original PHP: get_date_range()
    """
    start = datetime.strptime(start_date, '%d-%m-%Y')
    end = datetime.strptime(end_date, '%d-%m-%Y')

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime('%d-%m-%Y'))
        current += timedelta(days=1)

    return dates

@router.post("/reset_timetable_date")
def reset_timetable_date(
    request: ResetTimetableDateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        timetable = db.query(LMSTimetableDetails).filter(
            LMSTimetableDetails.tt_detail_id == request.tt_detail_id
        ).first()

        if not timetable:
            return returnException("Timetable not found")

        start_date = datetime.strptime(
            timetable.tt_start_date, "%d-%m-%Y"
        ).date()
        new_end_date = datetime.strptime(
            request.end_date, "%d-%m-%Y"
        ).date()

        if new_end_date < start_date:
            return returnException("End date cannot be before start date")

        # Keep only dated class entries inside the new range.
        mappings = db.query(LMSTimetableDayMapping).filter(
            LMSTimetableDayMapping.tt_detail_id == timetable.tt_detail_id
        ).all()

        deleted_count = 0
        existing_mappings = set()

        for mapping in mappings:
            class_date = datetime.strptime(
                mapping.class_date, "%d-%m-%Y"
            ).date()

            if class_date < start_date or class_date > new_end_date:
                db.delete(mapping)
                deleted_count += 1
            else:
                existing_mappings.add((
                    mapping.time_table_id,
                    mapping.class_date,
                ))

        # Only regular weekly classes recur when extending the timetable.
        weekly_classes = db.query(LMSTimetable).filter(
            LMSTimetable.tt_detail_id == timetable.tt_detail_id,
            LMSTimetable.extra_class_flag == 0,
        ).all()

        created_count = 0
        cursor = start_date

        while cursor <= new_end_date:
            weekday = cursor.strftime("%A")
            date_text = cursor.strftime("%d-%m-%Y")

            for weekly_class in weekly_classes:
                key = (weekly_class.time_table_id, date_text)

                if (
                    weekly_class.week_day_name == weekday
                    and key not in existing_mappings
                ):
                    db.add(LMSTimetableDayMapping(
                        time_table_id=weekly_class.time_table_id,
                        tt_detail_id=timetable.tt_detail_id,
                        day_id=weekly_class.day_id,
                        week_day_name=weekday,
                        class_date=date_text,
                        extra_class_flag=0,
                        created_by=current_user.get("user_id"),
                        created_date=datetime.now(),
                    ))
                    created_count += 1

            cursor += timedelta(days=1)

        timetable.tt_end_date = request.end_date
        timetable.modified_by = current_user.get("user_id")
        timetable.modified_date = datetime.now()

        db.commit()

        return returnSuccess({
            "status": True,
            "created_count": created_count,
            "deleted_count": deleted_count,
        }, "Timetable dates reset successfully")

    except Exception as error:
        db.rollback()
        logger.error(f"Error resetting timetable dates: {error}")
        return returnException(str(error))

@router.post("/export_timetable_pdf")
def export_timetable_pdf(
    request: ExportTimetableRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        timetable = db.query(LMSTimetableDetails).filter(
            LMSTimetableDetails.tt_detail_id == request.expo_tt_detail_id
        ).first()

        if not timetable:
            return returnException("Timetable not found")

        classes = db.query(LMSTimetable).filter(
            LMSTimetable.tt_detail_id == timetable.tt_detail_id
        ).all()

        weekdays = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        def time_to_minutes(value: str) -> int:
            if not value:
                return 0

            for time_format in ("%I:%M %p", "%H:%M"):
                try:
                    parsed = datetime.strptime(value.strip(), time_format)
                    return parsed.hour * 60 + parsed.minute
                except ValueError:
                    continue

            return 0

        # Each unique start/end range becomes one PDF column.
        time_slots = sorted(
            {
                (item.class_start_time, item.class_end_time)
                for item in classes
                if item.class_start_time and item.class_end_time
            },
            key=lambda slot: time_to_minutes(slot[0]),
        )

        # A cell can contain multiple courses if they share the same day/time.
        schedule_map: dict[tuple[str, str, str], list[str]] = {}

        for item in classes:
            if not item.class_start_time or not item.class_end_time:
                continue

            key = (
                item.week_day_name,
                item.class_start_time,
                item.class_end_time,
            )

            schedule_map.setdefault(key, []).append(
                item.crs_code or "-"
            )

        rows = [[
            "Days",
            *[
                f"{start_time} to\n{end_time}"
                for start_time, end_time in time_slots
            ],
        ]]

        for day in weekdays:
            row = [day]

            for start_time, end_time in time_slots:
                course_codes = schedule_map.get(
                    (day, start_time, end_time),
                    [],
                )
                row.append("\n".join(course_codes))

            rows.append(row)

        output = BytesIO()

        document = SimpleDocTemplate(
            output,
            pagesize=landscape(A4),
            leftMargin=28,
            rightMargin=28,
            topMargin=28,
            bottomMargin=28,
        )

        styles = getSampleStyleSheet()

        page_width = landscape(A4)[0]
        available_width = page_width - 56
        day_column_width = 1.2 * inch
        time_column_width = (
            (available_width - day_column_width)
            / max(len(time_slots), 1)
        )

        timetable_table = Table(
            rows,
            colWidths=(
                [day_column_width]
                + [time_column_width] * len(time_slots)
            ),
            repeatRows=1,
        )

        timetable_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#f1f5f9")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))

        document.build([
            Paragraph("Timetable", styles["Title"]),
            Spacer(1, 8),
            Paragraph(
                (
                    f"Period: {timetable.tt_start_date} "
                    f"to {timetable.tt_end_date}"
                ),
                styles["Normal"],
            ),
            Spacer(1, 16),
            timetable_table,
        ])

        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="timetable_{timetable.tt_detail_id}.pdf"'
                )
            },
        )

    except Exception as error:
        logger.error(f"Error exporting timetable PDF: {error}")
        return returnException(str(error))