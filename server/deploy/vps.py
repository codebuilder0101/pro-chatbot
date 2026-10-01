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

import base64
import hashlib
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
    """Envia um arquivo pelo stdin de um `base64 -d`, conferindo o sha256.

    Nao usa SFTP de proposito. O subsistema SFTP deste servidor recusa abrir
    caminho em /tmp com ENOENT, e no Git Bash existe uma segunda armadilha: o
    MSYS reescreve `/tmp/x` para `C:/Users/.../Temp/x` ANTES de o caminho
    chegar aqui, entao o arquivo e' criado no lugar errado sem erro nenhum.
    Mandar o conteudo por stdin do `exec` nao passa por nenhum dos dois.

    Em Git Bash, exporte MSYS_NO_PATHCONV=1 ao passar caminhos remotos.
    """
    data = Path(local).read_bytes()
    esperado = hashlib.sha256(data).hexdigest()

    stdin, stdout, stderr = client.exec_command(
        f"base64 -d > '{remote}' && sha256sum '{remote}'"
    )
    stdin.write(base64.b64encode(data).decode())
    stdin.channel.shutdown_write()

    saida = stdout.read().decode().strip()
    erro = stderr.read().decode().strip()
    codigo = stdout.channel.recv_exit_status()

    if codigo != 0 or not saida.startswith(esperado):
        raise OSError(
            f"falha ao enviar {local} -> {remote}: codigo {codigo}; "
            f"sha256 esperado {esperado}, recebido {saida.split(' ')[0] or '(nada)'}"
            + (f"; {erro}" if erro else "")
        )
    print(f"enviado: {Path(local).name} -> {remote}  ({len(data) / 1024:.0f} KB, sha256 ok)")


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
