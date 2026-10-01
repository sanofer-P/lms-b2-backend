from typing import Optional, List, Union
from pydantic import BaseModel


class DepartmentItem(BaseModel):
    dept_id: int
    dept_name: str


class ProgramItem(BaseModel):
    pgm_id: int
    pgm_title: str
    pgm_acronym: str


class CurriculumItem(BaseModel):
    crclm_id: int
    crclm_name: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None


class SemesterItem(BaseModel):
    semester_id: int
    semester: Optional[int] = None
    semester_desc: str


class MentorListMenteeItem(BaseModel):
    student_id: int
    student_name: str
    student_usn: str
    student_email: Optional[str] = None


class MentorMenteeRecord(BaseModel):
    group_mentor_id: int
    mentor_id: int
    mentor_name: str
    mentor_email: Optional[str] = None
    mentor_dept: Optional[str] = None
    group_title: Optional[str] = None
    mentees: List[MentorListMenteeItem]


class SendMessageRequest(BaseModel):
    mentee_id: Optional[int] = None
    comment: Optional[str] = None
    attachment: Optional[str] = None
 

class OptionCreateCustom(BaseModel):
    questionnaire_options_id: Optional[int] = None
    que_option: str
    specify_flag: bool = False


class QuestionCreateCustom(BaseModel):
    questionnaire_que_id: Optional[int] = None
    que_type_id: int
    que_no: int
    question: str
    questionnaire_type_id: int
    que_is_mandatory: bool = True
    options: List[Union[str, OptionCreateCustom]] = []


class QuestionnaireSaveCustom(BaseModel):
    questionnaire_id: Optional[int] = None
    questionnaire_name: str
    message_to_mentees: Optional[str] = None
    access_level: int = 0
    parent_id: Optional[int] = None
    questions: List[QuestionCreateCustom]
