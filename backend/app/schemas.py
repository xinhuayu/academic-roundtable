from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Participant = Literal["Sam", "Momo", "Bobby", "System"]
ConversationProfile = Literal["fast", "research", "verification"]


class SessionCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=1000)
    learning_goal: str = Field(default="Explore the topic deeply and critically", max_length=1500)
    rounds_per_segment: int = Field(default=2, ge=2, le=5)
    sources_only: bool = False
    periodic_summary: bool = False
    conversation_profile: ConversationProfile = "fast"
    force_reset: bool = False


class SamMessage(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    target: Literal["roundtable", "Momo", "Bobby", "both"] = "roundtable"
    continue_rounds: int | None = Field(default=None, ge=0, le=5)


class SegmentRequest(BaseModel):
    rounds: int | None = Field(default=None, ge=2, le=5)
    starting_speaker: Literal["Momo", "Bobby"] | None = None
    continue_without_sam: bool = False


class RecapRequest(BaseModel):
    focus: str | None = Field(default=None, max_length=2000)
    periodic: bool | None = None


class SessionSettingsUpdate(BaseModel):
    rounds_per_segment: int | None = Field(default=None, ge=2, le=5)
    sources_only: bool | None = None
    periodic_summary: bool | None = None
    conversation_profile: ConversationProfile | None = None


class LearningRating(BaseModel):
    score: float | None = Field(default=None, ge=1, le=5)
    evidence: str = Field(default="", max_length=4000)
    note: str = Field(default="", max_length=2000)


class LearningEvaluationSubmission(BaseModel):
    reviewer: str = Field(default="Sam", max_length=200)
    ratings: dict[str, LearningRating]
    most_valuable_moment: str = Field(default="", max_length=4000)
    most_confusing_moment: str = Field(default="", max_length=4000)
    one_change_for_next_run: str = Field(default="", max_length=4000)
    overall_comment: str = Field(default="", max_length=6000)


class HealthStatus(BaseModel):
    participant: str
    configured: bool
    reachable: bool | None = None
    model: str
    api_style: str
    detail: str | None = None
