"""Administracao dos codigos de acesso da IARA, do seu computador.

Os endpoints de administracao do token server respondem **so' em 127.0.0.1**,
de proposito: nao ha pagina de administracao publicada, entao nao ha o que
atacar de fora. Esta ferramenta fala com eles por dentro do SSH.

    python deploy/codes.py listar
    python deploy/codes.py criar "Clinica Exemplo" --teto 600 --validade 2026-12-31
    python deploy/codes.py criar "Outra" --codigo MINHACODE
    python deploy/codes.py desativar ABCD2345
    python deploy/codes.py ativar ABCD2345
    python deploy/codes.py remover ABCD2345

Credenciais do VPS vem do ambiente, como em deploy/vps.py:
    VPS_HOST, VPS_USER (padrao root), VPS_PASSWORD, VPS_PORT (padrao 22)
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vps import connect  # noqa: E402

APP = "/var/www/pro-chatbot"
BASE = "http://127.0.0.1:8099"


def _executar(client, metodo: str, rota: str, corpo: dict | None = None) -> tuple[int, str]:
    """Chama o token server por dentro do VPS, com o token de admin do .env."""
    partes = [
        "TOKEN=$(grep -E '^ADMIN_TOKEN=' " + APP + "/.env | cut -d= -f2-)",
        "; test -n \"$TOKEN\" || { echo 'ADMIN_TOKEN ausente no .env'; exit 2; }",
        f"; curl -s -o /tmp/_codes_out -w '%{{http_code}}' -X {metodo} '{BASE}{rota}'",
        " -H \"x-admin-token: $TOKEN\" -H 'content-type: application/json'",
    ]
    if corpo is not None:
        partes.append(" -d " + shlex.quote(json.dumps(corpo, ensure_ascii=False)))
    partes.append("; echo; cat /tmp/_codes_out; rm -f /tmp/_codes_out")

    chan = client.get_transport().open_session()
    chan.exec_command("".join(partes))
    saida = b""
    while True:
        if chan.recv_ready():
            saida += chan.recv(65536)
        if chan.exit_status_ready() and not chan.recv_ready():
            break
    while chan.recv_ready():
        saida += chan.recv(65536)

    texto = saida.decode("utf-8", "replace").strip()
    linhas = texto.split("\n", 1)
    try:
        status = int(linhas[0].strip())
    except ValueError:
        return 0, texto
    return status, (linhas[1] if len(linhas) > 1 else "")


def _imprimir_tabela(codigos: list[dict]) -> None:
    if not codigos:
        print("nenhum codigo cadastrado")
        return
    print(
        f"{'CODIGO':<10} {'EMPRESA':<26} {'ATIVO':<6} {'VALIDADE':<11} "
        f"{'USADOS':>7} {'RESERV':>7} {'TETO':>7} {'SESSOES':>8}"
    )
    print("-" * 92)
    for c in codigos:
        print(
            f"{c['codigo']:<10} {(c['empresa'] or '')[:25]:<26} "
            f"{'sim' if c['ativo'] else 'nao':<6} {(c['validade'] or '-'):<11} "
            f"{c['minutos_usados']:>7} {c['minutos_reservados']:>7} "
            f"{(c['teto_minutos'] if c['teto_minutos'] is not None else '-'):>7} "
            f"{c['sessoes']:>8}"
        )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="acao", required=True)

    sub.add_parser("listar", help="mostra todos os codigos e o consumo")

    c = sub.add_parser("criar", help="cria um codigo novo")
    c.add_argument("empresa")
    c.add_argument("--codigo", help="codigo fixo; sem isto, um e' sorteado")
    c.add_argument("--teto", type=int, help="teto de minutos")
    c.add_argument("--validade", help="AAAA-MM-DD")

    for nome, ativo in (("ativar", True), ("desativar", False)):
        s = sub.add_parser(nome, help=f"{nome} um codigo")
        s.add_argument("codigo")
        s.set_defaults(ativo=ativo)

    s = sub.add_parser("remover", help="apaga o codigo de vez")
    s.add_argument("codigo")

    args = p.parse_args()
    client = connect()
    try:
        if args.acao == "listar":
            status, corpo = _executar(client, "GET", "/admin/codes")
            if status == 200:
                _imprimir_tabela(json.loads(corpo)["codigos"])
                return 0

        elif args.acao == "criar":
            payload = {"empresa": args.empresa}
            if args.codigo:
                payload["codigo"] = args.codigo
            if args.teto:
                payload["teto_minutos"] = args.teto
            if args.validade:
                payload["validade"] = args.validade
            status, corpo = _executar(client, "POST", "/admin/codes", payload)
            if status == 200:
                d = json.loads(corpo)
                print(f"criado: {d['codigo']}  ->  {d['empresa']}")
                print("Entregue este codigo a empresa. Ele nao fica dentro do APK.")
                return 0

        elif args.acao in ("ativar", "desativar"):
            status, corpo = _executar(
                client, "PATCH", f"/admin/codes/{args.codigo}", {"ativo": args.ativo}
            )
            if status == 200:
                print(f"{args.codigo}: ativo={args.ativo}")
                return 0

        elif args.acao == "remover":
            status, corpo = _executar(client, "DELETE", f"/admin/codes/{args.codigo}")
            if status == 200:
                print(f"{args.codigo} removido")
                return 0

        print(f"falhou (HTTP {status}): {corpo}", file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
