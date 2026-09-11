from pydantic import BaseModel
from typing import Optional


class AddCrossDeptMentorPayload(BaseModel):
    mentor_user_id: int
    mentor_dept_id: int
    curriculum_ids: list[int]


class UpdateCrossDeptMentorPayload(BaseModel):
    assigned_dept_id: int
    curriculum_ids: list[int]
