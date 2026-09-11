"""Ferramenta de acesso ao VPS: roda comandos e envia arquivos por SSH.

    python deploy/vps.py run "uname -a"
    python deploy/vps.py run-file caminho/script.sh
    python deploy/vps.py put arquivo_local /caminho/remoto

As credenciais vem do ambiente, nunca do codigo:
    VPS_HOST, VPS_USER (padrao root), VPS_PASSWORD, VPS_PORT (padrao 22)

Existe porque o Windows nao tem `sshpass` e o ssh.exe nao aceita senha por
argumento. Paramiko resolve sem instalar nada no servidor.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

# O terminal do Windows abre em cp1252 e a saida do systemd traz setas unicode.
# Sem isto, um "Created symlink /a -> /b" derruba o deploy inteiro.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass


def connect() -> paramiko.SSHClient:
    host = os.environ.get("VPS_HOST", "").strip()
    user = os.environ.get("VPS_USER", "root").strip()
    password = os.environ.get("VPS_PASSWORD", "")
    port = int(os.environ.get("VPS_PORT", "22"))

    if not host or not password:
        sys.exit("defina VPS_HOST e VPS_PASSWORD no ambiente")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=port,
        username=user,
        password=password,
        timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


def run(client: paramiko.SSHClient, command: str, quiet: bool = False) -> int:
    """Executa e transmite a saida enquanto acontece."""
    chan = client.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(command)

    while True:
        if chan.recv_ready():
            data = chan.recv(65536).decode("utf-8", "replace")
            if not quiet:
                sys.stdout.write(data)
                sys.stdout.flush()
        if chan.exit_status_ready() and not chan.recv_ready():
            break

    while chan.recv_ready():
        data = chan.recv(65536).decode("utf-8", "replace")
        if not quiet:
            sys.stdout.write(data)

    return chan.recv_exit_status()


def put(client: paramiko.SSHClient, local: str, remote: str) -> None:
    """Envia um arquivo em blocos.

    Escrito a mao porque `sftp.put()` falha com ENOENT contra este servidor,
    enquanto `sftp.open()` no mesmo caminho funciona. Nao vale investigar o
    porque: o caminho manual e' curto e resolve.
    """
    size = Path(local).stat().st_size
    sftp = client.open_sftp()
    try:
        with open(local, "rb") as src, sftp.open(remote, "wb") as dst:
            dst.set_pipelined(True)
            while True:
                chunk = src.read(65536)
                if not chunk:
                    break
                dst.write(chunk)
        enviado = sftp.stat(remote).st_size
        if enviado != size:
            raise OSError(f"tamanho divergente: local {size}, remoto {enviado}")
        print(f"enviado: {Path(local).name} -> {remote}  ({size / 1024:.0f} KB)")
    finally:
        sftp.close()


def main() -> int:
    if len(sys.argv) < 2:
        sys.exit(__doc__)

    action = sys.argv[1]
    client = connect()
    try:
        if action == "run":
            return run(client, " ".join(sys.argv[2:]))
        if action == "run-file":
            script = Path(sys.argv[2]).read_text(encoding="utf-8")
            remote = "/tmp/_iara_step.sh"
            sftp = client.open_sftp()
            with sftp.open(remote, "w") as fh:
                fh.write(script)
            sftp.close()
            return run(client, f"bash {remote}")
        if action == "put":
            put(client, sys.argv[2], sys.argv[3])
            return 0
        sys.exit(f"acao desconhecida: {action}")
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
