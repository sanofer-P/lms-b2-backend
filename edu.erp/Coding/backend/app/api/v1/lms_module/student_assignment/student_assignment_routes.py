"""Assignment reports scoped to the selected batch, semester, course and section."""
from datetime import datetime, timedelta, timezone
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.utils.auth_helper import get_current_user
from .student_assignment_schema import AssignmentListRequest, StudentAssignmentReportRequest

router = APIRouter(tags=["Student Assignment"], dependencies=[Depends(get_current_user)])

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
