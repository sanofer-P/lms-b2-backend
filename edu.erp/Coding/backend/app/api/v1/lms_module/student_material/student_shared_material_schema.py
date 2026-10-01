from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CurriculumOption(BaseModel):
    id: int
    name: str


class TermOption(BaseModel):
    id: int
    name: str


class CourseOption(BaseModel):
    id: int
    name: str
    section_id: int


class ClassProgress(BaseModel):
    mat_id: int
    portion_count: int = 0
    completed_count: int = 0


class SharedMaterialRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mat_id: int
    document_name: str = ""
    file_name: Optional[str] = None
    url_flag: int = 0
    before_after_class_flag: int = 1
    license_flag: Optional[int] = None
    file_path: Optional[str] = None
    created_date: Optional[datetime] = None
    description: Optional[str] = None
    section_id: Optional[int] = None
    update_cnt: int = 0
    topic_title: Optional[str] = None
    topic_name: Optional[str] = None
    topic_id: Optional[str] = None
    academic_batch_id: int
    semester_id: int
    crs_id: int
    crs_title: Optional[str] = None
    crs_code: Optional[str] = None
    portion_count: int = 0
    completed_count: int = 0
    can_download: bool = False


class MaterialListResponse(BaseModel):
    status: bool
    material_list: list[SharedMaterialRow] = Field(default_factory=list)
    class_data: list[ClassProgress] = Field(default_factory=list)
