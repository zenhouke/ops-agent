# Ops Agent 生产发布就绪度复审

- 初审日期：2026-09-01
- 修复复审日期：2026-09-02
- 初审基线：`main` / `be3cda4a7987dfef19f94001cedd9bde44a15cc4`
- 当前结论：**仓库内整改已完成；生产发布仍为 NO-GO，等待外部签名凭据与三平台发布证据**
- 范围：Tauri 2 桌面端、内置 FastAPI 后端、数据与凭据、桌面 CI/CD、供应链、恢复与审计；Web/Nginx 不属于本轮桌面验收

## 执行摘要

初审的 12 项问题均已落实仓库内修复或强制发布门禁。Critical 级命令授权扩大、桌面本地 API 身份混淆已经关闭；SSH 改为严格主机密钥校验；已知 Python/Rust 漏洞依赖已升级；生产 Web、备份恢复、文件权限、审计完整性、诊断和三平台签名发布流水线均已补齐。

当前不能把“代码已修复”扩大为“可以生产发布”。本地没有 Apple Developer ID、Apple notarization、Windows Authenticode 和 Tauri updater 私钥，未能在 macOS/Windows Runner 上生成和安装真实签名产物，也没有执行旧版本到新版本的 updater E2E。发布工作流会在这些凭据缺失或任何签名/安装检查失败时停止，因此当前结论仍是 NO-GO。

工作区改动尚未提交或推送；本报告不把本地通过结果描述成远端 CI 或生产证据。

## 整改状态

### PR-001：命令信任从文本前缀改为完整命令精确匹配

- 状态：**已修复并回归**。
- 默认无信任规则时，`df -h && destructive-command` 整串进入人工审批。
- 用户信任 `df -h` 后，只有完全相同的 `df -h` 可自动通过；`df`、附加参数、`&&`、`;`、管道、重定向或换行组成的新命令仍要求审批。
- 信任记录同时绑定 `conversation_id + asset_id + execution_profile`；相同完整命令换会话、换资产或换执行类型都会重新审批。
- `*` 不再被加载、写入或视为允许规则；UI 只允许信任当前完整命令，并明确显示为只读值。
- 设置页已移除手工创建全局允许规则的入口；API 提交的旧 `permissions.allow` 会被忽略并清空，拒绝前缀仍保持全局且优先。
- 本地现有数据中的 4 条旧全局允许规则已通过新迁移路径清空；未输出其命令内容。
- 保留原有 API 字段名和兼容方法仅用于协议兼容，不再具备前缀语义。

### PR-002：桌面后端随机端口与每次启动认证

- 状态：**已修复；Linux 成品后端已冒烟**。
- Tauri 每次启动选择随机高位 loopback 端口并生成随机内存 token；后端认证保持开启。
- 显式指定端口被占用时立即失败，不再复用未知进程。
- WebView 通过 Tauri command 取得后端地址和 token；就绪检查调用受认证的 `/api/auth/verify`，不会把单纯 TCP 可连接当成可信后端。
- 子进程生命周期由桌面壳持有并在退出时终止。

### PR-003：SSH 主机身份校验

- 状态：**已修复；需部署方预置经独立核验的 known_hosts**。
- Server、Network、Netmiko 和 JumpServer 链路均启用严格主机密钥校验。
- 删除全部 `AutoAddPolicy`；未知密钥和变更密钥都会阻断连接。
- 支持系统 known_hosts 和显式 `OPS_AGENT_KNOWN_HOSTS_FILE`，生产 Compose 通过只读 secret 提供该文件。
- 本轮没有实现交互式 TOFU，因为生产默认应由运维侧预置独立核验的指纹，避免首次连接在同一不可信链路上完成信任。

### PR-004：依赖漏洞与可重复安装

- 状态：**已修复已有补丁的漏洞；保留一个上游框架风险说明**。
- Python 漏洞包已升级，新增带哈希的 `requirements.lock`；`pip-audit` 为 0 known vulnerabilities。
- `quick-xml`、`quinn-proto` 和 `anyhow` 已升级到修复版本；`cargo audit` 为 0 vulnerabilities。
- 前端 `pnpm audit --prod` 为 0 vulnerabilities。
- Rust 仍报告 Tauri Linux GTK3 传递依赖的 unmaintained 警告，以及 `glib 0.18.5` 特定 `VariantStrIter` API 的 unsound 警告。当前 Tauri 2 上游仍固定 GTK3/glib 0.18，项目代码没有直接调用该 API；这不是可在本仓库安全升级的独立依赖，需持续跟踪 Tauri 的 GTK4/Tauri 3 迁移。

### PR-005：桌面签名、公证与 updater

