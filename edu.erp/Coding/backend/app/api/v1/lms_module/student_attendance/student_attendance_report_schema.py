from pydantic import BaseModel, ConfigDict, Field


class StudentAttendanceOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    value: str
    label: str
    semester_id: int | None = None
    semester_number: int | None = None


class StudentAttendanceSummaryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course: str
    present: int = 0
    total_classes: int = 0
    percentage: float = 0.0


class StudentAttendanceDaywiseRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course: str
    attendance: str
    attendance_document: str = ""
    attendance_document_url: str = ""
    document_status: str = ""
    attendance_date: str



class StudentAttendanceStudentRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    usn: str
    name: str
    present: int = 0
    absent: int = 0


class AttendanceClassDateDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_class_in_day: int = 0
    attendance_month: str
    week_day_name: str
    class_date: str
    crs_id: int
    crs_title: str
    crs_code: str
    crclm_term_id: int
    attended_class_in_day: int | str = "-"


class AttendanceScheduledClasses(BaseModel):
    scheduled_classes: int = 0


class AttendanceCoursePresent(BaseModel):
    attendance: int = 0


class AttendanceClassDateResponse(BaseModel):
    status: str
    class_list: list[list[AttendanceClassDateDetail]] = Field(default_factory=list)
    course_data: list[str] = Field(default_factory=list)
    crs_code_data: list[str] = Field(default_factory=list)
    course_id_data: list[int] = Field(default_factory=list)
    total_class_in_month: dict[str, AttendanceScheduledClasses] = Field(
        default_factory=dict
    )
    attended_class_in_month: dict[str, AttendanceCoursePresent] = Field(
        default_factory=dict
    )
    overall_classes_in_month: int = 0
    overall_attendance_in_month: int = 0
    attended_class_in_day: int | str = "-"


class AttendanceCourseClassDateRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    attendance_month: str
    week_day_name: str
    class_date: str
    course: str
    crs_id: int
    student_usn: str = ""
    present_count: int = 0
    absent_count: int = 0
    class_count: int = 0

class AttendanceUploadResponse(BaseModel):
    status: str
    message: str
    attendance_document_url: str = ""