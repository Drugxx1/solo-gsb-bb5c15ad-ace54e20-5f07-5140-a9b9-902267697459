"""请求/响应模型与输入校验。"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class EventType(str, Enum):
    note_on = "note_on"
    note_off = "note_off"
    pedal_down = "pedal_down"
    pedal_up = "pedal_up"


NOTE_TYPES = (EventType.note_on, EventType.note_off)
PEDAL_TYPES = (EventType.pedal_down, EventType.pedal_up)


class Event(BaseModel):
    time_ms: int = Field(ge=0, description="事件时刻（毫秒）")
    channel: int = Field(ge=0, le=15, description="MIDI 通道 0-15")
    type: EventType
    pitch: Optional[int] = Field(
        default=None, ge=0, le=127, description="音高 0-127，仅按键事件需要"
    )

    @model_validator(mode="after")
    def check_pitch_usage(self):
        if self.type in NOTE_TYPES and self.pitch is None:
            raise ValueError("pitch is required for note_on/note_off events")
        if self.type in PEDAL_TYPES and self.pitch is not None:
            raise ValueError("pitch must be omitted for pedal events")
        return self


class RenderRequest(BaseModel):
    end_ms: int = Field(ge=0, description="结束时刻（毫秒）")
    events: List[Event] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_timeline(self):
        times = [e.time_ms for e in self.events]
        if any(later < earlier for earlier, later in zip(times, times[1:])):
            raise ValueError("events must be sorted by non-decreasing time_ms")
        if times and times[-1] > self.end_ms:
            raise ValueError("event time_ms must not exceed end_ms")
        return self


class Interval(BaseModel):
    channel: int
    pitch: int
    start_ms: int
    end_ms: int
    note_on_index: int = Field(description="对应 note_on 事件在输入中的序号")


class RenderError(BaseModel):
    index: int = Field(description="出错事件在输入中的序号")
    reason: str = Field(
        description="unmatched_note_off / pedal_already_down / pedal_not_down"
    )
    message: str


class RenderResponse(BaseModel):
    intervals: List[Interval]
    errors: List[RenderError]