- 状态：**发布链代码已修复；外部凭据和真实 Runner 证据未闭环**。
- 开启 updater artifacts；三平台提取 updater 包与签名并生成 `latest.json`。
- 按 Tauri 2 `createUpdaterArtifacts: true` 的实际格式提取 updater：Linux `*.AppImage.sig`、macOS `*.app.tar.gz.sig`、Windows `*.exe.sig`；修复了 Windows 错用 v1-compatible `*.nsis.zip.sig`、导致发布必然失败的问题。
- manifest 构建拒绝未知或重复平台、目录穿越文件名、缺失文件和空签名；发布上传排除内部 `updater-metadata.json`，避免三个同名元数据资产冲突。
- updater 公钥在 Release 构建时由受保护 secret 注入，缺失时立即失败；源码不再依赖未定义的字符串环境变量插值。
- macOS 流程导入 Developer ID、执行 notarization，并验证 `codesign`、Gatekeeper 与 stapler。
- Windows 流程导入 PFX、配置 SHA-256/时间戳签名并验证所有 EXE/MSI Authenticode。
- Release 先创建 draft、上传 SBOM/attestation/包/签名/manifest，最后才发布 immutable release。
- 阻断证据：当前远端没有发布签名 secrets/variables，且本轮没有 macOS/Windows 签名身份，无法完成真实三平台发布。

### PR-006：生产 Web 交付路径（不属于本轮桌面验收）

- 状态：**已修复并完成镜像/配置验证**。
- 新增固定 digest 的多阶段生产镜像、Nginx TLS 同源代理和生产 Compose。
- 后端以 UID 10001 运行；前端入口仅在复制 TLS secret 时临时使用 CHOWN/SETUID/SETGID，随后 Nginx 主进程和 worker 均降为 UID 101，运行时有效 capabilities 为 0。两者文件系统只读并启用 `no-new-privileges`，数据和临时文件使用独立持久卷与 tmpfs。
- TLS 证书、私钥和 SSH known_hosts 使用 Compose secrets；数据卷名可覆盖，便于隔离部署和验收。
- 后端强制 production 环境、认证、独立且至少 32 字符的 token/secret、Allowed Hosts、请求大小和并发限制。

### PR-007：敏感文件权限与明文模型 Key 迁移

- 状态：**已修复并在隔离数据目录验证**。
- POSIX 进程 umask 为 `077`；应用目录强制 `0700`，数据库、WAL/SHM、JSON、日志、备份和主密钥强制 `0600`。
- 旧 `settings.json.api_key` 在启动迁移时写入现有 AES-GCM 凭据记录并从 JSON 原子删除；正常配置读写不再落盘明文 API Key。
- Windows 的主密钥仍是用户数据目录内限权文件，不是系统 Credential Manager；这是后续纵深加固项，不影响本轮关闭明文配置漏洞的结论。

### PR-008：实际成品验收

- 状态：**流水线已补齐；Linux 后端与 AppImage 成品已本地验证**。
- 新增跨平台 PyInstaller 后端冒烟：随机高位端口、`/ready=200`、未认证验证 `401`、认证验证 `204`、认证资产 API `200`。
- Release 在 Linux/macOS/Windows 上构建后端并执行冒烟，再安装 DEB、DMG 或 MSI，启动已安装应用并验证进程存活。
- 本地 Linux PyInstaller 二进制已通过上述后端冒烟；使用一次性测试 updater 密钥生成了 DEB、RPM、AppImage 及签名，AppImage 在隔离显示环境中启动 15 秒未退出，并实际拉起内置后端与终端 WebSocket。测试密钥仅验证管线，不能替代生产密钥或 OS 外部签名。

### PR-009：数据库迁移、备份与恢复

- 状态：**已修复并完成隔离恢复演练**。
- 引入 schema version；发现未来版本数据库时拒绝启动。
- 旧 schema 升级前通过 SQLite backup API 创建一致性备份，保存数据库、可用时保存主密钥、SHA-256 manifest 和完整性校验，并保留最近 5 份。
- 服务持有数据目录独占进程锁；恢复脚本无法在服务运行时取得锁，因此拒绝覆盖。
- 恢复必须显式 `--confirm`，先验证 manifest/哈希/SQLite 完整性，再通过同目录临时文件原子替换并清理旧 WAL/SHM。

### PR-010：CI/CD 供应链与仓库治理

