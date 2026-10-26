# 腾讯云现有 Caddy 接入方案

已知：Ubuntu 26.04 x86_64，约 2 GiB 内存，Docker 与 Compose 已安装；`tk-web-1` 使用 `caddy:2` 占用公网 80/443，现有 `tk-app-1`、`tk-db-1` 正在运行。目标域名：`dt.riskai93.cn`。

## 隔离方式

新题库以独立 Compose 项目 `cjpractice15` 部署，使用 `compose.existing-caddy.yaml`，不使用默认 `compose.yaml`。新数据库只连接题库私有网络，新应用同时连接现有 Caddy 的网络，通过唯一别名 `cjpractice15-app` 被代理。保留 `127.0.0.1:18080` 仅供服务器本机诊断，不需要腾讯云开放新公网端口。

静态文件由应用通过 WhiteNoise 提供，现有 Caddy 无须挂载新静态文件目录。HTTPS 与新域名由现有 Caddy 统一处理。两名 Gunicorn 工作进程作为初始设置，实际并发容量须在服务器验证。

## 先做只读检查

可将 `cjpractice15-deploy.tar.gz` 上传到服务器 `/home/ubuntu/`，解压到全新的 `~/cjpractice15` 目录，再运行 `python3 tools/prepare_cloud.py`。此准备工具读取现有 Caddy 网络和挂载，在新项目内以 600 权限创建 `.env`，不会输出密钥、不会覆盖已有 `.env`、不会启动容器或修改旧 Caddy。它会打印后续接入所需的挂载位置与实际网络名。请勿重复解压覆盖已有部署；复用已有目录前先确认文件状态。

逐条检查配置挂载路径、真实网络名、域名解析，避免猜测旧项目位置：

```sh
sudo docker inspect tk-web-1 --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
sudo docker inspect tk-web-1 --format '{{range $name, $config := .NetworkSettings.Networks}}{{println $name}}{{end}}'
getent ahostsv4 dt.riskai93.cn
```

这些命令不读取密码或环境变量。不要粘贴容器完整 inspect 内容、`.env` 或私钥。

## 部署新应用

上传当前源码包到新的独立目录，使用 `deploy/existing-caddy.env.example` 作为根目录 `.env` 模板。仅在服务器生成并填写两份独立随机值作为 `SECRET_KEY` 和数据库密码，并根据实际检查结果填写 `CADDY_NETWORK`。`.env` 权限设为 `600`。

以下命令必须在新题库根目录执行；不会调用旧 `tk` 项目的 Compose 文件：

```sh
sudo docker compose -f compose.existing-caddy.yaml config --quiet
sudo docker compose -f compose.existing-caddy.yaml build
sudo docker compose -f compose.existing-caddy.yaml up -d practice-db
sudo docker compose -f compose.existing-caddy.yaml run --rm practice-app python manage.py migrate
sudo docker compose -f compose.existing-caddy.yaml run --rm practice-app python manage.py import_bank
sudo docker compose -f compose.existing-caddy.yaml run --rm practice-app python manage.py collectstatic --noinput
sudo docker compose -f compose.existing-caddy.yaml run --rm practice-app python manage.py createsuperuser
sudo docker compose -f compose.existing-caddy.yaml run --rm practice-app python manage.py check --deploy
sudo docker compose -f compose.existing-caddy.yaml up -d
```

管理员密码在服务器提示中交互输入，不在聊天中发送。

### Python 下载源连接不稳定

如果镜像构建在 `pip install` 阶段报 `from versions: none`，先检查失败的固定版本是否存在，不直接降级依赖。`sqlparse==0.6.0` 已核对官方 PyPI 和清华镜像，并成功从清华镜像下载。Dockerfile 支持通过构建参数切换 HTTPS 下载源，同时设置 60 秒超时和 5 次网络重试：

```sh
sudo docker compose -f compose.existing-caddy.yaml build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
```

此设置只影响新应用镜像构建，不修改服务器全局 pip 配置。保留依赖固定版本和 TLS 校验，不使用 `--trusted-host` 或 HTTP 源。若服务器通过压缩包安装而没有 `.git`，可单独下载更新后的 Dockerfile，再重新构建；不覆盖 `.env`，不重新运行配置生成器。

## 新增 Caddy 站点

已确认本例挂载为 `/home/ubuntu/TK/deploy/Caddyfile -> /etc/caddy/Caddyfile` 后，可以执行 `sudo python3 tools/connect_domain.py --apply`。该工具会核对实际挂载、共享网络、容器别名及同域名配置；先通过 stdin 校验候选配置，后生成 600 权限备份、保持原文件 inode 写入并平滑重载。校验失败不写文件，重载失败恢复原文件并尝试重新加载原配置。只适用于本项目已确认的服务器路径和容器名称；不输出原配置内容或密钥。

先确定旧 Caddy 的实际配置入口、挂载方式及是否使用通配域名路由。备份现有配置后，将 `deploy/dt.riskai93.cn.caddy` 的站点段新增到正确位置；不要直接覆盖旧文件。已有同域名或通配规则时先检查路由关系，不重复添加。

如果已确认入口是容器内 `/etc/caddy/Caddyfile`，可以用下列命令先校验、后平滑重载：

```sh
sudo docker exec tk-web-1 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo docker exec tk-web-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

校验失败时不要重载。正确入口尚待服务器实际检查，因此当前不提供对现有文件的直接写入命令。若需要回退，只撤销本次新增的站点配置，再校验与重载；不要停止或删除现有容器。

最终检查新域名 HTTPS、登录、静态资源、练习和错题流程，同时检查原网站继续可用。现阶段仅完成本地适配与配置校验，不代表服务器部署已完成。
