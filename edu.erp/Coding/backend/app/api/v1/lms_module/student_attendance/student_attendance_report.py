from calendar import monthrange
from datetime import date, datetime
from http.client import HTTPException
from typing import Annotated, Any
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, Query,  File, Form, HTTPException, UploadFile
from sqlalchemy import text
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

# Change only this import if get_db is located in a different module in your project.
from app.core.database import get_db
from app.utils.auth_helper import get_current_user
from .student_attendance_report_schema import (
    AttendanceClassDateResponse,
    AttendanceCourseClassDateRow,
    StudentAttendanceDaywiseRow,
    StudentAttendanceOption,
    StudentAttendanceSummaryRow,
    AttendanceUploadResponse

)

router = APIRouter()
UPLOAD_DIRECTORY = Path("uploads/ionlms/student_upload_attendance_document")
ALLOWED_EXTENSIONS = {".jpeg", ".jpg", ".png", ".pdf", ".doc", ".docx", ".txt"}
MAX_FILE_SIZE = 5 * 1024 * 1024


def _user_value(current_user: Any, key: str) -> Any:
    return current_user.get(key) if isinstance(current_user, dict) else getattr(current_user, key, None)


def _student(db: Session, current_user: Any) -> dict:
    user_id = _user_value(current_user, "id") or _user_value(current_user, "user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Unable to identify the logged-in user")
    row = db.execute(
        text("""
            SELECT s.student_id, s.usno, s.academic_batch_id, s.semester_id,
                   COALESCE(s.section_id, 0) AS section_id
            FROM iems_users u
            INNER JOIN iems_students s ON s.student_id = u.student_id
            WHERE u.id = :user_id AND COALESCE(u.active, 1) = 1
            LIMIT 1
        """), {"user_id": user_id}
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Student profile is not mapped to this user")
    return dict(row)

def _month_range(from_month: str, to_month: str) -> tuple[date, date]:
    try:
        from_value = datetime.strptime(from_month, "%Y-%m")
        to_value = datetime.strptime(to_month, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="from_month and to_month must use YYYY-MM format",
        ) from exc

    from_date = date(
        from_value.year,
        from_value.month,
        1,
    )

    to_date = date(
        to_value.year,
        to_value.month,
        monthrange(to_value.year, to_value.month)[1],
    )

    if from_date > to_date:
        raise HTTPException(
            status_code=422,
            detail="From Month cannot be later than To Month",
        )

    return from_date, to_date

def parse_ci_month(value: str, field_name: str) -> datetime:
    try:
        return datetime.strptime(value, "%m-%Y")
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must use MM-YYYY format",
        ) from exc

