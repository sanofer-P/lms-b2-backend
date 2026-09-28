from datetime import datetime
from html import unescape
from io import BytesIO
import re
from xml.sax.saxutils import escape

from fastapi import (
    APIRouter,
    Depends
)
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

from app.core.database import get_db

from app.utils.auth_helper import (
    get_current_user
)

from app.utils.http_return_helper import (
    returnSuccess,
    returnException
)

from app.db.models import (

    IEMSCourses,
    LMSIssuesObservations,
    LMSIssuesObservationsHistory,

    IEMStudents,
    IEMSemester,
    IEMSAcademicBatch,
    IEMSUsers,
    IEMOrganisation,
    IEMSDepartment,
    CudosMapCoursetoStudent
)

from .lms_issues_observations_report_schema import *

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

        student = db.query(
            IEMStudents
        ).filter(
            IEMStudents.usno == student_usn
        ).first()

        if not student:

            return returnException(
                "Student not found."
            )

        result = {

            "student_id":
                student.student_id,

            "student_name":
                student.name,

            "student_usn":
                student.usno,

            "academic_batch_id":
                student.academic_batch_id,

            "semester_id":
                student.current_semester,

            "email":
                student.email,

            "mobile":
                student.mobile
        }

        return returnSuccess(result)

    except Exception as e:

        return returnException(str(e))
    
    # ==========================================================
