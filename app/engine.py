"""发声区间计算引擎。

输入为已校验的事件字典列表（time_ms 非递减），输出发声区间与错误列表。
纯 Python 实现，不依赖 Web 框架，便于独立测试。
"""

from collections import defaultdict, deque

# 错误原因（机器可读）
REASON_UNMATCHED_NOTE_OFF = "unmatched_note_off"
REASON_PEDAL_ALREADY_DOWN = "pedal_already_down"
REASON_PEDAL_NOT_DOWN = "pedal_not_down"


def render(end_ms, events):
    """计算发声区间。

    参数:
        end_ms: 结束时刻（毫秒），仍发声的音在该时刻关闭。
        events: 事件字典列表，按 time_ms 非递减排列，同一时刻按列表顺序处理。
            每项含 time_ms/channel/type；note_on、note_off 另含 pitch。

    返回:
        {"intervals": [...], "errors": [...]}
        intervals 按起音（note_on）事件顺序排列，
        每项含 channel/pitch/start_ms/end_ms/note_on_index。
    """
    # (channel, pitch) -> 仍按住的 note_on 队列（先进先出配对）
    held = defaultdict(deque)
    # channel -> 踏板是否踩下
    pedal_down = defaultdict(bool)
    # channel -> 踏板期间已松键、待释放的音列表
    pending = defaultdict(list)

    intervals = []  # (note_on_index, channel, pitch, start_ms, end_ms)
    errors = []

    for index, ev in enumerate(events):
        t = ev["time_ms"]
        ch = ev["channel"]
        etype = ev["type"]

        if etype == "note_on":
            # 重复按键各自入队，保留独立发声区间
            held[(ch, ev["pitch"])].append((t, index))
        elif etype == "note_off":
            queue = held[(ch, ev["pitch"])]
            if not queue:
                errors.append({
                    "index": index,
                    "reason": REASON_UNMATCHED_NOTE_OFF,
                    "message": "note_off has no held note_on to pair with",
                })
                continue
            start_ms, onset_index = queue.popleft()  # 配对最早仍按住的 note_on
            if pedal_down[ch]:
                # 踏板踩下时松键只记为待释放
                pending[ch].append((ev["pitch"], start_ms, onset_index))
            else:
                intervals.append((onset_index, ch, ev["pitch"], start_ms, t))
        elif etype == "pedal_down":
            if pedal_down[ch]:
                errors.append({
                    "index": index,
                    "reason": REASON_PEDAL_ALREADY_DOWN,
                    "message": "pedal_down while pedal is already down",
                })
                continue
            pedal_down[ch] = True
        elif etype == "pedal_up":
            if not pedal_down[ch]:
                errors.append({
                    "index": index,
                    "reason": REASON_PEDAL_NOT_DOWN,
                    "message": "pedal_up while pedal is not down",
                })
                continue
            pedal_down[ch] = False
            # 抬踏板：该通道所有待释放音在同一时刻截断
            for pitch, start_ms, onset_index in pending[ch]:
                intervals.append((onset_index, ch, pitch, start_ms, t))
            pending[ch] = []

    # 结束时刻关闭仍发声的音：仍按住的 + 踏板悬着的待释放音
    for (ch, pitch), queue in held.items():
        for start_ms, onset_index in queue:
            intervals.append((onset_index, ch, pitch, start_ms, end_ms))
    for ch, notes in pending.items():
        for pitch, start_ms, onset_index in notes:
            intervals.append((onset_index, ch, pitch, start_ms, end_ms))

    # 按起音事件顺序返回
    intervals.sort(key=lambda item: item[0])
    return {
        "intervals": [
            {
                "channel": ch,
                "pitch": pitch,
                "start_ms": start_ms,
                "end_ms": stop_ms,
                "note_on_index": onset_index,
            }
            for onset_index, ch, pitch, start_ms, stop_ms in intervals
        ],
        "errors": errors,
    }
