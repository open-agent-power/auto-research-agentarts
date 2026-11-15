# S092：受限只读宿主的未知请求查询

S091 的 unknown Controller parent 查询现在也在 `LocalWorkbench.open_readonly` 和受限 HTTP 宿主显式开放。此查询对 manager 和 Project 使用 SQLite `mode=ro&immutable=1`、读取前后文件身份核对，并拒绝数据库 `-wal`/`-shm`/`-journal` sidecar，包括悬空符号链接；factory 的 manager sidecar 检查亦改用 lstat。避免重叠只读事务，保留原状态、活动项目和 snapshot 校验。新 GET 不带 body、恢复许可或派发；受限宿主 POST 仍被拒绝，其他原未开放 GET 不因此开放。

作者相关22/22、独审相关19/19合成通过。真实 loopback HTTP 查询前后对完整 manager/Project 目录和文件做哈希，字节不变；连接哨兵确认此查询使用 immutable 读取，禁止 writer/step/dispatch，覆盖合法 parent unknown、child completed、身份 mismatch、9项截断、过期 snapshot、禁 POST、manager/Project 普通和悬空 sidecar、factory 悬空 sidecar及模拟文件身份漂移。原普通宿主路径/旧wire相关检查通过。测试使用隔离合成，不访问真实科研、不运行模型或fit；本地文件I/O实际发生，费用/token unknown。

独审发现普通 `Project.status()` 的 mode=ro 不足以保证不触碰 sidecar，不能只加白名单；又指出已有 factory 的 `Path.exists` 会漏悬空链接，均修复后再验。immutable 和文件身份检查不证明抗恶意并发或 OS 级隔离，也不等于 SQL/工件真实性或自动恢复许可。旧真实项目沿原pin、原预算保持。
