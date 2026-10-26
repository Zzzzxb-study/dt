"""Read the existing proxy metadata and prepare only the new project's .env."""
import json
import os
import re
import secrets
import socket
import subprocess
from pathlib import Path

DOMAIN = 'dt.riskai93.cn'
ROOT = Path(__file__).resolve().parent.parent


def prepare_environment(root, network):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', network):
        raise ValueError('Docker 网络名称无效；未写入配置。')
    content = '\n'.join([
        f'DOMAIN={DOMAIN}',
        f'SECRET_KEY={secrets.token_hex(32)}',
        'POSTGRES_DB=practice',
        'POSTGRES_USER=practice',
        f'POSTGRES_PASSWORD={secrets.token_hex(32)}',
        f'CADDY_NETWORK={network}',
        '',
    ])
    # O_EXCL guarantees that a second run cannot replace production credentials.
    descriptor = os.open(Path(root) / '.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(content)


def inspect_field(expression):
    result = subprocess.run(['sudo', 'docker', 'inspect', '--type', 'container', 'tk-web-1', '--format', expression], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def main():
    if os.name != 'posix':
        raise SystemExit('请在目标 Linux 服务器解压后的项目根目录运行。')
    if not (ROOT / 'manage.py').is_file() or not (ROOT / 'compose.existing-caddy.yaml').is_file():
        raise SystemExit('项目文件不完整，请重新上传并解压部署包。')
    try:
        print('读取现有 Caddy 网络与配置挂载（只读）……', flush=True)
        networks = inspect_field('{{json .NetworkSettings.Networks}}')
        mounts = inspect_field('{{json .Mounts}}')
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        raise SystemExit('无法读取 tk-web-1。请先执行 sudo docker ps 检查容器和权限；未修改现有服务。')
    print('Caddy 网络：' + ', '.join(sorted(networks)))
    for mount in mounts:
        print('挂载：' + mount['Source'] + ' -> ' + mount['Destination'])
    if len(networks) != 1:
        raise SystemExit('Caddy 连接多个网络，需先确认应复用哪一个；未生成 .env。请将上面的网络与挂载输出发回。')
    try:
        addresses = sorted({entry[4][0] for entry in socket.getaddrinfo(DOMAIN, 443, socket.AF_INET, socket.SOCK_STREAM)})
        print('域名 A 记录：' + ', '.join(addresses) + '（仍需与腾讯云公网 IP 核对）')
    except socket.gaierror:
        print('当前服务器暂未解析到域名 IPv4；后续需核对解析状态。')
    try:
        prepare_environment(ROOT, next(iter(networks)))
        print('新题库 .env 已生成，权限 600；密钥未显示。')
    except FileExistsError:
        raise SystemExit('项目已有 .env，为避免覆盖原有配置，本次未改写。请告知已有部署情况。')
    print('准备完成：尚未启动新容器、未修改旧 Caddy。请将以上输出发回，不要发送 .env 内容。')


if __name__ == '__main__':
    main()
