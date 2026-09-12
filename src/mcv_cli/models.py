from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class AuthProvider(StrEnum):
    MCV = "mcv"
    PLATFORM = "platform"
    CHULA = "chula"
    GOOGLE = "google"


class StoredProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 2
    provider: AuthProvider = AuthProvider.PLATFORM
    cookies: dict[str, str] = Field(default_factory=dict, repr=False)


class User(BaseModel):
    model_config = ConfigDict(extra="allow")

    uid: str | int | None = None
    username: str | None = None
    name: str | None = None
    email: str | None = None
    account: dict[str, Any] | None = None


class Course(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    cv_cid: int
    course_no: str | None = Field(
        default=None,
        validation_alias=AliasChoices("course_no", "courseNo", "courseno"),
    )
    title: str | None = Field(
        default=None,
        validation_alias=AliasChoices("title", "name"),
    )
    icon: str | None = Field(
        default=None,
        validation_alias=AliasChoices("course_icon", "icon"),
    )
    year: str | int | None = None
    semester: str | int | None = None
    section: str | int | None = None
    role: str | None = None


ItemType = Literal["materials", "assignments"]


class Material(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    itemid: int
    cv_cid: int | None = None
    title: str | None = None
    status: int | str | None = None
    created: int | str | datetime | None = None
    changed: int | str | datetime | None = None
    description: str | None = None
    detail_url: str | None = None
    folder_id: str | None = None
    folder_name: str | None = None
    external_links: list[str] = Field(default_factory=list)
    thumbnail: str | None = None
    filepath: str | None = Field(
        default=None,
        validation_alias=AliasChoices("filepath", "file_path", "url"),
    )


class Assignment(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    itemid: int
    cv_cid: int | None = None
    title: str | None = None
    status: int | str | None = None
    created: int | str | datetime | None = None
    changed: int | str | datetime | None = None
    instruction: str | None = None
    detail_url: str | None = None
    submission_url: str | None = None
    is_group: bool | None = None
    submitted_at: str | None = None
    feedback: str | None = None
    external_links: list[str] = Field(default_factory=list)
    outdate: str | None = None
    duedate: str | None = None
    duetime: int | str | None = None


class MaterialFolder(BaseModel):
    folder_id: str
    name: str
    materials: list[Material] = Field(default_factory=list)


class Announcement(BaseModel):
    itemid: int
    cv_cid: int
    title: str
    posted: str | None = None
    detail_url: str | None = None
    body: str | None = None
    last_modified: str | None = None
    external_links: list[str] = Field(default_factory=list)


class MeetingRecording(BaseModel):
    started_at: str | None = None
    lifetime: str | None = None
    recording_type: str | None = None
    password: str | None = Field(default=None, repr=False)
    play_url: str | None = None
    download_url: str | None = None


class OnlineMeeting(BaseModel):
    itemid: int
    cv_cid: int
    name: str | None = None
    provider: str | None = None
    scheduled_at: str | None = None
    duration: str | None = None
    host: str | None = None
    meeting_id: str | None = None
    detail_url: str | None = None
    join_url: str | None = None
    recordings: list[MeetingRecording] = Field(default_factory=list)


class ScheduleEvent(BaseModel):
    index: int | None = None
    cv_cid: int
    date: str | None = None
    time: str | None = None
    title: str | None = None
    comment: str | None = None


class CourseAbout(BaseModel):
    cv_cid: int
    course_no: str | None = None
    year: str | None = None
    semester: str | None = None
    title: str | None = None
    affiliation: list[str] = Field(default_factory=list)
    instructors: list[str] = Field(default_factory=list)
    name_th: str | None = None
    name_en: str | None = None
    abbreviation: str | None = None
    description_th: str | None = None
    description_en: str | None = None
    learning_objectives: list[str] = Field(default_factory=list)
    assigned_outcomes: list[str] = Field(default_factory=list)
    custom_outcomes: list[str] = Field(default_factory=list)


class StudentGroup(BaseModel):
    grouping_id: int
    grouping_name: str
    group_id: int
    name: str
    slogan: str | None = None
    members: list[str] = Field(default_factory=list)


class Portfolio(BaseModel):
    cv_cid: int
    student_name: str | None = None
    total_points: str | None = None
    total_possible: str | None = None
    rank: int | None = None
    rank_total: int | None = None
    grade_letter: str | None = None
    badges: list[str] = Field(default_factory=list)
    group_membership: list[str] = Field(default_factory=list)


class WebResource(BaseModel):
    itemid: int
    cv_cid: int
    title: str
    url: str | None = None
    description: str | None = None


class DownloadResult(BaseModel):
    path: str
    bytes: int
    sha256: str


class ArchiveResult(BaseModel):
    path: str
    format: Literal["zip", "tar"]
    files: int
    bytes: int
    skipped: list[str] = Field(default_factory=list)
