# Product Definition

## Problem

The user tracks several active projects and dislikes maintaining a status table manually. Project progress, phase, testing state, and dates are already recorded in project folders, commonly across Markdown files such as `README.md`, `STATUS.md`, `TESTING.md`, and `ROADMAP.md`. The dashboard should read those records and make overall schedules easy to scan.

## Target user

First: one person running a local dashboard on Windows and using an internally deployed model API. The repository will be open source so others can self-host it and configure their own model API.

## Primary scenario

1. Add a project by entering its local folder path, project name, planned start date, and planned end date.
2. At computer startup, the dashboard launches and scans once that day. The user can also trigger a scan manually.
3. The dashboard reads the project's Markdown files and extracts the latest explicitly dated progress, current phase, phase dates when present, and relevant testing state.
4. The home calendar shows all projects as colored bars across their planned dates, ordered by start date.
5. Clicking a bar navigates to a project detail page with the project's phase timeline, latest progress, summary, and source references.
6. The user reviews the scan summary and resolves ambiguous states or schedule changes.

## User interface

### Home page

- Month-oriented calendar timeline, with a time axis left to right and projects ordered vertically by start date.
- Each project has a distinct color bar spanning its planned start and end dates. The bar identifies the current phase.
- Clicking a bar navigates to the project's detail page.
- A compact scan summary lists detected status changes, schedule changes, and items needing confirmation. If nothing changed, show that the project states are unchanged.
- Show scan failure and timestamp when a scan fails; retain the last successful state and offer manual retry.
- Provide a manual refresh button.

### Project detail page

- Show a concise overview derived from the project's README, the folder path, latest dated progress, and source Markdown references.
- Show the complete phase sequence. Completed phases are gray, the current phase is bold, and future phases use normal styling.
- If the current phase is explicitly marked as testing, show “Testing” beside it.
- Show phase start and end dates when documented. Missing dates remain unknown; do not infer them.
- Provide an action to open the local project folder.

## Progress and schedule rules

- Use explicit dates written in progress records to determine freshness; do not use file modification times as the status timestamp.
- The newest explicitly dated record is the current candidate state. Preserve links or paths to its source documents and the record date.
- If documents conflict, the current phase cannot be established, or evidence is missing, mark the project “Needs confirmation” and retain the last known state. Do not guess.
- The project start and end dates entered during setup define the initial overall bar.
- If a document reports a changed planned date, show old and new dates as a schedule change and wait for user confirmation before changing the timeline.
- Dashboard state may be updated; project source documents are read-only.

## API and privacy

- Support both OpenAI and Anthropic request formats, with user-configured API base URL, secret, and model name.
- Keep credentials in local configuration or the operating system's secure credential store; never commit them or log them.
- Do not host the dashboard or project data in the cloud. Do not upload files to a dashboard service. Do not add telemetry.
- Model requests go only to the endpoint configured by the user. A local application can still make network requests to that endpoint; the owner's intended endpoint is the company's internal model API.
- The open-source README and setup flow must explain that users are responsible for choosing an endpoint suitable for their project data.

## MVP scope

- Windows-first startup behavior and local folder navigation.
- Cross-platform core where practical; macOS/Linux support is not part of the first verified release.
- Explicit project registration by local path; no whole-disk discovery.
- Markdown-only source reading.
- Local dashboard state and source references.
- Daily first-start scan, manual refresh, change summary, failure state, and retry.

## Non-goals

- Editing project Markdown or other source files.
- Cloud hosting, cloud synchronization, or dashboard telemetry.
- Parsing PDF, Word, spreadsheets, or source code.
- Automatically changing planned dates without confirmation.
- Treating AI inference without dated evidence as a verified project status.
- Multi-user collaboration in the first release.

## Validation

Run a two-week personal trial. Check whether the dashboard makes all current phases and schedules quick to understand, and record how often status extraction requires correction. Set quantitative thresholds after collecting baseline usage rather than inventing an accuracy target before real project documents are evaluated.

---

# 产品定义（中文版）

## 问题