@router.get(
    "/attendance-class-date",
    response_model=AttendanceClassDateResponse,
)
def get_attendance_class_date(
    curriculum_id: int = Query(gt=0),
    term_id: int = Query(gt=0),
    ssd_id: int = Query(gt=0),
    class_date: str = Query(description="From month in MM-YYYY format"),
    class_to_date: str = Query(description="To month in MM-YYYY format"),
    db: Session = Depends(get_db),
):
    """FastAPI conversion of CodeIgniter get_attendance_class_date()."""
    from_month = parse_ci_month(class_date, "class_date")
    to_month = parse_ci_month(class_to_date, "class_to_date")
    if from_month > to_month:
        raise HTTPException(
            status_code=422,
            detail="class_date cannot be later than class_to_date",
        )

    date_params = {
        "from_date": from_month.strftime("%Y-%m-01"),
        "to_month": to_month.strftime("%Y-%m-01"),
    }

    courses = db.execute(
        text(
            """
            SELECT DISTINCT c.crs_id, c.crs_title, c.crs_code
            FROM iems_courses AS c
            INNER JOIN cudos_map_courseto_student AS mcs
                ON c.crclm_id = mcs.crclm_id
               AND c.crclm_term_id = mcs.crclm_term_id
               AND c.crs_id = mcs.crs_id
            WHERE c.crclm_id = :curriculum_id
              AND c.crclm_term_id = :term_id
              AND mcs.student_id = :ssd_id
              AND c.status > 0
            ORDER BY c.crs_code, c.crs_title
            """
        ),
        {
            "curriculum_id": curriculum_id,
            "term_id": term_id,
            "ssd_id": ssd_id,
        },
    ).mappings().all()

    if not courses:
        return AttendanceClassDateResponse(status="false")

    course_ids = [int(course["crs_id"]) for course in courses]
    common_params = {
        "curriculum_id": curriculum_id,
        "term_id": term_id,
        "ssd_id": ssd_id,
        "course_ids": course_ids,
        **date_params,
    }
    date_condition = """
        STR_TO_DATE(lma.attendance_date, '%d-%m-%Y') BETWEEN
        STR_TO_DATE(:from_date, '%Y-%m-%d')
        AND LAST_DAY(STR_TO_DATE(:to_month, '%Y-%m-%d'))
    """

    overall_query = text(
        f"""
        SELECT
            CAST(COALESCE(SUM(lma.attendance_class_count), 0) AS SIGNED)
                AS overall_classes_in_month,
            CAST(COALESCE(SUM(lmsa.attendance_status), 0) AS SIGNED)
                AS overall_attendance_in_month
        FROM lms_manage_attendance AS lma
        INNER JOIN lms_map_student_attendance AS lmsa
            ON lma.attendance_id = lmsa.attendance_id
        WHERE {date_condition}
          AND lma.crs_id IN :course_ids
          AND lma.crclm_id = :curriculum_id
          AND lma.crclm_term_id = :term_id
          AND lma.status = 1
          AND lmsa.ssd_id = :ssd_id
        """
    ).bindparams(bindparam("course_ids", expanding=True))
    overall = db.execute(overall_query, common_params).mappings().one()

    details_query = text(
        f"""
        SELECT
            CAST(COALESCE(lma.attendance_class_count, 0) AS SIGNED)
                AS total_class_in_day,
            RIGHT(lma.attendance_date, 7) AS attendance_month,
            DAYNAME(STR_TO_DATE(lma.attendance_date, '%d-%m-%Y'))
                AS week_day_name,
            lma.attendance_date AS class_date,
            c.crs_id,
            c.crs_title,
            c.crs_code,
            lma.crclm_term_id,
            CAST(COALESCE(SUM(lmsa.attendance_status), 0) AS SIGNED)
                AS attended_class_in_day
        FROM lms_manage_attendance AS lma
        INNER JOIN lms_map_student_attendance AS lmsa
            ON lma.attendance_id = lmsa.attendance_id
        INNER JOIN iems_courses AS c ON c.crs_id = lma.crs_id
        WHERE {date_condition}
          AND lma.crclm_id = :curriculum_id
          AND lma.crclm_term_id = :term_id
          AND lma.crs_id IN :course_ids
          AND lmsa.ssd_id = :ssd_id
          AND lma.status = 1
        GROUP BY lma.crs_id, lma.attendance_date,
                 lma.attendance_class_count, c.crs_title, c.crs_code,
                 lma.crclm_term_id
        ORDER BY STR_TO_DATE(lma.attendance_date, '%d-%m-%Y'), c.crs_code
        """
    ).bindparams(bindparam("course_ids", expanding=True))
    detail_rows = db.execute(details_query, common_params).mappings().all()

    totals_query = text(
        f"""
        SELECT
            lma.crs_id,
            CAST(
                COALESCE(
                    IF(
                        SUM(lma.attendance_class_count) > 0,
                        SUM(lma.attendance_class_count),
                        COUNT(lma.attendance_id)
                    ),
                    0
                ) AS SIGNED
            ) AS scheduled_classes,
            CAST(COALESCE(SUM(lmsa.attendance_status), 0) AS SIGNED)
                AS attendance
        FROM lms_manage_attendance AS lma
        INNER JOIN lms_map_student_attendance AS lmsa
            ON lma.attendance_id = lmsa.attendance_id
        WHERE {date_condition}
          AND lma.crclm_id = :curriculum_id
          AND lma.crclm_term_id = :term_id
          AND lma.crs_id IN :course_ids
          AND lmsa.ssd_id = :ssd_id
          AND lma.status = 1
        GROUP BY lma.crs_id
        """
    ).bindparams(bindparam("course_ids", expanding=True))
    totals = db.execute(totals_query, common_params).mappings().all()

    details_by_course: dict[int, list[dict]] = {course_id: [] for course_id in course_ids}
    for row in detail_rows:
        details_by_course[int(row["crs_id"])].append(dict(row))

    total_class_in_month = {
        str(row["crs_id"]): {"scheduled_classes": row["scheduled_classes"]}
        for row in totals
    }
    attended_class_in_month = {
        str(row["crs_id"]): {"attendance": row["attendance"]}
        for row in totals
    }
    last_attended = detail_rows[-1]["attended_class_in_day"] if detail_rows else "-"

    return {
        "status": "true" if totals else "false",
        "class_list": [details_by_course[course_id] for course_id in course_ids],
        "course_data": [str(course["crs_title"]) for course in courses],
        "crs_code_data": [str(course["crs_code"]) for course in courses],
        "course_id_data": course_ids,
        "total_class_in_month": total_class_in_month,
        "attended_class_in_month": attended_class_in_month,
        "overall_classes_in_month": overall["overall_classes_in_month"],
        "overall_attendance_in_month": overall["overall_attendance_in_month"],
        "attended_class_in_day": last_attended,
    }


