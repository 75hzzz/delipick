"""Maintainer validation, requiring both conventional and -Demo stacks running."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from datetime import date

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".local_validation"


def main():
    OUT.mkdir(exist_ok=True)
    env = dict(os.environ)
    if os.name == "nt":
        env["PATH"] = str(Path(env["LOCALAPPDATA"]) / "Programs/DockerDesktop/resources/bin") + os.pathsep + env["PATH"]
    docker = shutil.which("docker", path=env["PATH"])
    def command(args):
        result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout
    # Compare the running Docker image with this checkout, not archived reports.
    modules = ['main.py', 'recommend_logic.py', 'recommendation_rules.py',
               'recommendation_scoring.py', 'update_delivery.py',
               'vector_search.py', 'candidate_recall.py']
    core_expected = {name: hashlib.sha256((ROOT / 'delipick_server' / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
                     for name in modules}
    code = """import hashlib,json,platform
from pathlib import Path
from delipick_server import main,vector_search
c=main.get_db_connection()
with c.cursor() as cur:
 cur.execute('SELECT VERSION() v'); version=cur.fetchone()['v']
 counts={}
 for table in ('categories','restaurants','menus','menu_flavors','reviews','menu_tag_map'):
  cur.execute('SELECT COUNT(*) n FROM '+table); counts[table]=cur.fetchone()['n']
c.close()
files=['main.py','recommend_logic.py','recommendation_rules.py','recommendation_scoring.py','update_delivery.py','vector_search.py','candidate_recall.py']
hashes={name:hashlib.sha256((Path('/app/delipick_server')/name).read_bytes().replace(bytes([13,10]),bytes([10]))).hexdigest() for name in files}
print(json.dumps({'counts':counts,'points':vector_search.client().count(vector_search.collection(),exact=True).count,'core_sha256':hashes,'python':platform.python_version(),'mysql':version,'qdrant':vector_search.client().info().version}))
"""
    records = []
    for mode, project, port in (("existing", "delipick-integrated", 18086), ("demo", "delipick-integrated-demo", 18087)):
        with urlopen(f"http://127.0.0.1:{port}/deployment/info", timeout=10) as response:
            if json.load(response)["query_mode"] != "replay":
                raise RuntimeError("This automated checker requires a replay stack; do not send test requests to a live paid API")
        prefix = [docker, "compose", "-p", project, "exec", "-T", "api"]
        before = json.loads(command([*prefix, "python", "-c", code]))
        assert before["core_sha256"] == core_expected
        tests = command([*prefix, "python", "-m", "pytest", "delipick_server/tests", "-q", "-p", "no:cacheprovider", "--junitxml=/tmp/integration-tests.xml"])
        xml = command([*prefix, "cat", "/tmp/integration-tests.xml"])
        (OUT / f"{mode}_tests.xml").write_text(xml, encoding="utf-8")
        result = ET.fromstring(xml)
        suites = list(result) if result.tag == "testsuites" else [result]
        test_counts = {key: sum(int(suite.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}
        command([*prefix, "python", "-m", "delipick_server.deployment.initialize"])
        after = json.loads(command([*prefix, "python", "-c", code]))
        assert before == after, "Reinitialization changed data counts, code or vector point counts"
        with urlopen(f"http://127.0.0.1:{port}/deployment/info", timeout=10) as response:
            info = json.load(response)
        assert info["dataset_mode"] == mode
        assert info["fictional_dataset"] == (mode == "demo")
        http = []
        for text in info["examples"]:
            request = Request(f"http://127.0.0.1:{port}/recommendations", data=json.dumps({"preference_text": text, "user_type": "gourmet", "limit": 5}).encode("utf-8"), headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=30) as response:
                data = json.load(response)
                assert response.status == 200 and data["count"] > 0
                http.append({"status": response.status, "count": data["count"]})
        record = {"mode": mode, "tests": test_counts, "runtime": before, "reinitialization_preserved_counts": True, "http_examples": http}
        records.append(record)
        print(json.dumps({"mode": mode, "tests": test_counts, "counts": before["counts"], "points": before["points"]}), flush=True)
    # A disposable external Git metadata directory tests ignore rules without
    # adding Git history or a remote to the new working copy.
    with tempfile.TemporaryDirectory(prefix="delipick-ignore-") as directory:
        gitdir = Path(directory) / "metadata.git"
        command(["git", "init", "--bare", str(gitdir)])
        process = subprocess.run(["git", f"--git-dir={gitdir}", f"--work-tree={ROOT}", "ls-files", "--others", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True, check=True)
        public = [name.decode("utf-8") for name in process.stdout.split(b"\0") if name]
    forbidden = []
    for name in public:
        path = ROOT / name
        if (path.name.startswith(".env") and path.name != ".env.example") or path.suffix in {".sql", ".jks", ".keystore"}:
            forbidden.append(name)
        if name.startswith("delipick_server/data/") and not name.startswith("delipick_server/data/demo/"):
            forbidden.append(name)
        if path.suffix != ".gz" and re.search(rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}", path.read_bytes()):
            forbidden.append(name)
    assert not forbidden, f"Review potentially private publishable paths: {forbidden}"
    report = {"date": date.today().isoformat(), "app_files_checked": 0, "verified_core_modules": 7,
              "git_metadata_or_remote_created": False, "publishable_files_checked": len(public),
              "private_dump_env_raw_json_excluded": True, "known_api_key_pattern_found": False,
              "flutter_runtime_tested": False, "reason": "This script checks Docker; Flutter validation is recorded separately.", "stacks": records}
    (OUT / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 통합본 검증 결과", "", f"검증일 {date.today().isoformat()}", "",
             "핵심 서버 모듈을 현재 체크아웃의 체크섬과 대조했다. 이 스크립트는 Docker 검사이며 Flutter 검사는 포함하지 않는다.", "",
             "| 실행 환경 | 테스트 | 실패 | 오류 | 메뉴 | Qdrant 포인트 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in records:
        lines.append(f"| {row['mode']} | {row['tests']['tests']} | {row['tests']['failures']} | {row['tests']['errors']} | {row['runtime']['counts']['menus']} | {row['runtime']['points']} |")
    lines.extend(["", "기존 SQL 가져오기와 가상 샘플을 서로 다른 프로젝트·볼륨에서 실행했다. 두 환경에서 전체 계산 대비 추천 ID·순서·점수, 맛 수치 조합, 가격·카테고리·인식한 제외 조건, Qdrant 장애 503, API 키 없는 live 거절을 검사했다. 각 환경의 실제 HTTP 예시 네 개도 정상 반환했다.", "",
                  "초기화를 한 번 더 실행해 SQL 행 수와 Qdrant 포인트 수가 변하지 않음을 확인했다. 비밀번호·실제 SQL·수집 JSON을 Git이 포함할 목록에서 제외하는지 검사했고 알려진 OpenAI 키 패턴은 발견하지 않았다. 이것이 모든 비밀정보·저작권·개인정보를 보장하는 감사는 아니다.", "",
                  "이 테스트는 고정 예시의 회귀 검사이며 독립 자연어 정확도나 전국 규모 성능 검증은 아니다. 이전 성능 측정은 docs/RESULTS.md를 참고한다."])
    (OUT / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
