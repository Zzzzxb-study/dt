# 长江学堂 · 十五周年题库在线练习

PC / 手机浏览器共用一个网站。管理员开通账号，无注册接口。四板块多选练习、顺序练习、随机练习、限时模拟、个人错题重练和手动剔除，数据跟随账号保存。

## 本地启动（Windows）

安装 Python 3.12 或更新版本后，可双击项目根目录的 `启动练习.cmd`。首次运行会安装依赖、初始化题库，并在本机提示创建管理员；没有内置密码。浏览器会自动打开，保持启动窗口开启即可使用。以下是等价的手动步骤。

需要 Python 3.12 或更新版本。安装依赖：

```bat
python -m pip install --target .deps -r requirements.txt
python manage.py migrate
python manage.py import_bank
python manage.py createsuperuser
python tools/local_server.py
```

打开 http://127.0.0.1:8000 。管理员密码由 `createsuperuser` 在本地交互输入，没有内置账号或共享密码。已在当前项目安装 `.deps` 时无需重复安装。使用的 Python 必须与依赖安装时一致。

管理员登录后进入“账号管理”创建学员，支持 UTF-8 CSV 批量导入。空白模板可在页面下载。表头为 `username,first_name,password`。初始密码至少 10 位；学员首次登录强制改密。停用、重置或用户修改密码会撤销其他登录会话。

题目维护入口为 `/admin/`。可按板块、题型、启用状态筛选，查看原始文本、来源文件、页码和待复核项。现有来源页码指 PDF 物理页码，可能与页脚印刷页码不同。

## 题库导入与复核

`data/questions.json` 保存所有识别题目，包括待复核题目；`data/import-report.md` / `.json` 保存计数与异常详情。五份 PDF 完整保留。标准答案在导入时从题干分离，练习前不公开答案。

```bat
python manage.py import_bank --parse-pdfs
```

默认只新增题目，不覆盖管理员已经修改的记录。明确需要用文件覆盖现有题目时：

```bat
python manage.py import_bank --update
```

重新导入不删除历史记录，也不修改历史练习的题目快照。PDF 新增或改名会改变来源标识，应先检查导入报告。待复核题默认禁用，管理员核对原文并补齐后可启用。来源中的业务答案按原题库保存，程序校验不等于业务正确性审定；没有解析时不生成虚构解析。

非车险与健康险按独立来源分板块；涉及雇员伤病的责任险不因关键词被自动移入健康险。

## 练习规则

- 顺序练习优先选取当前账号尚未完成的顺序题；所有已完成后从头循环。已有练习可在首页或记录页继续。
- 随机练习在所选板块与题型范围无重复抽题，最多 300 题。题量不足时提示实际数量。
- 普通练习提交单题后展示标准答案和原有解析；单次作答不允许覆盖，重新练习会创建新记录。
- 多选题必须选项集合完全一致才算对。简答题写下答案或自行思考，再对照参考答案标记掌握程度，不使用 AI 判分。
- 模拟默认 50 题、60 分钟，可修改；只考客观题，未答计错，每题等权折算百分制。该规则是训练规则，不等同正式竞赛规则。
- 模拟答案逐题提交后保存，可返回修改；仅选中但未点击“保存答案并继续”的选项未保存。交卷后统一公布答案。刷新和重新登录保留服务器已保存内容。
- 服务器截止时间控制封卷，超时请求无法继续保存答案；后台没有常驻计时任务，无访问的过期模拟会在下次打开时按原截止状态完成封卷，成绩不受延迟影响。
- 答错进入个人错题本，同题累计错误次数。答对不自动剔除；手动剔除保留历史；再次答错重新加入。错题重练最多取当前筛选的 300 题，待复核禁用题不参与出题。
- 首页正确率仅统计已判定作答（包含简答自评），未交卷模拟不计入正确率；已练题量按已提交的不同题目去重。

## 云服务器部署（Linux）

源码仓库：https://github.com/Zzzzxb-study/dt 。首次部署可以直接在服务器拉取源码，无需上传压缩包：

```sh
git clone https://github.com/Zzzzxb-study/dt.git ~/cjpractice15
cd ~/cjpractice15
python3 tools/prepare_cloud.py
```