@router.get(
    "/course-class-date",
    response_model=list[AttendanceCourseClassDateRow],
)
def get_course_class_date(
    curriculum_id: int = Query(gt=0),
    term_id: int = Query(gt=0),
    ssd_id: int = Query(gt=0),
    class_date: str = Query(description="From month in MM-YYYY format"),
    class_to_date: str = Query(description="To month in MM-YYYY format"),
    db: Session = Depends(get_db),
):
    """FastAPI conversion of CodeIgniter get_course_class_date()."""
    from_month = parse_ci_month(class_date, "class_date")
    to_month = parse_ci_month(class_to_date, "class_to_date")
    if from_month > to_month:
        raise HTTPException(
            status_code=422,
            detail="class_date cannot be later than class_to_date",
        )

    rows = db.execute(
        text(
            """
            SELECT
                DATE_FORMAT(
                    MIN(STR_TO_DATE(lma.attendance_date, '%d-%m-%Y')),
                    '%m-%Y'
                ) AS attendance_month,
                DAYNAME(
                    MIN(STR_TO_DATE(lma.attendance_date, '%d-%m-%Y'))
                ) AS week_day_name,
                DATE_FORMAT(
                    MIN(STR_TO_DATE(lma.attendance_date, '%d-%m-%Y')),
                    '%d-%m-%Y'
                ) AS class_date,
                CONCAT_WS(' - ', c.crs_code, c.crs_title) AS course,
                c.crs_id,
                COALESCE(MAX(lmsa.student_usn), '') AS student_usn,
                CAST(COALESCE(SUM(lmsa.attendance_status), 0) AS SIGNED)
                    AS present_count,
                CAST(COALESCE(SUM(lmsa.refer_absent_status), 0) AS SIGNED)
                    AS absent_count,
                CAST(
                    COALESCE(
                        SUM(
                            COALESCE(lmsa.attendance_status, 0) +
                            COALESCE(lmsa.refer_absent_status, 0)
                        ),
                        0
                    ) AS SIGNED
                ) AS class_count
            FROM lms_manage_attendance AS lma
            INNER JOIN lms_map_student_attendance AS lmsa
                ON lma.attendance_id = lmsa.attendance_id
            INNER JOIN iems_courses AS c
                ON c.crs_id = lma.crs_id
            WHERE lma.crclm_id = :curriculum_id
              AND lma.crclm_term_id = :term_id
              AND lmsa.ssd_id = :ssd_id
              AND lma.status = 1
              AND STR_TO_DATE(lma.attendance_date, '%d-%m-%Y') BETWEEN
                  STR_TO_DATE(:from_date, '%Y-%m-%d')
                  AND LAST_DAY(STR_TO_DATE(:to_month, '%Y-%m-%d'))
              AND EXISTS (
                  SELECT 1
                  FROM cudos_map_courseto_student AS mcs
                  WHERE mcs.crs_id = c.crs_id
                    AND mcs.crclm_id = c.crclm_id
                    AND mcs.crclm_term_id = c.crclm_term_id
                    AND mcs.student_id = :ssd_id
              )
            GROUP BY c.crs_id, c.crs_code, c.crs_title
            ORDER BY course
            """
        ),
        {
            "curriculum_id": curriculum_id,
            "term_id": term_id,
            "ssd_id": ssd_id,
            "from_date": from_month.strftime("%Y-%m-01"),
            "to_month": to_month.strftime("%Y-%m-01"),
        },
    ).mappings().all()
    return rows


