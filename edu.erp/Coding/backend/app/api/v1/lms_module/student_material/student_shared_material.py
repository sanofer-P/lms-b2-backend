from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.utils.auth_helper import get_current_user
from app.api.v1.lms_module.student_material.student_shared_material_schema import (
    ClassProgress,
    CourseOption,
    CurriculumOption,
    MaterialListResponse,
    SharedMaterialRow,
    TermOption,
)

router = APIRouter()

# The CodeIgniter database stores relative uploaded paths here. Set this to the
# same upload root used by the faculty material-upload API.
UPLOAD_ROOT = Path("uploads").resolve()


def _value(user: Any, *names: str) -> Any:
    for name in names:
        value = user.get(name) if isinstance(user, dict) else getattr(user, name, None)
        if value not in (None, ""):
            return value
    return None


def _student(db: Session, current_user: Any) -> dict:
    """Resolve the logged-in user to iems_students without trusting FE IDs."""
    username = _value(current_user, "username", "user_name", "sub", "usno", "regno")
    org_id = _value(current_user, "org_id", "organization_id")
    user_id = _value(current_user, "id", "user_id")

    row = db.execute(text("""
        SELECT s.student_id, s.usno, s.regno, s.academic_batch_id,
               s.semester_id, s.section_id, s.org_id
        FROM iems_students s
        LEFT JOIN iems_users u
          ON u.username IN (s.usno, s.regno, s.college_id)
        WHERE (:username IS NOT NULL AND :username IN (s.usno, s.regno, s.college_id))
           OR (:user_id IS NOT NULL AND u.id = :user_id)
        ORDER BY CASE WHEN s.org_id = :org_id THEN 0 ELSE 1 END
        LIMIT 1
    """), {"username": username, "user_id": user_id, "org_id": org_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Student profile is not mapped to this user")
    return dict(row)


def _ensure_enrollment(db: Session, student_id: int, academic_batch_id: int,
                       semester_id: int | None = None, crs_id: int | None = None) -> None:
    row = db.execute(text("""
        SELECT 1 FROM cudos_map_courseto_student
        WHERE student_id = :student_id
          AND academic_batch_id = :academic_batch_id
          AND (:semester_id IS NULL OR semester_id = :semester_id)
          AND (:crs_id IS NULL OR crs_id = :crs_id)
          AND COALESCE(status, 1) = 1
        LIMIT 1
    """), locals()).first()
    if not row:
        raise HTTPException(403, "The selected academic data is not mapped to this student")

@router.get("/curriculums", response_model=list[CurriculumOption])
def curriculums(
    db: Session = Depends(get_db),
    # current_user: Any = Depends(get_current_user),
):
    # student = _student(db, current_user)

    params = {
        "student_id": 1,
    }

    rows = db.execute(
        text("""
            SELECT DISTINCT
                ab.academic_batch_id AS id,
                COALESCE(
                    NULLIF(ab.academic_batch_desc, ''),
                    ab.academic_batch_code
                ) AS name
            FROM iems_academic_batch AS ab
            INNER JOIN (
                SELECT academic_batch_id
                FROM iems_students
                WHERE student_id = :student_id

                UNION

                SELECT academic_batch_id
                FROM cudos_map_courseto_student
                WHERE student_id = :student_id
                  AND COALESCE(status, 1) = 1
            ) AS mapped_batch
                ON mapped_batch.academic_batch_id =
                   ab.academic_batch_id
            WHERE COALESCE(ab.status, 1) = 1
            ORDER BY name
        """),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]

@router.get("/terms", response_model=list[TermOption])
def terms(
    academic_batch_id: int,
    db: Session = Depends(get_db),
    # current_user: Any = Depends(get_current_user),
):
    student = 1

    _ensure_enrollment(
        db,
        int(student),
        academic_batch_id,
    )

    params = {
        "student_id": student,
        "academic_batch_id": academic_batch_id,
    }

    rows = db.execute(
        text("""
            SELECT DISTINCT
                sem.semester_id AS id,
                COALESCE(
                    NULLIF(sem.term_name, ''),
                    NULLIF(sem.semester_desc, ''),
                    sem.semester_code
                ) AS name
            FROM iems_semester AS sem
            INNER JOIN cudos_map_courseto_student AS mcs
                ON mcs.semester_id = sem.semester_id
                AND mcs.academic_batch_id =
                    sem.academic_batch_id
            WHERE mcs.student_id = :student_id
              AND sem.academic_batch_id =
                  :academic_batch_id
              AND COALESCE(mcs.status, 1) = 1
              AND COALESCE(sem.status, 1) = 1
            ORDER BY sem.semester_id
        """),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]


@router.get("/courses", response_model=list[CourseOption])
def courses(academic_batch_id: int, semester_id: int, db: Session = Depends(get_db),
            #   current_user: Any = Depends(get_current_user)):
            ):
    student = 1
    _ensure_enrollment(db, student, academic_batch_id, semester_id)
    params = {
            "student_id": student,
            "academic_batch_id": academic_batch_id,
            "semester_id": semester_id
        }
    
    rows =  db.execute(text("""
        SELECT DISTINCT c.crs_id AS id,
               CONCAT_WS(' - ', c.crs_code, c.crs_title) AS name,
               mcs.section_id
        FROM cudos_map_courseto_student mcs
        JOIN iems_courses c ON c.crs_id = mcs.crs_id
        WHERE mcs.student_id = :student_id
          AND mcs.academic_batch_id = :academic_batch_id
          AND mcs.semester_id = :semester_id
          AND COALESCE(mcs.status, 1) = 1 AND COALESCE(c.status, 1) = 1
        ORDER BY c.crs_code, c.crs_title
    """), params).mappings().all()

    return [dict(row) for row in rows]

@router.get("/materials", response_model=MaterialListResponse)
def materials(academic_batch_id: int, semester_id: int, crs_id: int,
              db: Session = Depends(get_db), #   current_user: Any = Depends(get_current_user)):
              ):
    student = 1
    _ensure_enrollment(db, student, academic_batch_id, semester_id, crs_id)

    params = {
        "student_id": int(student),
        "academic_batch_id": academic_batch_id,
        "semester_id": semester_id,
        "crs_id": crs_id,
    }

    rows = db.execute(
        text("""
            SELECT
                cmu.mat_id,
                cmu.document_name,
                cmu.file_name,
                COALESCE(cmu.url_flag, 0) AS url_flag,
                COALESCE(cmu.before_after_class_flag, 0)
                    AS before_after_class_flag,
                cmu.license_flag,
                cmu.docment_url AS file_path,
                cmu.created_date,
                cmu.description,
                mcmu.section_id,
                COALESCE(cmu.update_cnt, 0) AS update_cnt,
                GROUP_CONCAT(
                    DISTINCT t.topic_title
                    SEPARATOR '</br>'
                ) AS topic_title,
                GROUP_CONCAT(
                    DISTINCT t.topic_title
                ) AS topic_name,
                GROUP_CONCAT(
                    DISTINCT t.topic_id
                ) AS topic_id,
                cmu.academic_batch_id AS academic_batch_id,
                cmu.semester_id AS semester_id,
                cmu.crs_id,
                c.crs_title,
                c.crs_code
            FROM lms_crs_material_upload AS cmu

            INNER JOIN lms_map_share_materials_to_student AS sms
                ON sms.mat_id = cmu.mat_id

            INNER JOIN iems_students AS student
                ON student.student_id = :student_id
                AND student.usno = sms.student_usn

            INNER JOIN lms_map_crs_material_upload AS mcmu
                ON mcmu.mat_id = cmu.mat_id

            LEFT JOIN cudos_topic AS t
                ON t.topic_id = mcmu.topic_id

            INNER JOIN iems_courses AS c
                ON c.crs_id = cmu.crs_id

            WHERE cmu.academic_batch_id = :academic_batch_id
            AND cmu.semester_id = :semester_id
            AND cmu.crs_id = :crs_id
            AND mcmu.section_id IN (
                SELECT mcs.section_id
                FROM cudos_map_courseto_student AS mcs
                WHERE mcs.student_id = :student_id
                    AND mcs.academic_batch_id =
                        :academic_batch_id
                    AND mcs.semester_id = :semester_id
                    AND mcs.crs_id = :crs_id
                    AND COALESCE(mcs.status, 1) = 1
            )

            GROUP BY
                cmu.mat_id,
                cmu.document_name,
                cmu.file_name,
                cmu.url_flag,
                cmu.before_after_class_flag,
                cmu.license_flag,
                cmu.docment_url,
                cmu.created_date,
                cmu.description,
                mcmu.section_id,
                cmu.update_cnt,
                cmu.academic_batch_id,
                cmu.semester_id,
                cmu.crs_id,
                c.crs_title,
                c.crs_code

            ORDER BY
                cmu.created_date DESC,
                cmu.mat_id DESC
        """),
        params,
    ).mappings().all()

    material_list = []

    for row in rows:
        item = dict(row)
        item["url_flag"] = int(item.get("url_flag") or 0)
        item["before_after_class_flag"] = int(
            item.get("before_after_class_flag") or 0
        )
        item["update_cnt"] = int(item.get("update_cnt") or 0)
        file_path = (item.get("file_path") or "").strip()

        # Show download when a document path or external URL exists.
        item["can_download"] = bool(file_path)
        material_list.append(item)

    return {
        "status": bool(material_list),
        "material_list": material_list,
        "class_data": [],
    }


@router.get("/download/{mat_id}/{file_index}")
def download_material(
    mat_id: int,
    file_index: int = 0,
    db: Session = Depends(get_db),
    # current_user: Any = Depends(get_current_user),
):
    student_id = 1  # Temporary testing value

    row = db.execute(
        text("""
            SELECT
                cmu.mat_id,
                cmu.document_name,
                cmu.file_name,
                cmu.docment_url,
                COALESCE(cmu.url_flag, 0) AS url_flag,
                COALESCE(
                    cmu.before_after_class_flag,
                    0
                ) AS before_after_class_flag,
                mcmu.section_id,
                GROUP_CONCAT(
                    DISTINCT mcmu.topic_id
                ) AS topic_id
            FROM lms_crs_material_upload AS cmu

            INNER JOIN lms_map_share_materials_to_student AS sms
                ON sms.mat_id = cmu.mat_id

            INNER JOIN iems_students AS student
                ON student.student_id = :student_id
                AND student.usno = sms.student_usn

            INNER JOIN lms_map_crs_material_upload AS mcmu
                ON mcmu.mat_id = cmu.mat_id

            INNER JOIN cudos_map_courseto_student AS mcs
                ON mcs.student_id = :student_id
                AND mcs.crs_id = cmu.crs_id
                AND mcs.academic_batch_id =
                    cmu.academic_batch_id
                AND mcs.semester_id =
                    cmu.semester_id
                AND mcs.section_id =
                    mcmu.section_id
                AND COALESCE(mcs.status, 1) = 1

            WHERE cmu.mat_id = :mat_id

            GROUP BY
                cmu.mat_id,
                cmu.document_name,
                cmu.file_name,
                cmu.docment_url,
                cmu.url_flag,
                cmu.before_after_class_flag,
                mcmu.section_id

            LIMIT 1
        """),
        {
            "mat_id": mat_id,
            "student_id": student_id,
        },
    ).mappings().first()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Shared material not found",
        )

    paths = [
        value.strip()
        for value in (row["docment_url"] or "").split(",")
        if value.strip()
    ]

    names = [
        value.strip()
        for value in (
            row["file_name"]
            or row["document_name"]
            or "material"
        ).split(",")
    ]

    if file_index < 0 or file_index >= len(paths):
        raise HTTPException(
            status_code=404,
            detail="Material file not found",
        )

    selected_path = paths[file_index]

    # Redirect only when it is a genuine external URL.
    if (
        int(row["url_flag"] or 0) == 1
        and selected_path.lower().startswith(
            ("http://", "https://")
        )
    ):
        return RedirectResponse(selected_path)

    relative_path = selected_path.replace("\\", "/").lstrip("/")

    if relative_path.startswith("uploads/"):
        relative_path = relative_path[len("uploads/"):]

    upload_root = Path("uploads").resolve()
    document_path = (upload_root / relative_path).resolve()

    if (
        upload_root not in document_path.parents
        or not document_path.is_file()
    ):
        raise HTTPException(
            status_code=404,
            detail="Material document is missing from storage",
        )

    filename = (
        names[file_index]
        if file_index < len(names)
        else document_path.name
    )

    return FileResponse(
        path=document_path,
        filename=filename,
    )