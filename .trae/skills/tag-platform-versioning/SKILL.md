---
name: tag-platform-versioning
description: Align README and three Word design docs after a repo bump. Use when the user asks to sync docs after a version change, or update README to reflect latest state, or push release to master. Do not use for pure implementation or one-off bugfixes.
---

# TAG//OPS 版本同步 & 提交流程

本技能固化 `tag_platform` 仓库每次迭代后的收尾工作：**代码/架构变更完成后，同步 README + 三份 Word 文档 + 推送到 master**。

适用信号：
- 用户说「版本 X 同步文档」「README 跟上最新变化」「提交并推送」
- 完成了一轮功能迭代，需要收口到可交付状态

## 前置确认

开始前先跑一遍：

```powershell
git status            # 确认工作区有改动、无意外 untracked
git diff --stat HEAD  # 看改动范围，判断是否覆盖了后端 + 前端 + 测试
git log --oneline -3  # 最后一次提交，确定 bump 起点
```

确认 `requirements.txt`、`config.yaml` 里没有临时调试残留；`config.yaml` 的 `secret_key` 占位值已标记（启动时会自降级并告警，不要硬编码真实密钥进仓库）。

## 第一步：README 同步

必须维护的章节，任何章节有变化都要一起更新：

### 目录结构（`## 目录结构`）
- 只加，不删；**不要**从 git 历史中删除已经存在过的文件（否则后续 pull 会产生目录与文件冲突）
- 新建 CSS/JS 文件要写进 `static/css/` 和 `static/js/` 注释里
- 新建后端模块要写进 `app/` 对应子目录注释里
- 新建测试文件要写进 `tests/` 注释里

### 界面风格切换（如有主题）
- 列出三套主题的强调色 + 侧栏宽度 + 风格关键词
- 说明：右下角 FAB、localStorage 记忆、登录页不参与切换
- 给出切换路径（`<head>` 阻塞脚本按 `localStorage.theme` 条件加载样式表）

### 快速开始（`## 快速开始`）
- 监听端口：代码是什么就写什么（目前是 `127.0.0.1:8000`）
- 启动时的自动流程（建表 → 种子 → secret_key 降级告警）
- **不要**把 `demo_switch.enabled=true` 当作生产功能描述

### 默认账号（`### 默认账号`）
- 实际什么能登录就写什么
- 已废弃的（比如身份切换器）要明确标注「V1.7 起移除」而不是只删段落

### 版本更新日志（`## 版本更新日志`）
- **新增一节在最顶部**，格式固定为 `### VX.X — YYYY-MM-DD`
- 分块：**前端** / **后端** / **测试** / **文档**（有就写，没有就省略）
- 每个 bullet 讲清楚：**改了什么 → 为什么 → 具体文件/API**
- 示例：
  ```
  **前端：三主题切换**
  - **ops 工业数据面板（默认）**：深石墨底 `#080b0f`、荧光青 `#35e0c0` 强调...
  - 新增 `app/utils/sql_guard.py`：SQL 关键字白名单校验（禁止 DROP/DELETE/GRANT）
  ```
- 旧版本日志**保持原样**，不要回头修改历史条目

## 第二步：三份 Word 文档同步

文件固定在 `docs/` 目录：
- `tag_platform_需求规格说明书.docx`
- `tag_platform_方案设计文档.docx`
- `tag_platform_测试与验收报告.docx`

必须逐条核对的章节：
| 文档 | 必须更新的章节 |
|------|--------------|
| 需求规格说明书 | 版本头、功能点、接口清单、验收标准、限制与约束 |
| 方案设计文档 | 版本头、架构图、ER 图/表结构、核心模块实现、配置设计 |
| 测试与验收报告 | 版本头、测试覆盖矩阵、问题清单（问题 → 根因 → 修复）、最终验收结论 |

**版本号要同步到三处**：封面标题、目录页、页眉页脚。

修改 Word 文档使用 `trae-remote-official:office-plugin:docx` 技能。

## 第三步：提交与推送

### 提交顺序（重要）

**一个版本号一个 commit**，不要把多个版本的改动打包进同一个 commit。原因：`git log --oneline` 需要能一眼看出哪个 commit 对应哪个版本号。

推荐 commit 序列：
```
feat(V1.7): P0 安全加固 + 前端三主题切换 + SQL Guard
docs: README 同步 V1.7（三主题切换 + SQL Guard + 目录结构 + secret_key 说明）
docs: 三份 Word 文档同步 V1.7（需求/方案/测试）
```

每一条 commit message 遵循这个 shape：
```
<type>(<scope>): <一句话摘要>

正文：
- 文件 A：改了什么 + 为什么
- 文件 B：改了什么
```

常用 `<type>`：
- `feat` 新功能 / 新模块
- `fix` 明确 bug 修复
- `refactor` 结构或命名重构（功能不变）
- `security` 安全加固
- `docs` README 或 Word 文档更新
- `test` 测试用例新增/修复

### 推送

```powershell
git add .
git commit -m "feat(VX.X): ..."
git push -u origin master   # 首次建立 upstream 跟踪，后续只需 git push
```

推送完成后必须确认：
```powershell
git status                 # 输出应为 "Your branch is up to date with 'origin/master'"
git log --oneline -3       # 最后一条是刚推的那条
```

### 注意事项

- **不要** `force push` 覆盖 `origin/master`。如果本地 master 与远程 master 分叉，先用 `git pull --rebase origin master` 对齐再推。
- **不要**把 `node_modules`、`__pycache__`、`data/*.db` 加进提交；`.gitignore` 已覆盖。
- **不要**删除 `.git` 里的锁文件（比如 `index.lock`、`HEAD.lock`），它们可能被系统自动移入回收站——如果被移走，要告诉用户手动从桌面回收站还原，Agent 不负责恢复。

## 第四步：README 最终自检清单

提交前对照这个 checklist 再过一遍：

- [ ] 版本号在三处出现且一致（目录结构注释里不含版本号，所以只需检查快速开始、更新日志、顶部简介）
- [ ] 新增文件都进了目录结构注释
- [ ] 废弃功能已标注「V1.X 起移除」而不是静默删除
- [ ] 默认账号和实际运行行为一致
- [ ] 界面风格切换章节的强调色/侧栏宽度数字是真实值
- [ ] 更新日志里每个 bullet 有具体文件名或 API，不是笼统的「重构前端」

## 反模式

- 把 README 同步做成一个 commit、代码实现做成另一个 commit，但 commit message 里不提对应关系 → 后续 `git log --grep="V1.7"` 找不到完整上下文。
- 回头修改历史版本的更新日志（比如把 V1.6 的条目内容改正文）→ 用追加新条目替代。
- 版本号 bump 后，目录结构注释里不补新文件 → 下次有人看 README 会不知道这些文件是什么。
- 同时写 README 和 Word 文档但忘了用同一份 changelog 草稿 → 两份文档的版本号和变更列表很容易不一致。做法：先写 README 的更新日志，**复制**一份作为 Word 文档的版本历史页底稿，再扩写成更详细的正式段落。
