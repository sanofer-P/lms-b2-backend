from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, PositiveInt


class AssignmentListRequest(BaseModel):
    course_id: PositiveInt
    semester_id: PositiveInt
    academic_batch_id: PositiveInt
    section_id: PositiveInt


class StudentAssignmentReportRequest(AssignmentListRequest):
    assignment_id: PositiveInt


class DropdownOption(BaseModel):
    value: int
    label: str

    model_config = ConfigDict(from_attributes=True)


class DropdownListResponse(BaseModel):
    status: bool
    data: list[DropdownOption]


class StudentAssignmentItem(BaseModel):
    map_assignment_student_id: int
    lms_assignment_id: int
    ssd_id: int
    student_usn: str
    student_file_name: Optional[str] = None
    student_file_path: Optional[str] = None
    seen_on: Optional[datetime | str] = None
    accept_rework_flag: Optional[int] = None
    secured_marks: Optional[float] = None
    remark: Optional[str] = None
    assignment_justification: Optional[str] = None
    current_comments: Optional[str] = None
    assignment_name: str
    additional_info: Optional[str] = None
    assignment_file_name: Optional[str] = None
    assignment_file_path: Optional[str] = None
    issue_date: Optional[date | str] = None
    due_date: Optional[date | str] = None
    crclm_id: int
    crclm_term_id: int
    crs_id: int
    topic_id: Optional[int] = None
    topic_title: Optional[str] = None
    section_name: Optional[str] = None
    crs_code: Optional[str] = None
    crs_title: Optional[str] = None
    crclm_name: Optional[str] = None
    term_name: Optional[str] = None
    assignment_created_date: Optional[datetime] = None
    assignment_modified_date: Optional[datetime] = None
    update_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class StudentAssignmentListResponse(BaseModel):
    status: bool
    data: list[StudentAssignmentItem]


class StudentAssignmentUploadResponse(BaseModel):
    status: bool
    message: str
    file_name: str
    file_path: str
