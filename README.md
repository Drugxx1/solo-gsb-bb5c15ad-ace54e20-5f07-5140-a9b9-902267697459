# Keyboard Render API

电子琴演奏事件 → 发声区间计算服务。接收一串按时间排列的演奏事件（按键、松键、踏板），
考虑延音踏板的影响，输出每个音实际的发声起止毫秒。

## 启动

单条命令（需要 Docker 与 Docker Compose）：

```bash
docker compose up --build
```

## 访问地址

- API 地址： http://localhost:8000
- 交互式文档（Swagger UI）： http://localhost:8000/docs
- 健康检查： http://localhost:8000/health

## 配置

默认监听容器内 8000 端口，Compose 映射到本机 8000 端口。
如需修改本机端口，编辑 `docker-compose.yml` 中的 `ports`，例如 `"8080:8000"` 后访问
http://localhost:8080 。无其他必需配置。

## API 说明

### POST /render

请求体：

```json
{
  "end_ms": 2000,
  "events": [
    {"time_ms": 100, "channel": 0, "type": "pedal_down"},
    {"time_ms": 200, "channel": 0, "type": "note_on",  "pitch": 60},
    {"time_ms": 300, "channel": 0, "type": "note_on",  "pitch": 64},
    {"time_ms": 400, "channel": 0, "type": "note_off", "pitch": 60},
    {"time_ms": 800, "channel": 0, "type": "pedal_up"}
  ]
}
```

字段约束：

- `end_ms`：结束时刻（毫秒，≥ 0）。所有事件必须满足 `0 ≤ time_ms ≤ end_ms`，
  且 `events` 按 `time_ms` 非递减排列，否则返回 422。
- `channel`：0–15；`pitch`：0–127，仅 `note_on` / `note_off` 需要（踏板事件不得携带）。
- `type`：`note_on` / `note_off` / `pedal_down` / `pedal_up`。
- 同一时刻的多个事件按输入数组顺序处理。

响应：

```json
{
  "intervals": [
    {"channel": 0, "pitch": 60, "start_ms": 200, "end_ms": 800, "note_on_index": 1},
    {"channel": 0, "pitch": 64, "start_ms": 300, "end_ms": 2000, "note_on_index": 2}
  ],
  "errors": []
}
```

- `intervals` 按起音（note_on）事件的输入顺序排列，`note_on_index` 为对应
  note_on 事件在输入中的序号；`start_ms` / `end_ms` 为实际发声起止毫秒。
- `errors` 中每项给出出错事件的输入序号 `index` 与机器可读原因 `reason`：

| reason | 含义 |
| --- | --- |
| `unmatched_note_off` | 松键时该通道该音高没有仍按住的 note_on 可配对 |
| `pedal_already_down` | 踏板已踩下时又收到 pedal_down |
| `pedal_not_down` | 踏板未踩下时收到 pedal_up |

出错事件被跳过，不影响其余事件继续处理。

### 发声规则

- 每个 `(channel, pitch)` 的 `note_off` 配对**最早仍按住**的 `note_on`（FIFO）；
  同一音高重复按键各自保留独立的发声区间。
- 踏板踩下期间松键只记为**待释放**；`pedal_up` 时该通道所有待释放音在该时刻同时截断。
- 踏板按通道独立。
- 到达 `end_ms` 时，仍按住的音与踏板悬着的待释放音都在 `end_ms` 关闭。

### 示例

```bash
curl -s http://localhost:8000/render \
  -H 'Content-Type: application/json' \
  -d '{"end_ms": 2000, "events": [
        {"time_ms": 100, "channel": 0, "type": "pedal_down"},
        {"time_ms": 200, "channel": 0, "type": "note_on", "pitch": 60},
        {"time_ms": 400, "channel": 0, "type": "note_off", "pitch": 60},
        {"time_ms": 800, "channel": 0, "type": "pedal_up"}]}'
```

## 本地开发（不用 Docker）

```bash
pip install -r requirements-dev.txt
pytest                 # 运行测试
uvicorn app.main:app --reload
```

## 项目结构

```
app/
  main.py    FastAPI 入口，POST /render 与 GET /health
  models.py  请求/响应模型与输入校验
  engine.py  发声区间计算引擎（纯 Python，可独立测试）
tests/
  test_render.py
Dockerfile / docker-compose.yml / requirements.txt
```