@router.get("/curriculums", response_model=list[StudentAttendanceOption])
def get_curriculums(db: Session = Depends(get_db)):
    """Return curriculums for which active attendance has been entered."""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT
                CAST(cr.academic_batch_id AS CHAR) AS value,
                cr.academic_batch_code AS label
            FROM iems_academic_batch AS cr
            INNER JOIN lms_manage_attendance AS a
                ON a.academic_batch_id = cr.academic_batch_id
               AND a.status = 1
            ORDER BY cr.academic_batch_code
            """
        )
    ).mappings().all()
    return rows

@router.get("/terms/{academic_batch_id}", response_model=list[StudentAttendanceOption])
def get_terms(academic_batch_id: int, db: Session = Depends(get_db)):
    """academic_batch_id is the curriculum/academic_batch_id used by the current React page."""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT
                CAST(ct.semester_id AS CHAR) AS value,
                COALESCE(
                    NULLIF(TRIM(ct.semester_desc), ''),
                    CONCAT('Term ', ct.semester_id)
                ) AS label
            FROM iems_semester AS ct
            INNER JOIN lms_manage_attendance AS a
                ON a.semester_id = ct.semester_id
               AND a.academic_batch_id = ct.academic_batch_id
               AND a.status = 1
            WHERE ct.academic_batch_id = :academic_batch_id
            ORDER BY ct.semester_id
            """
        ),
        {"academic_batch_id": academic_batch_id},
    ).mappings().all()
    return rows


@router.get("/lesson-dates", response_model=list[str])
def get_lesson_dates(
    db: Session = Depends(get_db),
    academic_batch_id: int = Query(gt=0),
    semester_id: int = Query(gt=0),
    course_id: int = Query(gt=0),
    section_id: int = Query(gt=0),
):
    rows = db.execute(
        text(
            """
            SELECT DISTINCT
                DATE_FORMAT(
                    STR_TO_DATE(a.attendance_date, '%d-%m-%Y'),
                    '%Y-%m-%d'
                ) AS lesson_date
            FROM lms_manage_attendance AS a
            WHERE a.academic_batch_id = :academic_batch_id
              AND a.semester_id = :term_id
              AND a.crs_id = :course_id
              AND a.section_id = :section_id
              AND a.status = 1
              AND STR_TO_DATE(a.attendance_date, '%d-%m-%Y') IS NOT NULL
            ORDER BY STR_TO_DATE(a.attendance_date, '%d-%m-%Y')
            """
        ),
        {
            "academic_batch_id": academic_batch_id,
            "term_id": semester_id,
            "course_id": course_id,
            "section_id": section_id,
        },
    ).scalars().all()
    return list(rows)

