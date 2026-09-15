"""PC에서 수집한 결과를 GitHub 저장소에 올리고(앱이 읽음), 실행 전에는 앱에서 바꾼 단지 목록을 내려받는다.
git 설치 없이 GitHub API만 사용. 설정은 local_config.json (또는 환경변수 GITHUB_TOKEN/GITHUB_REPO).

  python collector/publish.py pull   # GitHub의 config/complexes.json → 로컬 (앱에서 추가/제거한 단지 반영)
  python collector/publish.py push   # 로컬 data/, config/ → GitHub (한 번의 커밋)
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
LOCAL_CFG = ROOT / "local_config.json"
API = "https://api.github.com"


def load_local_cfg() -> dict:
    cfg = {}
    if LOCAL_CFG.exists():
        with open(LOCAL_CFG, encoding="utf-8-sig") as f:
            cfg = json.load(f)
    token = (os.environ.get("GITHUB_TOKEN") or cfg.get("github_token") or "").strip()
    repo = (os.environ.get("GITHUB_REPO") or cfg.get("repo") or "").strip()
    if not token or token.startswith("여기에"):
        raise SystemExit("local_config.json 의 github_token 이 비어 있습니다. SETUP.md 6번을 참고해 토큰을 넣어주세요.")
    if not repo or "/" not in repo:
        raise SystemExit("local_config.json 의 repo 값이 'owner/repo' 형식이어야 합니다.")
    return {"token": token, "repo": repo, "branch": cfg.get("branch", "main")}


def gh(c: dict, method: str, path: str, **kw):
    r = requests.request(method, API + path, headers={
        "Authorization": f"Bearer {c['token']}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"}, timeout=30, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub API {method} {path} → {r.status_code}: {r.text[:200]}")
    return r.json() if r.text else None


def pull(c: dict) -> None:
    """앱에서 편집한 단지 목록을 내려받아 로컬 config에 반영 (단지번호 등 로컬에서 채운 값은 유지)."""
    j = gh(c, "GET", f"/repos/{c['repo']}/contents/config/complexes.json?ref={c['branch']}")
    remote = json.loads(base64.b64decode(j["content"]).decode("utf-8"))
    local_path = ROOT / "config" / "complexes.json"
    local = json.load(open(local_path, encoding="utf-8")) if local_path.exists() else {}
    known = {x["name"]: x for x in local.get("complexes", [])}
    merged = []
    for x in remote.get("complexes", []):
        old = known.get(x["name"])
        if old and not x.get("complexNo") and old.get("complexNo"):
            x = {**old, **{k: v for k, v in x.items() if v not in (None, "")}}
        merged.append(x)
    remote["complexes"] = merged
    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(remote, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"[pull] 단지 {len(merged)}개 설정 내려받음")


def push(c: dict) -> None:
    """data/ 와 config/ 전체를 하나의 커밋으로 올림 (Git Data API)."""
    files = [p for p in (ROOT / "data").rglob("*.json")] + [ROOT / "config" / "complexes.json"]
    ref = gh(c, "GET", f"/repos/{c['repo']}/git/ref/heads/{c['branch']}")
    head_sha = ref["object"]["sha"]
    base_tree = gh(c, "GET", f"/repos/{c['repo']}/git/commits/{head_sha}")["tree"]["sha"]
    tree = []
    for p in files:
        content = p.read_text(encoding="utf-8")
        blob = gh(c, "POST", f"/repos/{c['repo']}/git/blobs", json={"content": content, "encoding": "utf-8"})
        tree.append({"path": p.relative_to(ROOT).as_posix(), "mode": "100644", "type": "blob", "sha": blob["sha"]})
    new_tree = gh(c, "POST", f"/repos/{c['repo']}/git/trees", json={"base_tree": base_tree, "tree": tree})
    if new_tree["sha"] == base_tree:
        print("[push] 변경 없음")
        return
    msg = "data: " + dt.datetime.now().strftime("%Y-%m-%d %H:%M") + " (PC)"
    commit = gh(c, "POST", f"/repos/{c['repo']}/git/commits",
                json={"message": msg, "tree": new_tree["sha"], "parents": [head_sha]})
    gh(c, "PATCH", f"/repos/{c['repo']}/git/refs/heads/{c['branch']}", json={"sha": commit["sha"], "force": False})
    print(f"[push] {len(files)}개 파일 업로드 → {commit['sha'][:7]}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "push"
    c = load_local_cfg()
    if cmd == "pull":
        pull(c)
    elif cmd == "push":
        push(c)
    else:
        raise SystemExit("사용법: publish.py pull|push")


if __name__ == "__main__":
    main()
