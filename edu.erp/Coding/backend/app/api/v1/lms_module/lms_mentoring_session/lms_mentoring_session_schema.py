from datetime import date, time
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List

class SessionDateCreate(BaseModel):

    sub_group_date_id: Optional[int] = None

    start_date: date
    end_date: date

    start_time: time
    end_time: time

class SubGroupCreate(BaseModel):

    sub_group_id: Optional[int] = None

    sub_group_name: str

    location: str

    dates: List[SessionDateCreate]

    mentee_ids: List[int]

class MentoringSessionCreate(BaseModel):

    academic_batch_id: int

    mentors_group_id: int

    semester_id: int

    session_agenda: str

    sub_groups: List[SubGroupCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_session(self):
        seen_mentees = set()
        for subgroup in self.sub_groups:
            if not subgroup.dates:
                raise ValueError(f"{subgroup.sub_group_name} must contain at least one date slot")
            if not subgroup.mentee_ids:
                raise ValueError(f"{subgroup.sub_group_name} must contain at least one mentee")
            duplicate_ids = seen_mentees.intersection(subgroup.mentee_ids)
            if duplicate_ids:
                raise ValueError(
                    f"Mentees cannot be assigned to more than one sub-group: {sorted(duplicate_ids)}"
                )
            seen_mentees.update(subgroup.mentee_ids)
        return self


class SessionStatusUpdate(BaseModel):
    sub_group_date_id: int
    status: int = Field(ge=0, le=4)

class GroupCommentCreate(BaseModel):
    schedule_id: int
    comment: str
    attachment: Optional[str] = None

class IndividualCommentCreate(BaseModel):
    schedule_id: int
    mentee_id: int
    comment: str
    attachment: Optional[str] = None


class QuestionnaireResponseRequest(BaseModel):
    schedule_id: int
    student_id: int


class SessionMenteeRequest(BaseModel):
    schedule_id: int
    sub_group_id: Optional[int] = None

class MenteeResponseRequest(BaseModel):
    schedule_id: int
    student_id: int

class SaveGenericCommentRequest(BaseModel):
    schedule_id: int
    comment: str
    suggestion_type: int = 0
    user_type: int = 0

    attachment: Optional[str] = None

class SaveIndividualCommentRequest(BaseModel):
    schedule_id: int
    mentee_id: int
    comment: str
    attachment: Optional[str] = None

    suggestion_type: int = 0

    # 1 Faculty
    # 2 Student
    from_user_type: int = 1

class GroupCommentRequest(BaseModel):
    schedule_id: int

class IndividualCommentRequest(BaseModel):
    schedule_id: int
    mentee_id: int

class MenteeResponseRequest(BaseModel):
    student_id: int
    schedule_id: int
