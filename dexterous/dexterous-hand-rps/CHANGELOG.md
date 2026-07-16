# Changelog

## 2026-05-14

### Added

- 新增 `shared/rps-recognition.js` 共享识别模块，统一 `2.detect-hand-rps`、`3.output-event`、`5.always-win`、`6.gameplay` 的石头剪刀布判定逻辑。

### Fixed

- 修复 `server.go` 未嵌入 `shared/` 静态目录导致 `shared/rps-recognition.js` 返回 `404` 的问题，恢复 `5.always-win`、`6.gameplay` 等页面的模型初始化与摄像头列表加载。
- 修复 `5.always-win` 中每帧创建定时器并重复触发 `performGesture()` 的问题，稳定识别后同一手势只下发一次克制动作。
- 降低 `5.always-win` 多设备场景下的高频 CAN 调试日志，减少浏览器主线程压力。
- 优化 `4.follow-me` 跟随下发：请求进行中只保留最新帧，并跳过变化过小的数据，避免后端请求堆积。
- 优化 `server.go` CAN 下发并发模型：同一设备/接口内按数据行顺序发送，减少 goroutine 数量并避免多帧乱序。
- 为 `server.go` 到 can-bridge 的 HTTP 请求增加全局并发上限，缩短请求超时并提高连接池容量，降低多设备洪峰时的恢复时间。
- 修复四个 RPS 页面依赖拇指横向位置和 `tip.y < pip.y` 硬阈值导致的单目误判问题，去掉拇指参与判定。

### Changed

- 第二轮性能优化：在不降低 MediaPipe 分辨率、模型复杂度和识别阈值的前提下，降低 `5.always-win`、`4.follow-me`、`6.gameplay` 的非关键 DOM 更新频率。
- `5.always-win` 和 `6.gameplay` 的 FPS、检测详情、手势卡片、当前手势显示改为限频或“有变化才写入”，减少每帧主线程 DOM 操作。
- `4.follow-me` 的 FPS、关节条、手部调试信息改为限频刷新，识别计算和跟随下发节奏保持不变。
- `2.detect-hand-rps`、`3.output-event`、`5.always-win`、`6.gameplay` 的 RPS 识别改为只使用食指、中指、无名指、小指四指分数和模板匹配，不再要求手指完全伸直或完全弯曲。
- 四个页面统一使用同一置信度阈值和同一套模板约束，`3.output-event` 的事件触发、`5.always-win` 的反制触发、`6.gameplay` 的玩家出招判定保持一致标准。
- 四个页面的调试信息改为展示四指伸展分数、模板匹配结果和模板约束结果，便于后续继续调参与排查识别边界。
