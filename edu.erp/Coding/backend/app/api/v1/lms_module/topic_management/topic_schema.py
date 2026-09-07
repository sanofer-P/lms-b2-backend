from datetime import date, time
from typing import Optional, List
from pydantic import BaseModel, Field

class TopicContext(BaseModel):
    academic_batch_id: int = Field(gt=0)
    semester_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    section_id: int = Field(gt=0)

class CourseListRequest(BaseModel):
    curriculum_id: Optional[int] = None
    academic_batch_id: Optional[int] = None
    semester_id: Optional[int] = None

class TopicListRequest(TopicContext):
    instructor_id: Optional[int] = None

class TopicCreateRequest(BaseModel):
    topic_code: str = Field(min_length=1, max_length=10)
    topic_title: str = Field(min_length=1, max_length=500)
    topic_content: Optional[str] = None
    academic_batch_id: int = Field(gt=0)
    semester_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    topic_hrs: Optional[str] = Field(default=None, max_length=8)
    num_of_sessions: int = Field(default=1, ge=1)

class NewTopicRequest(TopicCreateRequest):
    section_id: int = Field(gt=0)
    instructor_id: int = Field(gt=0)
    delivery_date: Optional[date] = None

class ImportTopicRequest(TopicContext):
    instructor_id: int = Field(gt=0)
    topic_ids: List[int] = Field(min_length=1)

ImportCudosTopicsRequest = ImportTopicRequest

class TopicAssignment(BaseModel):
    topic_id: int = Field(gt=0)
    instructor_ids: List[int] = Field(min_length=1, max_length=3)

class AssignTopicsRequest(TopicContext):
    assignments: List[TopicAssignment] = Field(min_length=1)

class UpdateInstructorRequest(BaseModel):
    course_instructor_id: Optional[int] = None
    instructor_id: Optional[int] = None

class ScheduleInput(BaseModel):
    session_number: int = Field(default=1, ge=1)
    portion_to_be_covered: str = ''
    conduction_date: Optional[date] = None
    actual_delivery_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None

class AddScheduleRequest(ScheduleInput):
    mapping_id: int = Field(gt=0)

class SavedSchedule(ScheduleInput):
    schedule_id: int

class SaveSchedulesRequest(BaseModel):
    mapping_id: int = Field(gt=0)
    schedules: List[SavedSchedule]
    instructor_ids: Optional[List[int]] = Field(default=None, min_length=1, max_length=3)

class ExtraClassRequest(BaseModel):
    mapping_id: int = Field(gt=0)
    class_date: date
    start_time: time
    end_time: time
    notes: str = ''

class BulkDeleteRequest(TopicContext):
    topic_ids: List[int] = Field(min_length=1)