@router.get("/summary", response_model=list[StudentAttendanceSummaryRow])
def get_attendance_summary(academic_batch_id: int, semester_id: int, from_month: str,
                           to_month: str, db: Session = Depends(get_db),
                        #    current_user: Any = Depends(get_current_user)
                           ):
    # student = _student(db, current_user)
    student = 1
    from_date, to_date = _month_range(from_month, to_month)
    rows = db.execute(text("""
        SELECT CONCAT_WS(' - ', c.crs_code, c.crs_title) AS course,
               CAST(COALESCE(SUM(sa.attendance_status), 0) AS SIGNED) AS present,
               CAST(COALESCE(SUM(COALESCE(sa.attendance_status, 0) +
                                 COALESCE(sa.refer_absent_status, 0)), 0) AS SIGNED) AS total_classes
        FROM cudos_map_courseto_student mcs
        INNER JOIN iems_courses c ON c.crs_id = mcs.crs_id
        LEFT JOIN lms_manage_attendance a
          ON a.crs_id = mcs.crs_id AND a.academic_batch_id = mcs.academic_batch_id
         AND a.semester_id = mcs.semester_id AND a.status = 1
         AND STR_TO_DATE(a.attendance_date, '%d-%m-%Y') BETWEEN
             STR_TO_DATE(:from_date, '%Y-%m-%d') AND LAST_DAY(STR_TO_DATE(:to_date, '%Y-%m-%d'))
        LEFT JOIN lms_map_student_attendance sa
          ON sa.attendance_id = a.attendance_id AND sa.ssd_id = :student_id
        WHERE mcs.student_id = :student_id AND mcs.academic_batch_id = :academic_batch_id
          AND mcs.semester_id = :semester_id AND COALESCE(mcs.status, 1) > 0
          AND COALESCE(c.status, 1) > 0
        GROUP BY c.crs_id, c.crs_code, c.crs_title ORDER BY c.crs_code, c.crs_title
    """), {"student_id": student, "academic_batch_id": academic_batch_id,
             "semester_id": semester_id, "from_date": from_date, "to_date": to_date}).mappings().all()
    result = []
    for row in rows:
        item = dict(row)
        total, present = int(item["total_classes"] or 0), int(item["present"] or 0)
        percentage = round((present / total) * 100, 2) if total else 0.0
        item.update(percentage=percentage,
                    attendance_level="success" if percentage > 85 else "warning" if percentage > 75 else "danger")
        result.append(item)
    return result


@router.get(
    "/daywise",
    response_model=list[StudentAttendanceDaywiseRow],
)
def get_attendance_daywise(
    academic_batch_id: int,
    semester_id: int,
    from_month: str,
    to_month: str,
    db: Session = Depends(get_db),
    # current_user: Any = Depends(get_current_user),
):
    # student = _student(db, current_user)
    student = 1

    from_date, to_date = _month_range(
        from_month,
        to_month,
    )

    rows = db.execute(
        text(
            """
            SELECT
                MAX(a.attendance_id) AS attendance_id,
                CONCAT_WS(
                    ' - ',
                    c.crs_code,
                    c.crs_title
                ) AS course,
                DATE_FORMAT(
                    STR_TO_DATE(
                        a.attendance_date,
                        '%d-%m-%Y'
                    ),
                    '%Y-%m-%d'
                ) AS attendance_date,
                CAST(
                    COALESCE(
                        SUM(sa.attendance_status),
                        0
                    ) AS SIGNED
                ) AS present_count,
                CAST(
                    COALESCE(
                        SUM(
                            COALESCE(
                                sa.attendance_status,
                                0
                            ) +
                            COALESCE(
                                sa.refer_absent_status,
                                0
                            )
                        ),
                        0
                    ) AS SIGNED
                ) AS class_count,
                COALESCE(
                    MAX(sa.stud_attendance_doc_url),
                    ''
                ) AS document_path,
                COALESCE(
                    MAX(sa.accept_flag),
                    0
                ) AS accept_flag
            FROM lms_manage_attendance AS a
            INNER JOIN lms_map_student_attendance AS sa
                ON sa.attendance_id = a.attendance_id
                AND sa.ssd_id = :student_id
            INNER JOIN iems_courses AS c
                ON c.crs_id = a.crs_id
            WHERE a.academic_batch_id = :academic_batch_id
              AND a.semester_id = :semester_id
              AND a.status = 1
              AND STR_TO_DATE(
                    a.attendance_date,
                    '%d-%m-%Y'
                  ) >= :from_date
              AND STR_TO_DATE(
                    a.attendance_date,
                    '%d-%m-%Y'
                  ) <= :to_date
              AND EXISTS (
                    SELECT 1
                    FROM cudos_map_courseto_student AS mcs
                    WHERE mcs.crs_id = a.crs_id
                      AND mcs.student_id = :student_id
                      AND mcs.academic_batch_id =
                          :academic_batch_id
                      AND mcs.semester_id =
                          :semester_id
                      AND COALESCE(mcs.status, 1) > 0
              )
            GROUP BY
                a.crs_id,
                a.attendance_date,
                c.crs_code,
                c.crs_title
            ORDER BY
                STR_TO_DATE(
                    a.attendance_date,
                    '%d-%m-%Y'
                ) ASC,
                c.crs_code ASC
            """
        ),
        {
            "student_id": student,
            "academic_batch_id": academic_batch_id,
            "semester_id": semester_id,
            "from_date": from_date,
            "to_date": to_date,
        },
    ).mappings().all()

    result = []

    for row in rows:
        item = dict(row)

        flag = int(item.pop("accept_flag") or 0)
        document_path = item.pop("document_path") or ""
        present = int(item.pop("present_count") or 0)
        total = int(item.pop("class_count") or 0)

        item.update(
            attendance=f"{present} / {total}",
            attendance_document=(
                "View document"
                if document_path
                else ""
            ),
            attendance_document_url=(
                "/api/v1/student_attendance_report/"
                f'document/{item["attendance_id"]}'
                if document_path
                else ""
            ),
            document_status=(
                "Accepted"
                if flag == 1
                else "Rejected"
                if flag == 2
                else ""
            ),
            can_upload=(
                (present < total and not document_path)
                or flag == 2
            ),
        )

        result.append(item)

    return result