用户同时跟踪多个项目，不喜欢手动维护状态表。项目进度、阶段、测试状态和日期已记录在各自文件夹的 Markdown 文件中，常见文件包括 `README.md`、`STATUS.md`、`TESTING.md` 和 `ROADMAP.md`。看板应读取这些记录，让整体排期一目了然。

## 目标用户

第一阶段面向一位在 Windows 上本地运行看板、使用公司内部部署模型 API 的个人用户。仓库将开源，供其他人自行部署并配置自己的模型 API。

## 主要场景

1. 添加项目时输入本地文件夹路径、项目名、计划开始日期和计划结束日期。
2. 电脑启动时看板启动，并在当天巡检一次；用户也可以手动刷新。
3. 看板读取项目 Markdown，提取最新的明确日期进展、当前 Phase、文档中记录的阶段日期和测试状态。
4. 首页用横跨计划日期的彩色色块展示所有项目，按项目开始日期排序。
5. 点击项目色块进入详情页，查看该项目的 Phase 时间线、最新进展、简介和来源。
6. 用户查看巡检摘要，并处理状态不清楚或排期变化的项目。

## 用户界面

### 首页

- 按月展示日历时间轴，时间从左到右，项目按开始日期从上到下排序。
- 每个项目使用独立颜色的色块，覆盖计划开始和结束日期，并标记当前 Phase。
- 点击色块进入项目详情页。
- 显示简短的本次巡检摘要，包括状态变化、排期变化和待确认项目；没有变化时显示项目状态无更新。
- 巡检失败时显示失败状态和时间，保留上次成功结果并提供手动重试。
- 提供手动刷新按钮。

### 项目详情页

- 显示从 README 提取的简短概况、文件夹路径、最近一次有日期的进展和来源 Markdown 文档。
- 展示完整 Phase 顺序。已完成阶段灰显，当前阶段加粗，后续阶段使用正常样式。
- 当前 Phase 明确标记为测试中时，在旁边显示“测试中”。
- 文档有记录时展示阶段开始和结束日期；缺失日期保持未知，不自行推算。
- 提供打开本地项目文件夹的操作。

## 进度与排期规则

- 根据进展记录中明确写出的日期判断新旧，不用文件修改时间代替状态日期。
- 最新的明确日期记录作为当前候选状态。保留来源文档路径和记录日期。
- 若文档冲突、无法确认当前 Phase 或证据缺失，将项目标为“待确认”并保留上次已知状态，不猜测。
- 用户添加项目时填写的开始和结束日期构成初始整体时间条。
- 文档出现新的计划日期时，先显示旧日期和候选新日期，等待用户确认后再改时间轴。
- 看板可以更新自己的状态；项目源文档只读。

## API 与隐私

- 同时支持 OpenAI 和 Anthropic 请求格式，用户配置 API 地址、密钥和模型名称。
- 凭证保存在本地配置或操作系统安全凭证库中，绝不提交或写入日志。
- 不把看板或项目数据放到云端，不向看板服务上传文件，不添加遥测。
- 模型请求只发送到用户配置的 API。即使应用本地运行，远程模型调用仍会通过网络发送内容；发起人的预期接口是公司内部模型 API。
- 开源 README 和设置界面必须说明：用户需自行选择适合项目数据的模型 API。

## MVP 范围

- 优先验证 Windows 本机启动和本地文件夹跳转。
- 核心逻辑尽量跨平台；第一版不承诺完整验证 macOS/Linux。
- 由用户明确登记项目路径；不扫描整台电脑。
- 只读取 Markdown。
- 看板状态与来源引用保存在本地。
- 每天首次开机巡检一次，提供手动刷新、变更摘要、失败提示和重试。

## 非目标

- 编辑项目 Markdown 或其他源文件。
- 云端托管、云同步或看板遥测。
- 解析 PDF、Word、电子表格或源代码。
- 未经确认自动修改计划日期。
- 把没有明确日期证据的 AI 推断当作已核实状态。
- 第一版实现多人协作。

## 验证

先进行两周个人试用，观察看板是否能让用户快速理解各项目的阶段与排期，并记录状态识别需要纠正的频次。真实项目文档评估前不预设准确率门槛；收集基线后再设定量化标准。
