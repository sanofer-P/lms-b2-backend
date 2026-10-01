"""Assignment reports scoped to the selected batch, semester, course and section."""
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.utils.auth_helper import get_current_user
from .student_assignment_schema import (
    AssignmentListRequest,
    DropdownListResponse,
    StudentAssignmentListResponse,
    StudentAssignmentReportRequest,
    StudentAssignmentUploadResponse,
)

router = APIRouter(tags=["Student Assignment"], dependencies=[Depends(get_current_user)])

def _parse_database_date(value) -> date | None:
    """Convert MySQL/legacy CodeIgniter date values into a Python date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None

        try:
            return datetime.fromisoformat(text_value.replace("Z", "+00:00")).date()
        except ValueError:
            pass

        for date_format in (
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y/%m/%d",
            "%d/%m/%Y %H:%M:%S",
            "%d-%m-%Y %H:%M:%S",
        ):
            try:
                return datetime.strptime(text_value, date_format).date()
            except ValueError:
                continue

    raise HTTPException(
        status_code=500,
        detail="Invalid assignment due date stored in the database",
    )


@router.get("/student-curriculums/{student_id}", response_model=DropdownListResponse)
def get_student_curriculums(student_id: int, db: Session = Depends(get_db)):
    """Return academic batches (the LMS 2.0 replacement for curriculum)."""
    rows = db.execute(text("""
        SELECT DISTINCT ab.academic_batch_id AS value,
               CONCAT(ab.academic_batch_desc, ' ', ab.start_year, '-', ab.end_year) AS label
        FROM iems_academic_batch ab
        JOIN (
            SELECT s.academic_batch_id
            FROM iems_students s
            WHERE s.student_id = :student_id AND s.status = 1
            UNION
            SELECT m.academic_batch_id
            FROM cudos_map_courseto_student m
            WHERE m.student_id = :student_id
        ) student_batch ON student_batch.academic_batch_id = ab.academic_batch_id
        WHERE ab.status = 1
        ORDER BY label
    """), {"student_id": student_id}).mappings().all()
    return {"status": True, "data": [dict(row) for row in rows]}


@router.get("/semesters/{academic_batch_id}", response_model=DropdownListResponse)
def get_batch_semesters(
    academic_batch_id: int,
    student_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    rows = db.execute(text("""
        SELECT DISTINCT sem.semester_id AS value,
               COALESCE(NULLIF(sem.term_name, ''), NULLIF(sem.semester_desc, ''),
                        CONCAT('Semester ', sem.semester)) AS label
        FROM iems_semester sem
        WHERE sem.academic_batch_id = :academic_batch_id
          AND sem.status = 1
          AND (
              EXISTS (
                  SELECT 1
                  FROM cudos_map_courseto_student m
                  WHERE m.student_id = :student_id
                    AND m.academic_batch_id = sem.academic_batch_id
                    AND m.semester_id = sem.semester_id
              )
              OR EXISTS (
                  SELECT 1
                  FROM iems_students s
                  WHERE s.student_id = :student_id
                    AND s.academic_batch_id = sem.academic_batch_id
                    AND (s.current_semester = sem.semester_id
                         OR s.current_semester = sem.semester)
              )
          )
        ORDER BY sem.semester, sem.semester_id
    """), {
        "academic_batch_id": academic_batch_id,
        "student_id": student_id,
    }).mappings().all()
    return {"status": True, "data": [dict(row) for row in rows]}


@router.get("/student-courses", response_model=DropdownListResponse)
def get_student_courses(
    student_id: int = Query(..., gt=0),
    academic_batch_id: int = Query(..., gt=0),
    semester_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    rows = db.execute(text("""
        SELECT DISTINCT c.crs_id AS value,
               CONCAT(c.crs_code, ' - ', COALESCE(c.crs_title, '')) AS label
        FROM cudos_map_courseto_student m
        JOIN iems_courses c ON c.crs_id = m.crs_id
        WHERE m.student_id = :student_id
          AND m.academic_batch_id = :academic_batch_id
          AND m.semester_id = :semester_id
          AND COALESCE(c.status, 1) = 1
        ORDER BY c.crs_code, c.crs_title
    """), {
        "student_id": student_id,
        "academic_batch_id": academic_batch_id,
        "semester_id": semester_id,
    }).mappings().all()
    return {"status": True, "data": [dict(row) for row in rows]}


@router.get("/my-assignments", response_model=StudentAssignmentListResponse)
def get_my_assignments(
    student_id: int = Query(..., gt=0),
    academic_batch_id: int = Query(..., gt=0),
    semester_id: int = Query(..., gt=0),
    course_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    # The course condition is intentionally applied to lms_manage_assignment.
    # Filtering only the joined course table caused assignments from other
    # courses to appear in the legacy CodeIgniter screen.
    rows = db.execute(text("""
        SELECT m.map_assignment_student_id,
               a.lms_assignment_id,
               m.ssd_id,
               s.usno AS student_usn,
               m.file_name AS student_file_name,
               m.file_path AS student_file_path,
               m.seen_on,
               COALESCE(m.accept_rework_flag, 0) AS accept_rework_flag,
               m.secured_marks,
               m.remark,
               m.assignment_justification,
               m.current_comments,
               a.assignment_name,
               a.additional_info,
               a.file_name AS assignment_file_name,
               a.file_path AS assignment_file_path,
               a.issue_date,
               a.due_date,
               a.academic_batch_id AS crclm_id,
               a.semester_id AS crclm_term_id,
               a.crs_id,
               NULL AS topic_id,
               NULL AS topic_title,
               s.section AS section_name,
               c.crs_code,
               c.crs_title,
               CONCAT(ab.academic_batch_desc, ' ', ab.start_year, '-', ab.end_year) AS crclm_name,
               COALESCE(NULLIF(sem.term_name, ''), NULLIF(sem.semester_desc, ''),
                        CONCAT('Semester ', sem.semester)) AS term_name,
               a.created_date AS assignment_created_date,
               a.modified_date AS assignment_modified_date,
               0 AS update_count
        FROM lms_map_assignment_to_students m
        JOIN lms_manage_assignment a
          ON a.lms_assignment_id = m.lms_assignment_id
        JOIN iems_students s ON s.student_id = m.ssd_id
        JOIN iems_courses c ON c.crs_id = a.crs_id
        JOIN iems_academic_batch ab ON ab.academic_batch_id = a.academic_batch_id
        JOIN iems_semester sem ON sem.semester_id = a.semester_id
        WHERE m.ssd_id = :student_id
            AND a.academic_batch_id = :academic_batch_id
            AND a.semester_id = :semester_id
            AND a.crs_id = :course_id
            AND EXISTS (
                SELECT 1
                FROM cudos_map_courseto_student enrollment
                WHERE enrollment.student_id = :student_id
                    AND enrollment.academic_batch_id = :academic_batch_id
                    AND enrollment.semester_id = :semester_id
                    AND enrollment.crs_id = :course_id
            )
        ORDER BY a.issue_date DESC, a.lms_assignment_id DESC
    """), {
        "student_id": student_id,
        "academic_batch_id": academic_batch_id,
        "semester_id": semester_id,
        "course_id": course_id,
    }).mappings().all()
    return {"status": True, "data": [dict(row) for row in rows]}


ALLOWED_STUDENT_ASSIGNMENT_EXTENSIONS = {
    ".jpeg", ".jpg", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png"
}
MAX_STUDENT_ASSIGNMENT_SIZE = 5 * 1024 * 1024


def _assignment_storage_root() -> Path:
    """Return the application root that owns the legacy uploads directory."""
    configured_root = os.getenv("LMS_UPLOAD_ROOT")
    if configured_root:
        return Path(configured_root).expanduser().resolve()
    return Path(__file__).resolve().parents[5]


def _resolve_assignment_file(stored_value: str) -> Path | None:
    """Resolve legacy relative upload paths independently of Uvicorn's cwd."""
    normalized = stored_value.replace("\\", "/").lstrip("/")
    stored_path = Path(stored_value.replace("\\", "/"))

    candidates = []
    if stored_path.is_absolute():
        candidates.append(stored_path)
    else:
        backend_root = Path(__file__).resolve().parents[5]
        candidates.extend((
            _assignment_storage_root() / normalized,
            Path.cwd() / normalized,
            backend_root / normalized,
            backend_root.parent / normalized,
        ))

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


