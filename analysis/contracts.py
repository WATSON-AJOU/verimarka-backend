from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class GuardInputItem(BaseModel):
    url: str
    filename: str
    mime_type: str


class GuardMeta(BaseModel):
    user_id: str
    content_id: str


class GuardSearchOptions(BaseModel):
    top_k: int = 10
    top_phash: int = 10


class GuardWatermarkOptions(BaseModel):
    apply_on_allow: bool = True
    model: str = "wam"
    nbits: int = 32
    scaling_w: float = 2.0
    proportion_masked: float = Field(default=0.35, ge=0.0, le=1.0)


class GuardOptions(BaseModel):
    search: GuardSearchOptions = GuardSearchOptions()
    watermark: GuardWatermarkOptions = GuardWatermarkOptions()


class GuardRequestV1(BaseModel):
    job_id: str
    mode: Literal["register"] = "register"
    content_type: Literal["image"] = "image"
    input: list[GuardInputItem] = Field(min_length=1)
    meta: GuardMeta
    options: GuardOptions = GuardOptions()


class GuardCandidateV1(BaseModel):
    db_key: str | None = None
    db_file: str | None = None
    cosine: float | None = None
    phash_dist: int | None = None


class GuardScoresV1(BaseModel):
    top_cosine: float | None = None
    top_phash_dist: int | None = None
    policy_version: str = "v1"


class GuardWatermarkResultV1(BaseModel):
    requested: bool
    applied: bool = False
    output_url: str | None = None
    output_key: str | None = None
    model: str | None = None
    model_version: str | None = None
    nbits: int | None = None
    scaling_w: float | None = None
    proportion_masked: float | None = None
    payload_id: str | None = None


class GuardTimingV1(BaseModel):
    download: int = 0
    embed: int = 0
    ann_search: int = 0
    phash: int = 0
    total: int = 0


class GuardResponseV1(BaseModel):
    job_id: str
    mode: str
    content_type: str
    success: bool
    decision: Literal["allow", "review", "block"]
    reason: str
    next_action: Literal["none", "start_vote"]
    scores: GuardScoresV1
    top_match: GuardCandidateV1 | None = None
    candidates: list[GuardCandidateV1] = Field(default_factory=list)
    watermark: GuardWatermarkResultV1
    timing_ms: GuardTimingV1


class GuardErrorResponseV1(BaseModel):
    job_id: str | None = None
    success: bool = False
    error_code: str
    error_message: str
    retryable: bool