# GET ALL REPORTS OF STUDENT
# ==========================================================
@router.get("/get_issue_observations/{student_id}")
def get_issue_observations(
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

        for row in reports:

            mentor = db.query(
                IEMSUsers
            ).filter(
                IEMSUsers.id ==
                row.mentor_users_id
            ).first()

            result.append({

                "lms_isnob_id":
                    row.lms_isnob_id,

                "report_title":
                    row.report_title,

                "counselling_date":
                    row.counselling_date,

                "mentor_name":
                    mentor.first_name if mentor else "",

                "mentor_status":
                    row.mentor_status,

                "mentee_status":
                    row.mentee_status,

                "parent_guardian_status":
                    row.parent_guardian_status
            })

        return returnSuccess(result)

    except Exception as e:

        return returnException(str(e))
    
    # ==========================================================
# GET REPORT DETAILS
# ==========================================================
@router.get("/get_issue_observation/{lms_isnob_id}")
def get_issue_observation(
    lms_isnob_id: int,
    db: Session = Depends(get_db)
):

    try:

        report = db.query(
            LMSIssuesObservations
        ).filter(
            LMSIssuesObservations.lms_isnob_id ==
            lms_isnob_id,

            LMSIssuesObservations.is_deleted == 0
        ).first()

        if not report:

            return returnException(
                "Report not found."
            )

        result = {

            "lms_isnob_id":
                report.lms_isnob_id,

            "academic_batch_id":
                report.academic_batch_id,

            "semester_id":
                report.semester_id,

            "ssd_id":
                report.ssd_id,

            "student_usn":
                report.student_usn,

            "report_title":
                report.report_title,

            "counselling_date":
                report.counselling_date,

            "mentor_users_id":
                report.mentor_users_id,

            "purpose_of_meeting_desc":
                report.purpose_of_meeting_desc,

            "observation_desc":
                report.observation_desc,

            "comm_parent_flag":
                report.comm_parent_flag,

            "comm_high_auth_flag":
                report.comm_high_auth_flag,

            "mentor_status":
                report.mentor_status,

            "mentee_status":
                report.mentee_status,

            "parent_guardian_status":
                report.parent_guardian_status,

            "created_date":
                report.created_date
        }

        return returnSuccess(result)

    except Exception as e:

        return returnException(str(e))
    
    # ==========================================================
# SAVE ISSUE & OBSERVATION REPORT
# ==========================================================
@router.post("/save_issue_observation")
def save_issue_observation(
    req: IssueObservationCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    try:

        # ----------------------------------------------
        # Validate Student
        # ----------------------------------------------
        student = db.query(
            IEMStudents
        ).filter(
            IEMStudents.student_id == req.ssd_id
        ).first()

        if not student:

            return returnException(
                "Student not found."
            )

        # ----------------------------------------------
        # Validate Academic Batch
        # ----------------------------------------------
        batch = db.query(
            IEMSAcademicBatch
        ).filter(
            IEMSAcademicBatch.academic_batch_id ==
            req.academic_batch_id
        ).first()

        if not batch:

            return returnException(
                "Invalid Academic Batch."
            )

        # ----------------------------------------------
        # Validate Semester
        # ----------------------------------------------
        semester = db.query(
            IEMSemester
        ).filter(
            IEMSemester.semester_id ==
            req.semester_id
        ).first()

        if not semester:

            return returnException(
                "Invalid Semester."
            )

        # ----------------------------------------------
        # Validate Mentor
        # ----------------------------------------------
        mentor = db.query(
            IEMSUsers
        ).filter(
            IEMSUsers.id ==
            req.mentor_users_id
        ).first()

        if not mentor:

            return returnException(
                "Invalid Mentor."
            )

        # ----------------------------------------------
        # Create Report
        # ----------------------------------------------
        report = LMSIssuesObservations(

            academic_batch_id=req.academic_batch_id,

            semester_id=req.semester_id,

            ssd_id=req.ssd_id,

            student_usn=req.student_usn,

            report_title=req.report_title,

            counselling_date=req.counselling_date,

            mentor_users_id=req.mentor_users_id,

            purpose_of_meeting_desc=req.purpose_of_meeting_desc,

            observation_desc=req.observation_desc,

            comm_parent_flag=req.comm_parent_flag,

            comm_high_auth_flag=req.comm_high_auth_flag,

            mentor_status=req.mentor_status,

            mentee_status=req.mentee_status,

            parent_guardian_status=req.parent_guardian_status,

            created_by=current_user["user_id"]
        )

        db.add(report)

        db.commit()

        db.refresh(report)

        return returnSuccess({

            "lms_isnob_id":
                report.lms_isnob_id,

            "message":
                "Issue & Observation Report saved successfully."
        })

    except Exception as e:

        db.rollback()

        return returnException(
            str(e)
        )
# ==========================================================
# UPDATE ISSUE & OBSERVATION REPORT
# ==========================================================
@router.put("/update_issue_observation/{lms_isnob_id}")
def update_issue_observation(

    lms_isnob_id: int,

    req: IssueObservationUpdate,

    db: Session = Depends(get_db),

    current_user: dict = Depends(get_current_user)

):

    try:

        report = db.query(
            LMSIssuesObservations
        ).filter(
            LMSIssuesObservations.lms_isnob_id ==
            lms_isnob_id,

            LMSIssuesObservations.is_deleted == 0
        ).first()

        if not report:

            return returnException(
                "Issue & Observation Report not found."
            )

        # ----------------------------------------------
        # Update only provided fields
        # ----------------------------------------------

        if req.report_title is not None:

            report.report_title = req.report_title

        if req.counselling_date is not None:

            report.counselling_date = req.counselling_date

        if req.purpose_of_meeting_desc is not None:

            report.purpose_of_meeting_desc = \
                req.purpose_of_meeting_desc

        if req.observation_desc is not None:

            report.observation_desc = \
                req.observation_desc

        if req.comm_parent_flag is not None:

            report.comm_parent_flag = \
                req.comm_parent_flag

        if req.comm_high_auth_flag is not None:

            report.comm_high_auth_flag = \
                req.comm_high_auth_flag

        if req.mentor_status is not None:

            report.mentor_status = \
                req.mentor_status

        if req.mentee_status is not None:

            report.mentee_status = \
                req.mentee_status

        if req.parent_guardian_status is not None:

            report.parent_guardian_status = \
                req.parent_guardian_status

        report.modified_by = current_user["user_id"]

        report.modified_date = datetime.now()

        db.commit()

        db.refresh(report)

        return returnSuccess({

            "lms_isnob_id":
                report.lms_isnob_id,

            "message":
                "Issue & Observation Report updated successfully."
        })

    except Exception as e:

        db.rollback()

        return returnException(
            str(e)
        )
    
    # ==========================================================
# DELETE ISSUE & OBSERVATION REPORT
# ==========================================================
@router.delete("/delete_issue_observation/{lms_isnob_id}")
def delete_issue_observation(
    lms_isnob_id: int,
    req: DeleteIssueObservation,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):

    try:

        report = db.query(
            LMSIssuesObservations
        ).filter(
            LMSIssuesObservations.lms_isnob_id ==
            lms_isnob_id,

            LMSIssuesObservations.is_deleted == 0
        ).first()

        if not report:

            return returnException(
                "Issue & Observation Report not found."
            )

        report.is_deleted = 1

        report.delete_reason_desc = \
            req.delete_reason_desc

        report.modified_by = \
            current_user["user_id"]

        report.modified_date = \
            datetime.now()

        db.commit()

        return returnSuccess(
            "Issue & Observation Report deleted successfully."
        )

    except Exception as e:

        db.rollback()

        return returnException(str(e))
    
# ==========================================================
# GET REPORT HISTORY
# ==========================================================
@router.get("/get_issue_observation_history/{lms_isnob_id}")
def get_issue_observation_history(
    lms_isnob_id: int,
    db: Session = Depends(get_db)
):

    try:

        history = db.query(
            LMSIssuesObservationsHistory
        ).filter(
            LMSIssuesObservationsHistory.lms_isnob_id ==
            lms_isnob_id
        ).order_by(
            LMSIssuesObservationsHistory.action_timestamp.desc()
        ).all()

        result = []

        for row in history:

            user = db.query(
                IEMSUsers
            ).filter(
                IEMSUsers.id ==
                row.modified_by
            ).first()

            result.append({

                "history_id":
                    row.history_id,

                "action_type":
                    row.action_type,

                "report_title":
                    row.report_title,

                "mentor_status":
                    row.mentor_status,

                "mentee_status":
                    row.mentee_status,

                "parent_guardian_status":
                    row.parent_guardian_status,

                "modified_by":
                    user.first_name if user else "",

                "action_timestamp":
                    row.action_timestamp
            })

        return returnSuccess(result)

    except Exception as e:

        return returnException(str(e))
    
    # ==========================================================
# UPDATE MENTOR STATUS
# ==========================================================
@router.put("/mentor_agree/{lms_isnob_id}")
def mentor_agree(

    lms_isnob_id: int,

    req: MentorStatusUpdate,

    db: Session = Depends(get_db),

    current_user: dict = Depends(get_current_user)

):

    try:

        report = db.query(
            LMSIssuesObservations
        ).filter(
            LMSIssuesObservations.lms_isnob_id ==
            lms_isnob_id
        ).first()

        if not report:

            return returnException(
                "Report not found."
            )

        report.mentor_status = req.mentor_status

        report.modified_by = current_user["user_id"]

        report.modified_date = datetime.now()

        db.commit()

        return returnSuccess(
            "Mentor status updated successfully."
        )

    except Exception as e:

        db.rollback()

        return returnException(str(e))


def _report_full_name(person):
    if not person:
        return ""
    if isinstance(person, IEMStudents) and person.name:
        return person.name.strip()
    return " ".join(
        str(value).strip()
        for value in (
            getattr(person, "title", None),
            getattr(person, "first_name", None),
            getattr(person, "middle_name", None),
            getattr(person, "last_name", None),
        )
        if value and str(value).strip()
    )


def _report_plain_text(value):
    return unescape(re.sub(r"<[^>]*>", " ", value or "")).strip()


@router.post("/export_issue_observation_pdf")
def export_issue_observation_pdf(
    req: ExportIssueObservationRequest,
    db: Session = Depends(get_db),
):
    """Export reports using the original CodeIgniter report layout."""
    try:
        if not req.report_ids:
            return returnException("Select at least one report to export.")

        reports = (
            db.query(LMSIssuesObservations)
            .filter(
                LMSIssuesObservations.lms_isnob_id.in_(req.report_ids),
                LMSIssuesObservations.is_deleted == 0,
            )
            .order_by(
                LMSIssuesObservations.semester_id,
                LMSIssuesObservations.lms_isnob_id,
            )
            .all()
        )
        if not reports:
            return returnException("No reports found for export.")

        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        output = BytesIO()
        document = SimpleDocTemplate(
            output,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=10 * mm,
            bottomMargin=12 * mm,
        )
        styles = getSampleStyleSheet()
        body_style = ParagraphStyle(
            "ReportBody",
            parent=styles["BodyText"],
            fontName="Times-Roman",
            fontSize=9,
            leading=11,
        )
        label_style = ParagraphStyle(
            "ReportLabel",
            parent=body_style,
            fontName="Times-Bold",
        )
        heading_style = ParagraphStyle(
            "InstitutionHeading",
            parent=body_style,
            alignment=TA_CENTER,
            fontName="Times-Bold",
            fontSize=11,
            leading=13,
        )
        title_style = ParagraphStyle(
            "ReportTitle",
            parent=label_style,
            textColor=colors.HexColor("#b00000"),
            fontSize=11,
            leading=14,
        )

        def paragraph(value, style=body_style):
            return Paragraph(escape(str(value or "")), style)

        story = []
        for index, report in enumerate(reports):
            if index:
                story.append(PageBreak())

            student = db.query(IEMStudents).filter_by(
                student_id=report.ssd_id
            ).first()
            mentor = db.query(IEMSUsers).filter_by(
                id=report.mentor_users_id
            ).first()
            semester = db.query(IEMSemester).filter_by(
                semester_id=report.semester_id
            ).first()
            batch = db.query(IEMSAcademicBatch).filter_by(
                academic_batch_id=report.academic_batch_id
            ).first()
            department = None
            if batch and batch.dept_id:
                department = db.query(IEMSDepartment).filter_by(
                    dept_id=batch.dept_id
                ).first()

            org_id = (
                getattr(student, "org_id", None)
                or getattr(mentor, "org_id", None)
                or getattr(batch, "org_id", None)
            )
            organisation = (
                db.query(IEMOrganisation).filter_by(org_id=org_id).first()
                if org_id else None
            )
            organisation_name = (
                organisation.org_name
                if organisation else "IonIdea Institute of Technology and Management"
            )
            department_name = department.dept_name if department else ""

            header = Table(
                [[
                    Paragraph("<b>YOUR<br/>LOGO<br/>HERE</b>", heading_style),
                    Paragraph(
                        f"{escape(organisation_name)}<br/>"
                        f"{escape(organisation_name)}<br/>"
                        f"Department of {escape(department_name)}",
                        heading_style,
                    ),
                ]],
                colWidths=[28 * mm, 139 * mm],
            )
            header.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("BOX", (0, 0), (0, 0), 0.5, colors.HexColor("#777777")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.7, colors.HexColor("#777777")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.extend([
                header,
                Spacer(1, 5 * mm),
                Paragraph("Issues and Observation Report", title_style),
                Spacer(1, 7 * mm),
                Paragraph(escape(report.report_title), label_style),
                Spacer(1, 2 * mm),
            ])

            counselling_date = (
                report.counselling_date.strftime("%d-%m-%Y")
                if report.counselling_date else ""
            )
            semester_name = (
                (semester.term_name or semester.semester_desc)
                if semester else ""
            )
            mentor_agreed_date = (
                report.modified_date or report.created_date
            )
            mentee_agreed_date = report.modified_date or report.created_date
            mentor_agreement = (
                f"Agreed on {mentor_agreed_date.strftime('%d-%m-%Y')}"
                if report.mentor_status and mentor_agreed_date else "Pending"
            )
            mentee_agreement = (
                f"Agreed on {mentee_agreed_date.strftime('%d-%m-%Y')}"
                if report.mentee_status and mentee_agreed_date else "Pending"
            )

            data = [
                [paragraph("Mentee Name", label_style),
                 paragraph(f"{_report_full_name(student)} [{report.student_usn}]"),
                 paragraph("Mentor Name", label_style), paragraph(_report_full_name(mentor))],
                [paragraph("Counselling Date", label_style), paragraph(counselling_date),
                 paragraph("Semester", label_style), paragraph(semester_name)],
                [paragraph("Purpose of Meeting / Issue Reported", label_style),
                 paragraph(_report_plain_text(report.purpose_of_meeting_desc)), "", ""],
                [paragraph("Observations and Action Taken", label_style),
                 paragraph(_report_plain_text(report.observation_desc)), "", ""],
                [paragraph("Has the issue been communicated and discussed with parents?", label_style),
                 "", "", paragraph("Yes" if report.comm_parent_flag else "No")],
                [paragraph("Has the issue been communicated and discussed with higher authorities?", label_style),
                 "", "", paragraph("Yes" if report.comm_high_auth_flag else "No")],
                [paragraph("Mentee Signature with Date", label_style), "",
                 paragraph("Mentor Signature with Date", label_style), ""],
                [paragraph(mentee_agreement), "", paragraph(mentor_agreement), ""],
            ]
            report_table = Table(
                data,
                colWidths=[68 * mm, 27 * mm, 52 * mm, 20 * mm],
                repeatRows=0,
            )
            report_table.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#bbbbbb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("SPAN", (1, 2), (3, 2)),
                ("SPAN", (1, 3), (3, 3)),
                ("SPAN", (0, 4), (2, 4)),
                ("SPAN", (0, 5), (2, 5)),
                ("SPAN", (0, 6), (1, 6)),
                ("SPAN", (2, 6), (3, 6)),
                ("SPAN", (0, 7), (1, 7)),
                ("SPAN", (2, 7), (3, 7)),
            ]))
            story.append(report_table)

        document.build(story)
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="application/pdf",
            headers={
                "Content-Disposition":
                    "attachment; filename=issues_observations_report.pdf"
            },
        )
    except Exception as e:
        return returnException(str(e))

