"""POST /render 的端到端测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def post(payload):
    return client.post("/render", json=payload)


def test_basic_note_pairing():
    resp = post({
        "end_ms": 1000,
        "events": [
            {"time_ms": 100, "channel": 0, "type": "note_on", "pitch": 60},
            {"time_ms": 400, "channel": 0, "type": "note_off", "pitch": 60},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["intervals"] == [
        {"channel": 0, "pitch": 60, "start_ms": 100, "end_ms": 400,
         "note_on_index": 0}
    ]


def test_note_off_pairs_earliest_held_note_on():
    """重复按键各自保留独立区间，松键按 FIFO 配对。"""
    resp = post({
        "end_ms": 1000,
        "events": [
            {"time_ms": 100, "channel": 0, "type": "note_on", "pitch": 60},
            {"time_ms": 200, "channel": 0, "type": "note_on", "pitch": 60},
            {"time_ms": 300, "channel": 0, "type": "note_off", "pitch": 60},
            {"time_ms": 500, "channel": 0, "type": "note_off", "pitch": 60},
        ],
    })
    assert resp.status_code == 200
    assert [i["start_ms"] for i in resp.json()["intervals"]] == [100, 200]
    assert [i["end_ms"] for i in resp.json()["intervals"]] == [300, 500]


def test_pedal_defers_release_until_pedal_up():
    """踏板踩下时松键只记为待释放，抬踏板时统一截断。"""
    resp = post({
        "end_ms": 1000,
        "events": [
            {"time_ms": 100, "channel": 0, "type": "pedal_down"},
            {"time_ms": 200, "channel": 0, "type": "note_on", "pitch": 60},
            {"time_ms": 300, "channel": 0, "type": "note_on", "pitch": 64},
            {"time_ms": 400, "channel": 0, "type": "note_off", "pitch": 60},
            {"time_ms": 500, "channel": 0, "type": "note_off", "pitch": 64},
            {"time_ms": 800, "channel": 0, "type": "pedal_up"},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert [(i["pitch"], i["start_ms"], i["end_ms"])
            for i in body["intervals"]] == [(60, 200, 800), (64, 300, 800)]


def test_pedal_is_per_channel():
    resp = post({
        "end_ms": 1000,
        "events": [
            {"time_ms": 100, "channel": 0, "type": "pedal_down"},
            {"time_ms": 200, "channel": 0, "type": "note_on", "pitch": 60},
            {"time_ms": 300, "channel": 1, "type": "note_on", "pitch": 60},
            {"time_ms": 400, "channel": 0, "type": "note_off", "pitch": 60},
            {"time_ms": 450, "channel": 1, "type": "note_off", "pitch": 60},
            {"time_ms": 800, "channel": 0, "type": "pedal_up"},
        ],
    })
    assert resp.status_code == 200
    intervals = resp.json()["intervals"]
    # 通道 0 的音被踏板延到 800，通道 1 不受踏板影响
    assert [(i["channel"], i["end_ms"]) for i in intervals] == [(0, 800), (1, 450)]


def test_end_ms_closes_held_and_pending_notes():
    resp = post({
        "end_ms": 900,
        "events": [
            {"time_ms": 100, "channel": 0, "type": "pedal_down"},
            {"time_ms": 200, "channel": 0, "type": "note_on", "pitch": 60},
            {"time_ms": 300, "channel": 0, "type": "note_off", "pitch": 60},
            {"time_ms": 400, "channel": 0, "type": "note_on", "pitch": 64},
        ],
    })
    assert resp.status_code == 200
    intervals = resp.json()["intervals"]
    # 待释放的 60 与仍按住的 64 都在结束时刻关闭
    assert [(i["pitch"], i["start_ms"], i["end_ms"])
            for i in intervals] == [(60, 200, 900), (64, 400, 900)]


def test_unmatched_note_off_reports_index_and_reason():
    resp = post({
        "end_ms": 1000,
        "events": [
            {"time_ms": 100, "channel": 0, "type": "note_off", "pitch": 60},
            {"time_ms": 200, "channel": 0, "type": "note_on", "pitch": 62},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"][0]["index"] == 0
    assert body["errors"][0]["reason"] == "unmatched_note_off"
    # 处理继续，后续音符在结束时刻关闭
    assert body["intervals"][0]["end_ms"] == 1000


def test_invalid_pedal_transitions_report_errors():
    resp = post({
        "end_ms": 1000,
        "events": [
            {"time_ms": 100, "channel": 0, "type": "pedal_down"},
            {"time_ms": 200, "channel": 0, "type": "pedal_down"},
            {"time_ms": 300, "channel": 0, "type": "pedal_up"},
            {"time_ms": 400, "channel": 0, "type": "pedal_up"},
        ],
    })
    assert resp.status_code == 200
    errors = resp.json()["errors"]
    assert [(e["index"], e["reason"]) for e in errors] == [
        (1, "pedal_already_down"),
        (3, "pedal_not_down"),
    ]


def test_same_time_events_processed_in_input_order():
    resp = post({
        "end_ms": 1000,
        "events": [
            {"time_ms": 100, "channel": 0, "type": "note_off", "pitch": 60},
            {"time_ms": 100, "channel": 0, "type": "note_on", "pitch": 60},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    # 先处理 note_off：无配对 -> 报错；note_on 后到，在结束时刻关闭
    assert body["errors"][0]["reason"] == "unmatched_note_off"
    assert body["intervals"][0]["start_ms"] == 100
    assert body["intervals"][0]["end_ms"] == 1000


def test_intervals_ordered_by_note_on_event_order():
    resp = post({
        "end_ms": 1000,
        "events": [
            {"time_ms": 100, "channel": 0, "type": "note_on", "pitch": 64},
            {"time_ms": 200, "channel": 0, "type": "note_on", "pitch": 60},
            {"time_ms": 300, "channel": 0, "type": "note_off", "pitch": 60},
            {"time_ms": 400, "channel": 0, "type": "note_off", "pitch": 64},
        ],
    })
    assert resp.status_code == 200
    intervals = resp.json()["intervals"]
    # 64 先结束，但 64 的起音事件在前，故仍排第一
    assert [i["pitch"] for i in intervals] == [64, 60]


def test_validation_rejects_unsorted_events():
    resp = post({
        "end_ms": 1000,
        "events": [
            {"time_ms": 500, "channel": 0, "type": "note_on", "pitch": 60},
            {"time_ms": 100, "channel": 0, "type": "note_off", "pitch": 60},
        ],
    })
    assert resp.status_code == 422


def test_validation_rejects_event_beyond_end_ms():
    resp = post({
        "end_ms": 100,
        "events": [
            {"time_ms": 200, "channel": 0, "type": "note_on", "pitch": 60},
        ],
    })
    assert resp.status_code == 422


def test_validation_requires_pitch_for_notes_and_forbids_it_for_pedal():
    assert post({"end_ms": 100, "events": [
        {"time_ms": 0, "channel": 0, "type": "note_on"},
    ]}).status_code == 422
    assert post({"end_ms": 100, "events": [
        {"time_ms": 0, "channel": 0, "type": "pedal_down", "pitch": 60},
    ]}).status_code == 422


def test_health():
    assert client.get("/health").json() == {"status": "ok"}
