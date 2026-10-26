"""Connect the confirmed site to the existing Caddy, with validation and rollback."""
import argparse
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

DOMAIN = 'dt.riskai93.cn'
HOST_CONFIG = Path('/home/ubuntu/TK/deploy/Caddyfile')
CONTAINER_CONFIG = '/etc/caddy/Caddyfile'
PROXY = 'tk-web-1'
APP = 'cjpractice15-practice-app-1'
SITE = b'\n\n# cjpractice15: managed site\ndt.riskai93.cn {\n    encode zstd gzip\n    reverse_proxy cjpractice15-app:8000\n}\n'


def write_in_place(path, data):
    # Single-file bind mounts must retain the same inode.
    with path.open('r+b') as stream:
        stream.seek(0)
        stream.write(data)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())


def update_configuration(path, validate, reload_config):
    original = path.read_bytes()
    candidate = original + SITE
    validate(candidate)
    if path.read_bytes() != original:
        raise RuntimeError('Caddyfile changed during validation; stopped without overwriting it.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = path.with_name(path.name + '.backup-' + stamp + '-' + uuid.uuid4().hex[:8])
    descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(original)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        write_in_place(path, candidate)
        reload_config()
    except BaseException as failure:
        write_in_place(path, original)
        try:
            reload_config()
        except BaseException as rollback_failure:
            raise RuntimeError(f'Reload failed and rollback reload failed. Original file restored; backup: {backup}') from rollback_failure
        raise failure
    return backup


def docker(*args, data=None):
    result = subprocess.run(['docker', *args], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
    if result.returncode:
        # Never print the config body or environment variables.
        detail = result.stderr.decode('utf-8', errors='replace')[-4000:]
        raise RuntimeError('Docker/Caddy command failed:\n' + detail)
    return result.stdout


def hostnames(value):
    result = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == 'host' and isinstance(child, list):
                result.update(item for item in child if isinstance(item, str))
            else:
                result.update(hostnames(child))
    elif isinstance(value, list):
        for child in value:
            result.update(hostnames(child))
    return result


def main():
    parser = argparse.ArgumentParser(description='检查并接入已确认的题库域名；不会停止或重建现有容器。')
    parser.add_argument('--apply', action='store_true', help='校验通过后备份、新增站点并平滑重载；失败时回退')
    args = parser.parse_args()
    if os.name != 'posix' or os.geteuid() != 0:
        raise SystemExit('请在目标服务器使用 sudo python3 tools/connect_domain.py --apply 执行。')
    mounts = json.loads(docker('inspect', '--type', 'container', PROXY, '--format', '{{json .Mounts}}'))
    expected = [m for m in mounts if m.get('Destination') == CONTAINER_CONFIG]
    if len(expected) != 1 or Path(expected[0]['Source']).resolve() != HOST_CONFIG.resolve() or not HOST_CONFIG.is_file():
        raise SystemExit('Caddy 挂载位置与已确认路径不同，未作更改。请发回此提示。')
    proxy_networks = json.loads(docker('inspect', PROXY, '--format', '{{json .NetworkSettings.Networks}}'))
    app_networks = json.loads(docker('inspect', APP, '--format', '{{json .NetworkSettings.Networks}}'))
    shared = set(proxy_networks) & set(app_networks)
    if not shared or not any('cjpractice15-app' in (app_networks[n].get('Aliases') or []) for n in shared):
        raise SystemExit('现有 Caddy 与题库应用缺少共享网络或指定别名，未作更改。')
    config = json.loads(docker('exec', PROXY, 'caddy', 'adapt', '--config', CONTAINER_CONFIG, '--adapter', 'caddyfile'))
    if DOMAIN in hostnames(config):
        raise SystemExit('现有配置已经包含 dt.riskai93.cn；未重复添加。请发回此提示以检查已有路由。')
    print('已确认配置挂载和容器网络。计划新增：dt.riskai93.cn -> cjpractice15-app:8000', flush=True)
    if not args.apply:
        print('只读检查结束。需要应用时运行 sudo python3 tools/connect_domain.py --apply。')
        return

    def validate(candidate):
        # Reading from stdin avoids writing an invalid config to the live mount.
        # The working directory preserves relative import resolution.
        docker('exec', '-i', '-w', '/etc/caddy', PROXY, 'caddy', 'validate', '--config', '-', '--adapter', 'caddyfile', data=candidate)
        print('新增配置校验通过。', flush=True)

    def reload_config():
        docker('exec', PROXY, 'caddy', 'reload', '--config', CONTAINER_CONFIG, '--adapter', 'caddyfile')

    backup = update_configuration(HOST_CONFIG, validate, reload_config)
    print('配置备份：' + str(backup))
    print('Caddy 已平滑重载。请继续验证 https://dt.riskai93.cn/login/；首次申请证书可能需要等待。')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(str(exc))
