# 业务项目看板

单机版的海外项目进展看板。记录每个项目现在在哪个阶段、卡在什么事上、下一步谁在什么时候做什么。

- 完整背景与边界：[`PRODUCT.md`](PRODUCT.md)
- 技术架构与 API：[`ARCHITECTURE.md`](ARCHITECTURE.md)
- 开发计划：[`ROADMAP.md`](ROADMAP.md)
- 改动规则（AI agent 必读）：[`AGENTS.md`](AGENTS.md)
- 选型理由：[`DECISIONS.md`](DECISIONS.md)

---

## 启动

项目支持两种模式，自动切换，**不需要配置**。

### 模式 A · 后端模式（数据落盘，推荐）

**Windows**：双击 `scripts\start.bat`
**macOS**：双击 `scripts\start.command`

浏览器会自动打开 `http://127.0.0.1:8787`，页面顶部显示「后端模式」。数据存在 SQLite，关浏览器不丢。

第一次运行需要 Python 3.9+ 和三个包：

```
pip install fastapi uvicorn pydantic
```

### 模式 B · 离线模式（零依赖，保底）

直接双击 `index.html`。

页面顶部会显示「离线模式 · 记得导出备份」。功能完整，但数据存在这个浏览器的 localStorage 里——**清缓存、换文件夹、换浏览器都会看不到**，所以必须定期导出。

### 不知道走哪条？

跑一下自检：

```
python scripts\check_env.py     # Windows
python3 scripts/check_env.py    # macOS
```

它会告诉你：Python 在不在、依赖齐不齐、数据目录能不能写、该走哪个模式。

---

## 日常使用

| 想做的事 | 怎么做 |
|---|---|
| 加项目 | 首页右上「＋ 新增项目」 |
| 记一条进展 | 顶部「对话录入」，用大白话写，系统抽字段，你核对后入库 |
| 改阶段定义 | 首页「⚙ 阶段设置」，可增删改、拖顺序、改颜色 |
| 看某个项目详情 | 点项目名，展开卡点/负责人/关键时间点 |
| 查 DDL | 首页月历（◆ 标记）或「关键时间点」列表 |

**录入建议**：一句话里尽量带齐「客户 + 项目 + 现在什么阶段 + 卡在哪 + 下一步谁做什么 + 关键日期」。例：

> 德国 Kalom 的洗碗机项目开发中，模具要改，计划 11/10 到 12/5，12/5 是出货 DDL。我找开发老李要了包装书，下一步催他确认图纸。

---

## 数据备份

**这件事每周做一次，不要省。**

| 方式 | 位置 | 适合 |
|---|---|---|
| 导出 JSON | 首页「导出备份」 | 换机器、换模式时导入用 |
| 导出 CSV | 导出菜单选 CSV | 用 Excel/WPS 打开看或做周报 |
| 整库快照 | `GET /api/backup` | 后端模式下完整备份 |

后端模式的数据目录：

- Windows：`%LOCALAPPDATA%\BusinessDashboard\`
- macOS：`~/Library/Application Support/BusinessDashboard/`

直接复制 `dashboard.sqlite3` 即可。

---

## 出问题了

| 现象 | 原因 | 处理 |
|---|---|---|
| 双击 `start.bat` 黑窗一闪就没了 | 没找到 Python | 看 `data\start.log`；或直接双击 `index.html` 用离线模式 |
| 页面打开是空白 | 端口被占 / 代理拦截 | 换 `http://127.0.0.1:8788` 试；确认浏览器没走代理访问 localhost |
| 「离线模式」但之前是后端模式 | 后端没起来 | 数据在后端库里没丢，把服务起来即可看到 |
| 数据"消失"了 | 离线模式下移动了 `index.html` 的位置 | localStorage 按路径隔离。移回原位置，或从导出的 JSON 导入 |
| CSV 用 Excel 打开乱码 | 编码问题 | 本项目导出已带 BOM，若仍乱码请用「数据→自文本」并选 UTF-8 |

---

## 开发

```
python scripts/smoke.py     # 12 项冒烟测试，改代码后必跑
```

详细规范见 `AGENTS.md`。
