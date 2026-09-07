from pydantic import BaseModel, PositiveInt


class AssignmentListRequest(BaseModel):
    course_id: PositiveInt
    semester_id: PositiveInt
    academic_batch_id: PositiveInt
    section_id: PositiveInt


class StudentAssignmentReportRequest(AssignmentListRequest):
    assignment_id: PositiveInt