@router.post("/upload-document", response_model=AttendanceUploadResponse)
def upload_document(attendance_id: int = Form(...), document: UploadFile = File(...),
                    db: Session = Depends(get_db), current_user: Any = Depends(get_current_user)):
    student = _student(db, current_user)
    suffix = Path(document.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Allowed formats: jpeg, jpg, png, pdf, doc, docx and txt")
    content = document.file.read(MAX_FILE_SIZE + 1)
    if not content:
        raise HTTPException(status_code=422, detail="Please choose a document")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Document size cannot exceed 5 MB")
    record = db.execute(text("""
        SELECT sa.stud_attendance_doc_url, COALESCE(sa.accept_flag, 0) AS accept_flag
        FROM lms_map_student_attendance sa
        INNER JOIN lms_manage_attendance a ON a.attendance_id = sa.attendance_id
        WHERE sa.attendance_id = :attendance_id AND sa.ssd_id = :student_id AND a.status = 1 LIMIT 1
    """), {"attendance_id": attendance_id, "student_id": student["student_id"]}).mappings().first()
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    if record["stud_attendance_doc_url"] and int(record["accept_flag"] or 0) != 2:
        raise HTTPException(status_code=409, detail="A document has already been submitted")
    UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIRECTORY / f'{datetime.now():%Y%m%d%H%M%S}_{student["usno"]}_{uuid4().hex}{suffix}'
    path.write_bytes(content)
    db.execute(text("""
        UPDATE lms_map_student_attendance SET stud_attendance_doc_url = :path, accept_flag = 0
        WHERE attendance_id = :attendance_id AND ssd_id = :student_id
    """), {"path": path.as_posix(), "attendance_id": attendance_id, "student_id": student["student_id"]})
    db.commit()
    return {"status": "true", "message": "File uploaded successfully",
            "attendance_document_url": f"/api/v1/student_attendance_report/document/{attendance_id}"}


@router.get("/document/{attendance_id}")
def download_document(attendance_id: int, db: Session = Depends(get_db),
                      current_user: Any = Depends(get_current_user)):
    student = _student(db, current_user)
    stored = db.execute(text("""
        SELECT stud_attendance_doc_url FROM lms_map_student_attendance
        WHERE attendance_id = :attendance_id AND ssd_id = :student_id LIMIT 1
    """), {"attendance_id": attendance_id, "student_id": student["student_id"]}).scalar_one_or_none()
    if not stored:
        raise HTTPException(status_code=404, detail="Attendance document not found")
    path = Path(stored)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attendance document is missing from storage")
    return FileResponse(path, filename=path.name)

