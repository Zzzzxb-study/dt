# 在线练习应用 Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task in this session.

**Goal:** 将当前五份 PDF 题库转为可登录、可练习、可记录个人错题的响应式网站。

**Architecture:** Django 单服务、服务端模板与少量原生浏览器交互。PostgreSQL 用于云部署，SQLite 用于本地验证。每次练习冻结题目快照，服务端控制权限、判分和截止时间。

**Tech Stack:** Django 5.2 LTS、pypdf、PostgreSQL、Gunicorn、Caddy、Docker Compose。

## 文件与任务

- [x] 基础：`manage.py`, `config/{settings,urls,wsgi}.py`, `requirements.txt`；本地依赖放 `.deps/`，不改系统 Python。运行 `python manage.py check`，预期无错误。
- [x] 题库：`practice/importer.py`, `practice/management/commands/import_bank.py`, `practice/tests/test_importer.py`。先测试嵌入式答案拆分、多选与判断归一化、跨页题和选项提取，再实现；命令 `python manage.py test practice.tests.test_importer`。生成逐题 JSON 与待复核报告，保留源文件页码和内容。
- [x] 数据与规则：`practice/models.py`, `practice/services.py`, `practice/tests/test_services.py`。先测试范围过滤、唯一抽题、快照、精确多选、超时封卷、重复交卷、错题状态及用户隔离，再实现。运行 `python manage.py test practice.tests.test_services`。
- [x] 账号与页面：`practice/{forms,views,urls,middleware,admin}.py`, `practice/tests/test_views.py`。测试无注册、越权拒绝、首次改密、停用会话、CSRF、交卷前答案保密、账号批量创建，再实现。
- [x] UI：`templates/practice/*.html`, `static/practice/{app.css,app.js}`。默认 paper #f5f5f5、ink #2d3142、accent #bf4520，无阴影，中文采用本机字体；创建首页、答题、成绩、历史、错题、账号管理，PC 侧栏与手机底栏，浏览器检查 1440px 和 390px。
- [x] 部署：`Dockerfile`, `compose.yaml`, `deploy/Caddyfile`, `.env.example`, `README.md`。容器使用非 root 应用、持久化数据库、HTTPS 反向代理、显式初始化管理员、备份恢复说明。
- [x] 验收：全部自动化测试、源题导入报告、浏览器完整练习与错题流程、静态资源收集、`check --deploy`、容器配置验证。无法执行的生产环境检查如实列出。

## 实现约束

管理员建号、不支持注册；敏感操作只接受带 CSRF 的 POST。管理员重置密码和停用账号撤销会话。所有会话按用户查询，模拟提交前绝不在响应中提供答案。简答自评不参与模拟计分。错题保留历史、手动移除、再次答错重新加入。默认模拟 50 题 60 分钟，不足时明确实际题量。

采用连续执行，用户已批准设计和开发，无需逐步再次确认。项目尚无 Git 仓库，不创建额外工作树。

最终本地验收：50 项测试通过；生产配置检查、迁移完整性、静态资源及 Compose 配置检查通过。Docker 引擎未运行，镜像启动、PostgreSQL 实际并发及云端 HTTPS 留待目标服务器验证，详见 output/验收报告.md。
