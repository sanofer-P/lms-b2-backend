from datetime import date, time
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class CourseTypeLimitSave(BaseModel):
    crs_type_id: int
    crs_type_total: Decimal = Field(ge=0)
    stud_min_crs_enroll: Decimal = Field(ge=0)
    stud_max_crs_enroll: Decimal = Field(ge=0)

    @model_validator(mode="after")
    def validate_limits(self):
        if self.stud_min_crs_enroll > self.stud_max_crs_enroll:
            raise ValueError("Minimum credits cannot exceed maximum credits")
        if self.stud_max_crs_enroll > self.crs_type_total:
            raise ValueError("Maximum credits cannot exceed the course-type total")
        return self


class RegistrationSetupSave(BaseModel):
    academic_batch_id: int
    semester_id: int
    enroll_start_date: date
    enroll_start_time: time
    enroll_end_date: date
    enroll_end_time: time
    total_crs_enroll: Decimal = Field(gt=0)
    own_crclm_elective: int = Field(ge=0)
    other_crclm_elective: int = Field(ge=0)
    course_limits: list[CourseTypeLimitSave] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_registration_window(self):
        if (self.enroll_end_date, self.enroll_end_time) <= (
            self.enroll_start_date,
            self.enroll_start_time,
        ):
            raise ValueError("Registration end date and time must be after the start date and time")
        if sum(item.stud_min_crs_enroll for item in self.course_limits) > self.total_crs_enroll:
            raise ValueError("The total of minimum credits cannot exceed total credits")
        return self
