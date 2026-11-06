# 复深蓝标签管理平台演示系统

> 保险行业数据标签配置管理平台，支持元数据建模、业务主题定义、标签任务编排、多级审批与 SQL 执行。
> AI 辅助软件开发综合实践项目。

---

## 简介

面向保险业务场景的标签配置管理平台，覆盖从数据源接入 → 元数据建模 → 业务主题抽象 → 标签任务配置 → 三级审批 → SQL 生成与执行 → 全链路审批闭环。

### 核心模块

| 模块 | 说明 |
|------|------|
| 认证与权限 | JWT 登录 + 角色权限（admin / data_approver / tech_approver / biz_approver） |
| 元数据管理 | 数据源接入、表/字段注册、状态流转（pending → approved / rejected） |
| 业务主题 | 从元数据表抽象业务主题，指定主题表与关联字段 |
| 表关系 | 表间外键/关联关系定义，支撑 SQL 生成 |
| 枚举配置 | 字段枚举值管理，供标签值编码选择 |
| 数据源管理 | 多数据源配置（SQLite / MySQL / Spark 等） |
| 标签任务 | 两种模式：字段配置（自动生成 SQL） / SQL 直配 |
| 三级审批 | 数据审批 → 技术审批 → 业务审批，任一驳回即终止 |
| SQL 执行 | SQLite 本地引擎执行生成的 SQL，记录执行结果 |

---

## 技术栈

- **后端**：FastAPI + SQLAlchemy + Pydantic + SQLite
- **前端**：纯静态 HTML / CSS / JS（无框架依赖）
- **执行引擎**：基于 DB-API 的可插拔引擎（SQLite 内置，Spark Thrift 预留）
- **测试**：pytest（154 用例：unit + integration + engines）

---

## 目录结构

```
tag_platform/
├── run.py                      # 启动入口
├── requirements.txt
├── config.yaml                 # 运行配置（host/port/db 路径等）
├── data/                       # SQLite 数据库文件
├── docs/                       # 设计/需求/测试文档（docx）
├── scripts/                    # 辅助脚本（冒烟测试等）
├── static/                     # 前端静态资源
│   ├── css/main.css            # 全站设计令牌（深海军蓝正式风）
│   ├── js/common.js            # 登录/主题/权限通用逻辑
│   ├── index.html              # 登录页
│   ├── dashboard.html          # 首页
│   ├── metadata.html           # 元数据
│   ├── themes.html             # 业务主题
│   ├── relations.html          # 表关系
│   ├── enum_config.html        # 枚举配置
│   ├── datasources.html        # 数据源
│   ├── approvals.html          # 审批工单（可折叠面板）
│   ├── tag_tasks.html          # 标签任务
│   └── users.html              # 用户角色
├── app/
│   ├── main.py                 # FastAPI 应用入口（CORS + 路由汇总 + 启动钩子）
│   ├── config.py               # YAML 配置加载
│   ├── dependencies.py         # 依赖注入（DB Session / 当前用户）
│   ├── db/
│   │   ├── database.py          # SQLAlchemy engine / SessionLocal / Base
│   │   ├── models/             # ORM 模型（9 个业务表）
│   │   └── seed_data.py        # 保险演示数据（幂等初始化）
│   ├── engines/                # SQL 执行引擎（base / sqlite / spark）
│   ├── routers/                # REST API 路由（10 个 router）
│   ├── schemas/                # Pydantic 输入/输出模型
│   ├── services/               # 业务逻辑层（12 个 service）
│   │   └── base.py             # BaseService + 通用 serial_no 编号生成器
│   └── utils/                  # 密码加密 / JWT / 异常定义 / Excel 解析
└── tests/                      # pytest 测试套件
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python run.py
```

默认监听 `http://0.0.0.0:8000`，启动时自动：

1. 建表（`init_db`）
2. 初始化默认角色与管理员账号
3. 写入保险演示数据（幂等）

### 3. 访问

| 入口 | URL |
|------|-----|
| 登录页 | http://localhost:8000/static/index.html |
| API 文档 | http://localhost:8000/docs |

### 默认账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| `admin` | `admin123` | 系统管理员（可切换身份） |

管理员登录后可通过「设置」按钮切换为数据审批人 / 技术审批人 / 业务审批人角色进行权限测试。

### 运行测试

```bash
python -m pytest tests/ -q
```

当前基线：**154 passed**

---

## 编号体系（V1.4.3）

所有业务实体均使用统一的 `serial_no` 编号规则：**3 位大写前缀 + YYYYMMDD + 3 位递增序号**。

| 模块 | 前缀 | 示例 |
|------|------|------|
| 元数据表 | `MET` | `MET20261105001` |
| 业务主题 | `THE` | `THE20261105001` |
| 表关系 | `REL` | `REL20261105001` |
| 数据源 | `DAT` | `DAT20261105001` |
| 标签任务 | `TAG` | `TAG20261105001` |
| 审批工单 | `APP` | `APP20261105001` |
| 用户 | `USR` | `USR20261105001` |

生成器位于 `app/services/base.py`：

```python
self._gen_serial_no(ModelClass, "PREFIX")
```

---

## 版本更新日志

### V1.4.3 — 2026-11-06

- **UI**：侧栏风格（formal）升级为全站默认主题，侧栏导航字体加大至 15.5px / 加粗 600
- **UI**：各模块清单表头与数据行 padding 统一为 8px，行高更紧凑
- **UI**：审批工单卡片改为可折叠面板（进行中默认展开，已结束默认折叠）
- **UI**：品牌标题统一为「复深蓝标签管理平台演示系统」
- **后端**：7 个业务模型新增 `serial_no VARCHAR(20) UNIQUE` 字段
- **后端**：BaseService 新增 `_gen_serial_no(model_cls, prefix)` 通用编号生成器
- **后端**：ApprovalTicket 工单号由 `TK + 时间戳 + 随机数` 升级为 `APP20261105001` 格式
- **数据库**：6 张业务表 + approval_tickets 已 ALTER TABLE ADD COLUMN 并回填现有数据
- **前端**：清单表头由「ID」改为「ID编号」，数据列改用 serial_no

### V1.4 — 深海军蓝正式风统一改造

- 全站 35 个 CSS 设计令牌（深海军蓝顶栏 `#1B3A5C` / 正式按钮 `#1F4D80` / 墨阶文字 9 级 等）
- 正式主题：侧栏 244px sticky + 01–09 编号索引 + 加粗激活态
- 按钮 3D 立体感（顶部高光 / 底部投影 / 双层阴影）
- 移除所有 emoji / 副标题冗余文字

### V1.3 — 权限控制 + 主题切换

- 管理员专用身份切换器
- 数据权限敏感导航项隐藏
- 审批节点角色门禁

### V1.2 — 标签任务三级审批

- 标签任务提交触发三级审批流
- 审批通过后自动生成 SQL + 执行入口
- 驳回保留当前状态，允许重新提交

### V1.1 — 业务主题 + 枚举 + 执行引擎

- 业务主题抽象层
- 字段枚举配置
- SQLite 执行引擎 + Spark Thrift 预留

### V1.0 — 基础模块

- 元数据 CRUD / 数据源 CRUD / 表关系 CRUD / 权限管理

---

## License

MIT
