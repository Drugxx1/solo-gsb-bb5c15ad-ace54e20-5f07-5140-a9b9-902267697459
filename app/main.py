"""FastAPI 入口。"""

from fastapi import FastAPI

from .engine import render
from .models import RenderRequest, RenderResponse

app = FastAPI(
    title="Keyboard Render API",
    version="1.0.0",
    description="根据电子琴演奏事件计算每个音的实际发声区间（含踏板处理）。",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/render", response_model=RenderResponse)
def post_render(request: RenderRequest):
    events = [ev.model_dump(exclude_none=True) for ev in request.events]
    return render(request.end_ms, events)
