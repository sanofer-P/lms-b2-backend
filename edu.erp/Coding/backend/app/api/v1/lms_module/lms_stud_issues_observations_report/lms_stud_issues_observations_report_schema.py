from pydantic import BaseModel
from typing import List

class StudentAgreeSchema(BaseModel):
    lms_isnob_id: int

class StudentAgreeSchema(BaseModel):
    lms_isnob_id: int

class TermDetail(BaseModel):
    crclm_id: int
    crclm_name: str
    crclm_term_id: int
    term_name: str

class CurriculumGroup(BaseModel):
    crclm_id: int
    crclm_name: str
    terms: List[TermDetail]

    class Config:
        orm_mode = True