from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import logging
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.units import mm
from app.core.database import get_db
from .topic_coverage_schema import (
    CurriculumResponse, TermResponse, CourseResponse,
    CourseTopicsStatusResponse, CourseTopicStatusItem
)

router = APIRouter(tags=["Topic Coverage And Tracking"])
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 1. GET /curriculum  →  list of all curricula
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/curriculum", response_model=List[CurriculumResponse])
def get_curriculum(db: Session = Depends(get_db)):
    try:
        result = db.execute(text("""
            SELECT academic_batch_id AS id, academic_batch_desc AS name
            FROM iems_academic_batch
            WHERE status = 1
            ORDER BY academic_batch_id ASC
        """)).fetchall()
        return [{"id": r.id, "name": r.name} for r in result]
    except Exception as e:
        logger.error(f"Error fetching curriculum: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# 2. GET /terms/{curriculum_id}  →  terms for a curriculum
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/terms/{curriculum_id}", response_model=List[TermResponse])
def get_terms(curriculum_id: int, db: Session = Depends(get_db)):
    try:
        result = db.execute(text("""
            SELECT semester_id AS id,
                   CONCAT('Semester ', semester) AS name
            FROM iems_semester
            WHERE academic_batch_id = :curriculum_id
              AND status = 1
            ORDER BY semester
        """), {"curriculum_id": curriculum_id}).fetchall()

        return [{"id": r.id, "name": r.name} for r in result]

    except Exception as e:
        logger.error(f"Error fetching terms: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: determine topic status
#   Returns one of: "LS not added", "Not started", "In-progress", "Completed"
# ─────────────────────────────────────────────────────────────────────────────
def _get_topic_status(topic_id: int, mapping_id: Optional[int], db: Session) -> str:
    """
    Logic:
      - No mapping_id (not imported)         → "LS not added"
      - Has mapping, no schedules at all      → "Not started"
      - Has schedules, none have actual date  → "In-progress"
      - All schedules have actual date        → "Completed"
    """
    if not mapping_id:
        return "LS not added"

    # count total schedules for this mapping
    total = db.execute(text("""
        SELECT COUNT(*) FROM lms_lesson_schedule
        WHERE mapping_id = :mid
    """), {"mid": mapping_id}).scalar() or 0

    if total == 0:
        return "Not started"

    # count schedules that have an actual delivery date
    completed = db.execute(text("""
        SELECT COUNT(*) FROM lms_lesson_schedule
        WHERE mapping_id = :mid
        AND actual_delivery_date IS NOT NULL
    """), {"mid": mapping_id}).scalar() or 0

    if completed == total:
        return "Completed"
    return "In-progress"


STATUS_COLOR = {
    "LS not added": "blue",
    "Not started":  "red",
    "In-progress":  "orange",
    "Completed":    "green",
}


# ─────────────────────────────────────────────────────────────────────────────
# 3. GET /courses  →  section-wise courses with status
#    Query params: academic_batch_id, semester_id
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/courses")
def get_courses(
    academic_batch_id: int,
    semester_id: int,
    db: Session = Depends(get_db)
):
    try:
        # Sections belong to course-instructor assignments in Topic Management.
        # iems_section is not the section master used by these assignments.
        rows = db.execute(text("""
            SELECT DISTINCT m.section_id, sec.mt_details_name AS section,
                   c.crs_id, c.crs_code, c.crs_title
            FROM cudos_map_courseto_course_instructor m
            JOIN cudos_master_type_details sec ON sec.mt_details_id = m.section_id
            JOIN iems_courses c ON c.crs_id = m.crs_id
            JOIN iems_semester sem ON sem.semester_id = m.semester_id
                AND sem.academic_batch_id = m.academic_batch_id
            WHERE m.academic_batch_id = :batch_id
              AND m.semester_id = :sem_id
              AND c.academic_batch_id = m.academic_batch_id
              AND c.semester = sem.semester
            ORDER BY sec.mt_details_name, m.section_id, c.crs_code, c.crs_id
        """), {"batch_id": academic_batch_id, "sem_id": semester_id}).fetchall()

        sections = {}
        for row in rows:
            sections.setdefault(row.section_id, row.section)

        # ✅ STEP 2: MAP
        result = []

        for section_id, section_name in sections.items():
            section_data = {
                "section_id": section_id,
                "section": section_name,
                "courses": []
            }

            for c in rows:
                if c.section_id != section_id:
                    continue
                # Use the section-specific LMS portions used by Topic Management.
                coverage = db.execute(text("""
                    SELECT COUNT(DISTINCT m.topic_id) AS topics,
                           COUNT(DISTINCT p.mtp_id) AS schedules,
                           COUNT(DISTINCT CASE WHEN p.delivery_date IS NOT NULL
                                 THEN p.mtp_id END) AS completed,
                           COUNT(DISTINCT CASE WHEN p.mtp_id IS NULL
                                 THEN m.topic_id END) AS unscheduled_topics
                    FROM lms_map_instructor_topic m
                    LEFT JOIN lms_map_portion_ls p
                      ON p.topic_id = m.topic_id AND p.section_id = m.section_id
                    WHERE m.academic_batch_id = :batch_id
                      AND m.semester_id = :sem_id
                      AND m.crs_id = :course_id AND m.section_id = :section_id
                """), {"batch_id": academic_batch_id, "sem_id": semester_id,
                       "course_id": c.crs_id, "section_id": section_id}).one()
                if coverage.topics == 0:
                    status = "LS not added"
                elif coverage.schedules == 0:
                    status = "Not started"
                elif coverage.completed == coverage.schedules and coverage.unscheduled_topics == 0:
                    status = "Completed"
                else:
                    status = "In-progress"

                section_data["courses"].append({
                    "course_id": c.crs_id,
                    "course_code": c.crs_code,
                    "course_title": c.crs_title,
                    "instructor": "N/A",
                    "section": section_name,
                    "section_id": section_id,
                    "status": status,
                    "color": STATUS_COLOR.get(status, "blue")
                })

            result.append(section_data)

        return result

    except Exception as e:
        logger.exception("Error fetching topic coverage courses")
        raise HTTPException(status_code=500, detail="Unable to load topic coverage courses") from e
    
# ─────────────────────────────────────────────────────────────────────────────
# 4. GET /course-topics  →  all topics of a course+section with status & dates
#    Query params: course_id, section_id, academic_batch_id, semester_id
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/course-topics")
def get_course_topics(
    course_id: int,
    section_id: int,
    semester_id: int,
    db: Session = Depends(get_db)
):
    try:
        print("🔥 INPUT:", course_id, section_id, semester_id)

        topics = db.execute(text("""
            SELECT t.topic_id, t.topic_code, t.topic_title
            FROM cudos_topic t
            JOIN lms_map_instructor_topic m 
                ON m.topic_id = t.topic_id
            WHERE m.crs_id = :course_id
              AND m.section_id = :section_id
              AND m.semester_id = :semester_id
        """), {
            "course_id": course_id,
            "section_id": section_id,
            "semester_id": semester_id
        }).fetchall()

        print("🔥 TOPICS FOUND:", len(topics))

        result = []

        for t in topics:
            result.append({
                "topic_id": t.topic_id,
                "topic_code": t.topic_code,
                "topic_title": t.topic_title,
                "status": "Not started",
                "color": "red",
                "class_dates": []
            })

        return result

    except Exception as e:
        print("❌ ERROR:", str(e))
        return []
    
# ─────────────────────────────────────────────────────────────────────────────
# 5. GET /export-pdf  →  download PDF report
#    Query params: academic_batch_id, semester_id
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/export-pdf")
def export_topic_coverage_pdf(
    academic_batch_id: int,
    semester_id: int,
    db: Session = Depends(get_db)
):
    try:
        import io
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.pagesizes import A4
        from fastapi.responses import StreamingResponse
        from sqlalchemy import text

        # ✅ Curriculum & Term (SAFE)
        batch_name = db.execute(text("""
            SELECT academic_batch_desc 
            FROM iems_academic_batch 
            WHERE academic_batch_id = :id
        """), {"id": academic_batch_id}).scalar() or "N/A"

        sem_name = db.execute(text("""
            SELECT semester_desc 
            FROM iems_semester 
            WHERE semester_id = :id
        """), {"id": semester_id}).scalar() or "N/A"

        sections = get_courses(academic_batch_id, semester_id, db)
        grouped = {
            (section["section_id"], section["section"]): section["courses"]
            for section in sections
        }

        # ✅ PDF BUILD
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)

        styles = getSampleStyleSheet()
        elements = []

        # ✅ TITLE (MATCH IMAGE)
        elements.append(Paragraph(
            "<b><font size=14 color='red'>Topic Coverage and Tracking Report</font></b>",
            styles["Normal"]
        ))

        elements.append(Spacer(1, 10))

        # ✅ HEADER ROW (Curriculum + Term)
        header_table = Table([
            [f"Curriculum: {batch_name}", f"Term: {sem_name}"]
        ], colWidths=[250, 250])

        header_table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke)
        ]))

        elements.append(header_table)
        elements.append(Spacer(1, 10))

        # ✅ MAIN TABLE HEADER
        data = [[
            "Sl No",
            "Course Code and Course Title",
            "Faculty Name",
            "Coverage Status",
            "Remarks"
        ]]

        sl = 1

        # ✅ SECTION + COURSES
        for (_, section), courses in grouped.items():
            data.append([f"Section: {section}", "", "", "", ""])

            for c in courses:
                data.append([
                    str(sl),
                    f"{c['course_code']} - {c['course_title']}",
                    c["instructor"],
                    c["status"],
                    ""
                ])
                sl += 1

        # ✅ TABLE STYLE (MATCH YOUR IMAGE)
        table = Table(data, repeatRows=1)

        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),

            # Section highlight
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ]))

        elements.append(table)

        doc.build(elements)
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=Topic_Coverage_Report.pdf"}
        )

    except Exception as e:
        print("❌ PDF ERROR:", str(e))
        raise HTTPException(status_code=500, detail=str(e))