以上准备工具面向本项目已确认的腾讯云 `tk-web-1` Caddy 接入场景，只生成新项目配置，不启动容器或修改旧代理。如果目录或 `.env` 已存在，请先确认现有部署状态，不要覆盖。

如果服务器已由 `tk-web-1` 等现有 Caddy 容器占用 80/443，使用 `deploy/复用现有Caddy.md` 中的独立接入方案和 `compose.existing-caddy.yaml`，不要启动默认代理配置争用端口。

准备 Docker Engine 与 Compose，域名解析到服务器，开放 80/443。将整个项目上传服务器（排除 `.deps`、`.venv`、`.env`、`local.sqlite3`、`tmp`、`staticfiles`）。官方生产检查参考：https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/ 。

```sh
cp .env.example .env
```

在服务器上编辑 `.env`：`DOMAIN` 为纯域名，`SECRET_KEY` 使用至少 50 字符随机值，`POSTGRES_PASSWORD` 使用随机数据库密码。可用 `openssl rand -hex 32` 分别生成，两次生成不同值。不要把 `.env` 加入代码仓库。

```sh
docker compose build
docker compose up -d db
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py import_bank
docker compose run --rm web python manage.py collectstatic --noinput
docker compose run --rm web python manage.py createsuperuser
docker compose run --rm web python manage.py check --deploy
docker compose up -d
```

Caddy 自动申请 HTTPS 证书；需要域名有效解析及 80/443 可从公网访问。应用与数据库不直接映射到公网端口。应用使用非 root 用户；数据库和证书采用命名卷持久化。不要执行 `docker compose down -v`，该命令会删除数据库卷。

若构建时访问官方 PyPI 不稳定，可添加 `--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple` 使用清华 HTTPS 镜像。Dockerfile 保留固定版本，设置下载超时和重试；不关闭证书校验。现有 Caddy 方案的完整命令见 `deploy/复用现有Caddy.md`。

登录限制采用数据库记录：单账号连续失败 5 次或同一连接地址 40 次后，在 15 分钟窗口内限制登录。反向代理默认情况下连接地址是代理地址，40 次为共享保护阈值；大量同时使用时应在受控代理层补充按真实 IP 的限流，不信任浏览器传入的转发头。

升级：先备份，再上传代码，`docker compose build`、`docker compose run --rm web python manage.py migrate`、`docker compose run --rm web python manage.py collectstatic --noinput`、`docker compose up -d`。仅有新增题时运行默认导入；覆盖题目请先审阅报告。

### 数据备份与恢复

在服务器保管 `.env`，并定期备份数据库与原始题库。数据库备份命令（Linux）：

```sh
mkdir -p backups
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > backups/practice.dump
```

恢复会替换目标数据库中的表和数据，只在确认目标正确并停止应用后执行：

```sh
docker compose stop web
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < backups/practice.dump
docker compose start web
```

## 测试

```bat
python manage.py test practice.tests
python manage.py check
python manage.py collectstatic --noinput
```

附加校验：`python tools/check_bank.py` 校验已启用题目数据约束；`python tools/check_deployment.py` 在不输出临时密钥的情况下运行生产配置检查。

本地使用 SQLite 验证主要业务；正式并发使用 PostgreSQL。模拟保存和交卷通过父会话行锁串行化，数据库对会话题目、错题条目施加唯一约束。正式上线仍需在服务器验证 HTTPS、备份恢复及实际并发量。

## UI 风格

用户批准 diagram-design 默认风格：背景 `#f5f5f5`、文字 `#2d3142`、强调色 `#bf4520`，细线边框、少量圆角、不使用阴影。借用视觉规则而非把交互页面画成 SVG 图。中文使用系统黑体回退，英文优先 Geist / Instrument Serif；本项目不请求外部字体服务，未安装的字体回退到本机字体。桌面侧栏，手机底部导航和可折叠答题卡。


## 全题库通刷与巩固练习

支持全部未练题、累计通刷进度、继续上次练习及按掌握状态安排巩固练习。见 [功能说明](docs/通刷与巩固练习.md) 和 [已有云服务器升级说明](deploy/更新通刷与巩固练习.md)。升级须运行数据库迁移，保留旧记录。