@router.get("/download/{lms_assignment_id}")
def download_assignment_document(
    lms_assignment_id: int,
    student_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    """Download a faculty attachment mapped to the requesting student."""
    assignment = db.execute(text("""
        SELECT a.file_name, a.file_path
        FROM lms_manage_assignment a
        JOIN lms_map_assignment_to_students m
          ON m.lms_assignment_id = a.lms_assignment_id
        WHERE a.lms_assignment_id = :lms_assignment_id
          AND m.ssd_id = :student_id
        LIMIT 1
    """), {
        "lms_assignment_id": lms_assignment_id,
        "student_id": student_id,
    }).mappings().first()

    if assignment is None:
        raise HTTPException(404, "Assignment document not found")

    file_name = Path(assignment["file_name"] or "").name
    stored_value = str(assignment["file_path"] or "").strip()
    if not file_name or not stored_value:
        raise HTTPException(404, "No document is attached to this assignment")

    file_path = _resolve_assignment_file(stored_value)
    if file_path is None:
        raise HTTPException(404, "Assignment document is missing from storage")

    return FileResponse(
        path=file_path,
        filename=file_name,
        media_type="application/octet-stream",
    )


@router.post(
    "/student-upload/{map_assignment_student_id}",
    response_model=StudentAssignmentUploadResponse,
)
def upload_student_assignment(
    map_assignment_student_id: int,
    student_id: int = Form(..., gt=0),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    assignment = db.execute(text("""
        SELECT m.map_assignment_student_id,
               COALESCE(m.accept_rework_flag, 0) AS accept_rework_flag,
               a.due_date,
               s.usno
        FROM lms_map_assignment_to_students m
        JOIN lms_manage_assignment a
          ON a.lms_assignment_id = m.lms_assignment_id
        JOIN iems_students s ON s.student_id = m.ssd_id
        WHERE m.map_assignment_student_id = :map_assignment_student_id
          AND m.ssd_id = :student_id
    """), {
        "map_assignment_student_id": map_assignment_student_id,
        "student_id": student_id,
    }).mappings().first()

    if assignment is None:
        raise HTTPException(404, "Assignment is not mapped to this student")

    if assignment["accept_rework_flag"] in (1, 2):
        raise HTTPException(409, "Assignment is already uploaded or accepted")

    due_day = _parse_database_date(assignment["due_date"])
    if due_day is not None and due_day < datetime.now().date():
        raise HTTPException(400, "The assignment due date has passed")

    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()
    if not original_name or extension not in ALLOWED_STUDENT_ASSIGNMENT_EXTENSIONS:
        raise HTTPException(
            400,
            "Invalid file format. Allowed formats: jpeg, jpg, pdf, doc, docx, xls, xlsx, png",
        )

    contents = file.file.read(MAX_STUDENT_ASSIGNMENT_SIZE + 1)
    if not contents:
        raise HTTPException(400, "The selected file is empty")
    if len(contents) > MAX_STUDENT_ASSIGNMENT_SIZE:
        raise HTTPException(400, "File size must not exceed 5MB")

    now = datetime.now()
    relative_directory = Path(
        "uploads", "ionlms", "upload_assignment_material",
        str(now.year), now.strftime("%W"),
    )
    physical_directory = _assignment_storage_root() / relative_directory
    physical_directory.mkdir(parents=True, exist_ok=True)
    stored_name = (
        f"{int(now.timestamp())}_{uuid4().hex[:8]}_"
        f"{assignment['usno']}_{original_name}"
    )
    relative_file_path = relative_directory / stored_name
    physical_file_path = physical_directory / stored_name

    try:
        physical_file_path.write_bytes(contents)
        db.execute(text("""
            UPDATE lms_map_assignment_to_students
            SET file_name = :file_name,
                file_path = :file_path,
                seen_on = :seen_on,
                accept_rework_flag = 1
            WHERE map_assignment_student_id = :map_assignment_student_id
              AND ssd_id = :student_id
        """), {
            "file_name": original_name,
            "file_path": relative_file_path.as_posix(),
            "seen_on": now,
            "map_assignment_student_id": map_assignment_student_id,
            "student_id": student_id,
        })
        db.commit()
    except Exception:
        db.rollback()
        physical_file_path.unlink(missing_ok=True)
        raise HTTPException(500, "Unable to save the assignment document")
    finally:
        file.file.close()

    return {
        "status": True,
        "message": "Assignment uploaded successfully",
        "file_name": original_name,
        "file_path": relative_file_path.as_posix(),
    }

# Use the upload mapping, as in CodeIgniter: an assignment need not have been
# shared with a student yet to appear in the assignment dropdown.
ASSIGNMENTS_SQL = """
    SELECT a.lms_assignment_id AS value, a.assignment_name AS label
    FROM lms_manage_assignment a
    WHERE a.crs_id = :course_id AND a.semester_id = :semester_id
      AND a.academic_batch_id = :academic_batch_id
      AND EXISTS (
        SELECT 1 FROM lms_map_assignment_upload upload
        WHERE upload.lms_assignment_id = a.lms_assignment_id
          AND upload.section_id = :section_id
      )
"""


def parameters(data):
    return data.model_dump() if hasattr(data, "model_dump") else data.dict()


def assignment_details(db, data):
    assignment = db.execute(text(ASSIGNMENTS_SQL + " AND a.lms_assignment_id = :assignment_id"),
                            parameters(data)).mappings().first()
    if assignment is None:
        raise HTTPException(404, "Assignment does not belong to the selected filters")
    return assignment


def report_rows(db, data):
    # Current IEMS keeps the education-system switch on the course. Section IDs
    # in assignment upload/topic APIs are CUDOS master-type IDs; students store
    # section names. Course enrollment uses the parent section for a batch.
    query = text("""
        SELECT m.map_assignment_student_id AS id,
               s.usno AS student_usn,
               COALESCE(NULLIF(TRIM(CONCAT_WS(' ', NULLIF(s.first_name, ''),
                   NULLIF(s.middle_name, ''), NULLIF(s.last_name, ''))), ''),
                   NULLIF(TRIM(s.name), ''), s.usno) AS student_name,
               m.secured_marks
        FROM lms_map_assignment_to_students m
        JOIN iems_students s ON s.student_id = m.ssd_id
        JOIN iems_courses c ON c.crs_id = :course_id
        JOIN cudos_master_type_details section ON section.mt_details_id = :section_id
        WHERE m.lms_assignment_id = :assignment_id
          AND (
            (COALESCE(c.edu_sys_flag, 0) = 0
             AND s.academic_batch_id = :academic_batch_id
             AND s.section = section.mt_details_name)
            OR (c.edu_sys_flag = 1 AND EXISTS (
                SELECT 1 FROM cudos_map_courseto_student enrollment
                WHERE enrollment.student_id = s.student_id
                  AND enrollment.crs_id = :course_id
                  AND enrollment.semester_id = :semester_id
                  AND (enrollment.academic_batch_id = :academic_batch_id
                       OR s.academic_batch_id = :academic_batch_id)
                  AND enrollment.section_id = COALESCE(NULLIF(section.parent_id, 0), section.mt_details_id)
            ))
          )
        ORDER BY s.usno, s.student_id, m.map_assignment_student_id
    """)
    return [dict(row) for row in db.execute(query, parameters(data)).mappings().all()]


@router.post("/assignment_list")
def get_assignment_list(data: AssignmentListRequest, db: Session = Depends(get_db)):
    rows = db.execute(text(ASSIGNMENTS_SQL + " ORDER BY a.lms_assignment_id"), parameters(data)).mappings().all()
    return {"status": True, "data": [dict(row) for row in rows]}


@router.post("/report")
def get_student_assignment_report(data: StudentAssignmentReportRequest, db: Session = Depends(get_db)):
    assignment_details(db, data)
    return {"status": True, "data": report_rows(db, data)}


def make_workbook(rows, assignment_name):
    wb = Workbook()
    ws = wb.active
    ws.title = "Assignment Report"
    india = timezone(timedelta(hours=5, minutes=30))
    ws.append(["Date of Export Report", datetime.now(india).strftime("%d-%m-%Y")])
    ws.append(["Assignment Name", assignment_name])
    ws.append(["USNO", "Student Name", "Marks"])
    for row in rows:
        ws.append([row["student_usn"], row["student_name"], row["secured_marks"]])
    # Names and identifiers are literal strings, including values beginning '='.
    for row in ws:
        for cell in row:
            if isinstance(cell.value, str):
                cell.data_type = "s"
    for column, width in (("A", 24), ("B", 40), ("C", 12)):
        ws.column_dimensions[column].width = width
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


@router.post("/export")
def export_assignment_report(data: StudentAssignmentReportRequest, db: Session = Depends(get_db)):
    assignment = assignment_details(db, data)
    stream = make_workbook(report_rows(db, data), assignment["label"])
    return StreamingResponse(stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="assignment_report_{data.assignment_id}.xlsx"'})
