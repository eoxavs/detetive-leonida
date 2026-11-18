"""Robô de comentários do Detetive Leonida (roda no GitHub Actions a cada 15 min).

Lê pendentes.json. Para cada vídeo cujo horário de publicação já passou e que já está público,
posta o comentário do canal e move o item para feitos.json. Só usa a biblioteca padrão do Python.
Credenciais vêm dos secrets: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
PEND, FEITOS = AQUI / "pendentes.json", AQUI / "feitos.json"
API = "https://www.googleapis.com/youtube/v3"


def ler(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def http(url, dados=None, token=None, json_body=None):
    h = {}
    corpo = None
    if token:
        h["Authorization"] = f"Bearer {token}"
    if json_body is not None:
        corpo = json.dumps(json_body).encode()
        h["Content-Type"] = "application/json"
    elif dados is not None:
        corpo = urllib.parse.urlencode(dados).encode()
    req = urllib.request.Request(url, data=corpo, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{e.code} {e.read().decode()[:400]}") from None


def main():
    pend = ler(PEND)
    agora = datetime.now(timezone.utc)
    # renova o acesso em toda execução: se o login quebrar, o job falha e o GitHub avisa por e-mail
    tok = http("https://oauth2.googleapis.com/token", {
        "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"})["access_token"]
    vencidos = [p for p in pend if datetime.fromisoformat(p["publishAt"].replace("Z", "+00:00")) <= agora]
    if not vencidos:
        print(f"login ok; nada a fazer ({len(pend)} aguardando)")
        return
    feitos = ler(FEITOS)
    falhou = False
    for p in vencidos:
        vid = p["video_id"]
        st = http(f"{API}/videos?part=status&id={vid}", token=tok).get("items", [])
        if not st:
            print(vid, "não encontrado; removendo")
            pend.remove(p)
            continue
        if st[0]["status"]["privacyStatus"] != "public":
            print(vid, "ainda não está público; tento de novo depois")
            continue
        try:
            http(f"{API}/commentThreads?part=snippet", token=tok, json_body={"snippet": {
                "videoId": vid, "topLevelComment": {"snippet": {"textOriginal": p["comentario"]}}}})
        except RuntimeError as e:
            print(vid, "ERRO ao comentar:", e)
            falhou = True
            continue
        print(vid, "comentário postado")
        p["comentado_em"] = agora.isoformat(timespec="seconds")
        feitos.append(p)
        pend.remove(p)
    PEND.write_text(json.dumps(pend, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    FEITOS.write_text(json.dumps(feitos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if falhou:
        sys.exit(1)  # o GitHub manda e-mail de falha para o dono do repositório


if __name__ == "__main__":
    main()
