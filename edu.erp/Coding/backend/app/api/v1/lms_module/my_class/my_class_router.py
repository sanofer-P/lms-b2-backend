from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date, datetime
from typing import Optional
from app.core.database import get_db

from .my_class_schema import *

router = APIRouter()

@router.get("/dropdowns", response_model=StudentDropdownResponse)
def get_student_dropdowns(
    student_id: int = Query(...),
    academic_batch_id: Optional[int] = Query(None),
    semester_id: Optional[int] = Query(None),
    course_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    # -------------------------
    # CURRICULUM
    # -------------------------
    curriculum_query = """
        SELECT ab.academic_batch_id, ab.academic_batch_desc AS batch_name
        FROM iems_students s
        JOIN iems_academic_batch ab ON s.academic_batch_id = ab.academic_batch_id
        WHERE s.student_id = :student_id
    """
    curriculum = db.execute(text(curriculum_query), {"student_id": student_id}).fetchall()

    # -------------------------
    # TERMS (SEMESTERS)
    # -------------------------
    terms = []
    if academic_batch_id:
        term_query = """
            SELECT DISTINCT
                sem.semester_id,
                sem.semester_desc AS semester_name
            FROM iems_semester sem
            WHERE sem.academic_batch_id = :academic_batch_id
            ORDER BY sem.semester_id
        """
        terms = db.execute(
            text(term_query),
            {"academic_batch_id": academic_batch_id}
        ).fetchall()

    # -------------------------
    # COURSES + SECTIONS
    # -------------------------
    course_section = []
    if academic_batch_id and semester_id:
        cs_query = """
            SELECT DISTINCT
                c.crs_id AS course_id,
                c.crs_code AS course_code,
                c.crs_title AS course_title,
                sec.id AS section_id,
                sec.section AS section_name
            FROM iems_courses c
            JOIN cudos_map_courseto_student mcs
              ON mcs.crs_id = c.crs_id
             AND mcs.academic_batch_id = c.academic_batch_id
             AND mcs.semester_id = mcs.semester_id
            JOIN iems_students stu
              ON stu.student_id = mcs.student_id
            JOIN iems_section sec
              ON sec.id = mcs.section_id
            WHERE c.academic_batch_id = :academic_batch_id
              AND mcs.semester_id = :semester_id
              AND mcs.student_id = :student_id
        """
        params = {
            "academic_batch_id": academic_batch_id,
            "semester_id": semester_id,
            "student_id": student_id,
        }

        if course_id:
            cs_query += " AND c.crs_id = :course_id"
            params["course_id"] = course_id

        cs_query += " ORDER BY c.crs_code, c.crs_title"
        course_section = db.execute(text(cs_query), params).fetchall()

    # Split courses & sections
    courses = []
    sections = []
    seen_courses = set()
    seen_sections = set()

    for row in course_section:
        if row.course_id not in seen_courses:
            courses.append({
                "course_id": row.course_id,
                "course_code": row.course_code,
                "course_title": row.course_title
            })
            seen_courses.add(row.course_id)

        if row.section_id not in seen_sections:
            sections.append({
                "section_id": row.section_id,
                "section_name": row.section_name
            })
            seen_sections.add(row.section_id)

    return {
        "curriculum": [
            {"academic_batch_id": c.academic_batch_id, "academic_batch_name": c.batch_name} 
            for c in curriculum
        ],
        "terms": [
            {"semester_id": t.semester_id, "semester_name": t.semester_name} 
            for t in terms
        ],
        "courses": courses,
        "sections": sections
    }

@router.get("/class-list")
def get_class_list(
    student_id: int,
    academic_batch_id: int,
    section_id: int,
    semester_id: int,
    selected_date: date,
    course_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    student = db.execute(
        text("""
            SELECT usno AS student_usn
            FROM iems_students
            WHERE student_id = :student_id
            LIMIT 1
        """),
        {"student_id": student_id}
    ).mappings().first()

    if not student or not student["student_usn"]:
        return {"classes": []}

    # CodeIgniter sets api_id to 1 when class_date is supplied.
    api_id = 1

    query = """
        SELECT
            lls.lls_id,
            lls.lesson_schedule_id,
            lls.crs_id AS course_id,
            c.crs_code AS course_code,
            c.crs_title AS course_title,
            lls.section_id,
            sec.section AS section_name,
            DATE(lls.actual_start_date) AS class_date,
            lls.start_time,
            lls.end_time,
            CAST(lms_fetch_timetable_topic_ids_map(lls.lls_id, :api_id) AS CHAR) AS topic_id,
            lms_fetch_timetable_topic_mapping_data(lls.lls_id, :api_id) AS topic_title,
            lms_fetch_tt_topic_portion_mapping_data(lls.lls_id, :api_id) AS portion_to_be_covered,
            CAST(lms_fetch_lls_bloom_ids(lls.lls_id) AS CHAR) AS bloom_ids,
            CAST(lms_fetch_lls_dlvry_mthd_ids(lls.lls_id) AS CHAR) AS delivery_method_ids,
            lms_fetch_ls_bloom_mapping(lls.lls_id) AS bloom_level,
            lms_fetch_ls_delivery_method_mapping(lls.lls_id) AS delivery_method,
            (
                SELECT ls.video_link
                FROM lms_lesson_schedule ls
                LEFT JOIN lms_ls_student_map lst ON lst.lls_id = ls.lls_id
                WHERE ls.lls_id = lls.lls_id
                    AND lst.student_usn = :student_usn
                LIMIT 1
            ) AS video_link,
            CASE lls.status
                WHEN 0 THEN 'Yet to start'
                WHEN 1 THEN 'In progress'
                WHEN 2 THEN 'Completed'
                ELSE 'Yet to start'
            END AS status
        FROM lms_lesson_schedule lls
        LEFT JOIN lms_ls_student_map st ON st.lls_id = lls.lls_id
        LEFT JOIN cudos_topic top ON top.topic_id = lls.topic_id
        LEFT JOIN topic_lesson_schedule tls
            ON tls.lesson_schedule_id = lls.lesson_schedule_id
        LEFT JOIN iems_courses c ON c.crs_id = lls.crs_id
        LEFT JOIN iems_section sec ON sec.id = lls.section_id
        WHERE lls.academic_batch_id = :academic_batch_id
            AND lls.semester_id = :semester_id
            AND lls.section_id = :section_id
            AND st.student_usn = :student_usn
            AND CAST(lls.actual_start_date AS CHAR) LIKE CONCAT('%', :selected_date, '%')
    """
    params = {
        "academic_batch_id": academic_batch_id,
        "semester_id": semester_id,
        "section_id": section_id,
        "student_usn": student["student_usn"],
        "selected_date": selected_date.isoformat(),
        "api_id": api_id,
    }

    if course_id:
        query += " AND lls.crs_id = :course_id"
        params["course_id"] = course_id

    query += " GROUP BY lls.lls_id ORDER BY lls.start_time, lls.end_time"
    result = db.execute(text(query), params).fetchall()

    return {
        "classes": [
            {
                "lls_id": r.lls_id,
                "lesson_schedule_id": r.lesson_schedule_id,
                "topic_id": r.topic_id,
                "course_id": r.course_id,
                "course_code": r.course_code,
                "course_name": r.course_title,
                "section_id": r.section_id,
                "section_name": r.section_name,
                "topic_title": r.topic_title,
                "portion_to_be_covered": r.portion_to_be_covered,
                "bloom_ids": r.bloom_ids,
                "delivery_method_ids": r.delivery_method_ids,
                "bloom_level": r.bloom_level,
                "delivery_method": r.delivery_method,
                "status": r.status,
                "class_date": r.class_date,
                "start_time": r.start_time,
                "end_time": r.end_time,
                "video_link": r.video_link
            } for r in result
        ]
    }

# # -------------------------------
# # CRUD OPERATIONS
# # -------------------------------

# @router.post("/create-class")
# def create_class(request: ClassCreateRequest, db: Session = Depends(get_db)):
#     try:
#         # Insert into lms_lesson_schedule
#         query = """
#             INSERT INTO lms_lesson_schedule 
#             (academic_batch_id, semester_id, crs_id, section_id, plan_date, start_time, end_time, video_link, status)
#             VALUES (:batch_id, :sem_id, :crs_id, :sec_id, :p_date, :s_time, :e_time, :v_link, 1)
#         """
#         result = db.execute(text(query), {
#             "batch_id": request.academic_batch_id,
#             "sem_id": request.semester_id,
#             "crs_id": request.course_id,
#             "sec_id": request.section_id,
#             "p_date": request.plan_date,
#             "s_time": request.start_time,
#             "e_time": request.end_time,
#             "v_link": request.video_link
#         })
#         lls_id = result.lastrowid
        
#         # Sync lesson_schedule_id column with lls_id if needed
#         db.execute(text("UPDATE lms_lesson_schedule SET lesson_schedule_id = :id WHERE lls_id = :id"), {"id": lls_id})
        
#         # If topic_id provided, also map it in topic_lesson_schedule
#         if request.topic_id:
#             db.execute(text("""
#                 INSERT INTO topic_lesson_schedule (lesson_schedule_id, topic_id, academic_batch_id, course_id, semester_id, conduction_date)
#                 VALUES (:ls_id, :t_id, :batch_id, :crs_id, :sem_id, :c_date)
#             """), {
#                 "ls_id": lls_id,
#                 "t_id": request.topic_id,
#                 "batch_id": request.academic_batch_id,
#                 "crs_id": request.course_id,
#                 "sem_id": request.semester_id,
#                 "c_date": request.plan_date
#             })
            
#         db.commit()
#         return {"success": True, "message": "Class created successfully", "lesson_schedule_id": lls_id}
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=str(e))

# @router.put("/update-class/{lls_id}")
# def update_class(lls_id: int, request: ClassUpdateRequest, db: Session = Depends(get_db)):
#     try:
#         # Update lms_lesson_schedule
#         update_ls_query = "UPDATE lms_lesson_schedule SET "
#         ls_params = {"lls_id": lls_id}
#         ls_updates = []
        
#         if request.plan_date:
#             ls_updates.append("plan_date = :p_date")
#             ls_params["p_date"] = request.plan_date
#         if request.start_time:
#             ls_updates.append("start_time = :s_time")
#             ls_params["s_time"] = request.start_time
#         if request.end_time:
#             ls_updates.append("end_time = :e_time")
#             ls_params["e_time"] = request.end_time
#         if request.video_link is not None:
#             ls_updates.append("video_link = :v_link")
#             ls_params["v_link"] = request.video_link
            
#         if ls_updates:
#             update_ls_query += ", ".join(ls_updates) + " WHERE lls_id = :lls_id"
#             db.execute(text(update_ls_query), ls_params)

#         # Update topic_lesson_schedule / status
#         if request.topic_id is not None or request.status is not None:
#             # Check if entry exists using lls_id as lesson_schedule_id
#             exists = db.execute(text("SELECT 1 FROM topic_lesson_schedule WHERE lesson_schedule_id = :ls_id"), {"ls_id": lls_id}).fetchone()
            
#             if exists:
#                 tls_updates = []
#                 tls_params = {"ls_id": lls_id}
#                 if request.topic_id is not None:
#                     tls_updates.append("topic_id = :t_id")
#                     tls_params["t_id"] = request.topic_id
#                 if request.status == "Completed":
#                     tls_updates.append("actual_delivery_date = :a_date")
#                     tls_params["a_date"] = date.today()
                
#                 if tls_updates:
#                     db.execute(text("UPDATE topic_lesson_schedule SET " + ", ".join(tls_updates) + " WHERE lesson_schedule_id = :ls_id"), tls_params)
#             elif request.topic_id:
#                 # Need batch/course for new insert in topic_lesson_schedule
#                 ls_info = db.execute(text("SELECT academic_batch_id, crs_id, semester_id FROM lms_lesson_schedule WHERE lls_id = :lls_id"), {"lls_id": lls_id}).fetchone()
#                 if ls_info:
#                     db.execute(text("""
#                         INSERT INTO topic_lesson_schedule (lesson_schedule_id, topic_id, academic_batch_id, course_id, semester_id, conduction_date)
#                         VALUES (:ls_id, :t_id, :batch_id, :crs_id, :sem_id, :c_date)
#                     """), {
#                         "ls_id": lls_id,
#                         "t_id": request.topic_id,
#                         "batch_id": ls_info.academic_batch_id,
#                         "crs_id": ls_info.crs_id,
#                         "sem_id": ls_info.semester_id,
#                         "c_date": date.today()
#                     })

#         db.commit()
#         return {"success": True, "message": "Class updated successfully"}
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=str(e))

# @router.delete("/delete-class/{lls_id}")
# def delete_class(lls_id: int, db: Session = Depends(get_db)):
#     try:
#         # Delete from dependent tables first
#         db.execute(text("DELETE FROM topic_lesson_schedule WHERE lesson_schedule_id = :ls_id"), {"ls_id": lls_id})
#         db.execute(text("DELETE FROM lms_map_portion_ls WHERE lesson_schedule_id = :ls_id"), {"ls_id": lls_id})
#         # Delete from main table
#         db.execute(text("DELETE FROM lms_lesson_schedule WHERE lls_id = :lls_id"), {"lls_id": lls_id})
        
#         db.commit()
#         return {"success": True, "message": "Class deleted successfully"}
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(status_code=500, detail=str(e))