# ==========================================================
# GET CURRICULUM / TERM LIST FOR A STUDENT
# ==========================================================
@router.get("/get_crclm_term/{student_usn}")
def get_crclm_term(
    student_usn: str,
    db: Session = Depends(get_db)
):
    try:
        student = db.query(IEMStudents).filter(
            IEMStudents.usno == student_usn
        ).first()

        if not student:
            return returnException("Student not found.")

        rows = (
            db.query(
                IEMSAcademicBatch.academic_batch_id,
                IEMSAcademicBatch.academic_batch_desc,
                IEMSemester.semester_id,
                IEMSemester.semester_desc,
                IEMSemester.term_name,
                IEMSCourses.crs_code,
            )
            .select_from(CudosMapCoursetoStudent)
            .join(
                IEMSAcademicBatch,
                IEMSAcademicBatch.academic_batch_id ==
                CudosMapCoursetoStudent.academic_batch_id,
            )
            .join(
                IEMSemester,
                IEMSemester.semester_id ==
                CudosMapCoursetoStudent.semester_id,
            )
            .join(
                IEMSCourses,
                IEMSCourses.crs_id == CudosMapCoursetoStudent.crs_id,
            )
            .filter(
                CudosMapCoursetoStudent.student_id == student.student_id
            )
            .distinct()
            .order_by(
                IEMSAcademicBatch.academic_batch_id,
                IEMSAcademicBatch.first_year_flag.desc(),
                IEMSemester.semester,
                IEMSemester.semester_id,
            )
            .all()
        )

        curriculum_map = {}

        for row in rows:
            curriculum = curriculum_map.setdefault(
                row.academic_batch_id,
                {
                    "crclm_id": row.academic_batch_id,
                    "crclm_name": row.academic_batch_desc,
                    "terms": {},
                },
            )

            term = curriculum["terms"].setdefault(
                row.semester_id,
                {
                    "crclm_id": row.academic_batch_id,
                    "crclm_name": row.academic_batch_desc,
                    "crclm_term_id": row.semester_id,
                    "term_name": row.term_name or row.semester_desc,
                    "crs_code": [],
                },
            )

            if row.crs_code and row.crs_code not in term["crs_code"]:
                term["crs_code"].append(row.crs_code)

        result = []
        for curriculum in curriculum_map.values():
            curriculum["terms"] = [
                {
                    **term,
                    "crs_code": ", ".join(term["crs_code"]),
                }
                for term in curriculum["terms"].values()
            ]
            result.append(curriculum)

        return returnSuccess(result)

    except Exception as e:
        return returnException(str(e))