- 状态：**仓库文件与可执行的远端治理均已修复；签名 secrets 待用户提供**。
- GitHub Actions 全部锁定完整 commit SHA，Rust/Python 构建工具固定版本，Python 安装要求 hashes。
- Quality 和 Release 均执行 compile、两套确定性评测、Pyright、ESLint、Vite build、Cargo check 和三生态依赖审计；新增 gitleaks、SBOM 和 GitHub artifact provenance attestation。
- 远端已启用 Dependabot security updates、secret scanning 和 push protection。
- 远端 `main` 已改为无绕过角色、必须通过 PR、解决 review threads、严格要求 GitHub Actions `validate` 状态检查，且继续禁止删除和强推。
- 远端已创建 `production-release` 环境：仅受保护分支可部署，并要求指定 reviewer 人工批准。

### PR-011：Web/API 加固（不属于本轮桌面验收）

- 状态：**已修复并通过生产 HTTP 回归**。
- production 禁用 docs/redoc/openapi，启用 TrustedHost、严格 CORS、认证和安全响应头。
- 请求体上限同时校验 Content-Length 和实际流量；并发许可在读取请求体前获取，避免慢速请求绕过并发上限。
- Nginx 提供 TLS 1.2/1.3、CSP、frame-ancestors、nosniff、Referrer/Permissions Policy、请求体限制和 API 每 IP 限速。
- 回归覆盖健康检查、安全头、错误 Host `400`、未认证 `401`、认证 `200`、生产 docs `404`、非法 Content-Length `400`、超限请求 `413`。

### PR-012：可观测、审计和支持信息

- 状态：**已修复核心链路**。
- 健康、runtime health 和 diagnostics 返回统一 version、build SHA 和 schema version。
- Release 同时注入后端、Web、Cargo 和 Tauri 版本。
- 生产日志采用 10 MiB x 5 轮转、`0600` 权限和统一脱敏过滤；diagnostics 只返回脱敏日志尾部。
- 审批决策和命令提交写入审计记录，命令内容按既有脱敏规则处理。
- 审计日志使用应用 secret 的 HMAC 哈希链；启动迁移旧记录，发现历史链被修改会拒绝继续；API 导出同时给出链完整性状态。
- 审计链写入增加进程内串行化，并统一哈希前的数据类型，避免并发写入分叉以及字符串 ID 经 SQLite 转成整数后立即验签失败。
- 隔离并发测试验证 16 个写入形成完整链，篡改历史记录后能定位首个失败条目。

## 最终验证结果

- Python `compileall`：通过。
- Agent dialogue：8/8 通过。
- Runtime events：17/17 通过，其中包括命令精确信任、审计并发/篡改、严格 SSH、备份校验、凭据迁移和三平台 updater 元数据。
- Pyright：0 errors。
- ESLint：通过。
- Vite production build：通过。
- Cargo check：通过。
- `pip-audit`：0 known vulnerabilities。
- `pnpm audit --prod`：0 known vulnerabilities。
- `cargo audit`：0 vulnerabilities；17 个上游 unmaintained/unsound warnings（`anyhow` 修复后由 18 降为 17）。
- Linux PyInstaller 后端成品冒烟：通过。
- Linux Tauri 桌面成品：DEB、RPM、AppImage 和 updater 签名生成通过；AppImage 进程级启动通过。
- 命令精确授权与会话/资产/执行类型隔离回归：通过。
- 明文 Key 迁移与权限回归：通过。
- schema 升级、备份校验、进程互斥与恢复演练：通过。
- 审计 HMAC 链篡改检测：通过。
- GitHub 外部签名验收：`production-release` 环境存在且要求 reviewer，但环境 secret、环境 variable 和仓库 secret 当前均为空；最新 v0.1.3 Release 没有 updater `.sig`、`latest.json`、SBOM，Windows installer 也没有 Authenticode 证书表，因此不能作为签名发布证据。

## 仍然阻断正式发布的外部条件

1. 在 `production-release` environment 配置 Tauri updater 私钥/密码/公钥、Apple Developer ID P12/密码、Apple notarization API 信息、Windows PFX/密码和可信时间戳 URL。
2. 将本地改动通过受保护分支的 PR 提交，等待新的 `validate` 状态检查通过；本轮未执行 commit 或 push。
3. 由授权 reviewer 批准 Desktop Release，在三个原生 Runner 上取得 OS 签名、公证、安装后启动、updater 签名、SBOM 和 provenance 全部通过的证据。
4. 使用上一生产版本执行一次真实 updater 升级，并验证数据迁移、凭据读取、终端连接和回滚恢复。

上述四项未完成前，发布工作流应保持阻断，不得用本地 build、HTTP 200 或 Linux 单平台冒烟代替生产验收。

## 审计边界

- 未执行生产资产命令。
- 用户没有要求浏览器调试，本轮没有启动 Playwright，也没有把前端构建扩大为浏览器验收。
- 没有生成、读取或输出用户的代码签名私钥、证书密码、API Token 或其他凭据。
- 没有执行 `git commit`、`git push` 或创建 Release。
