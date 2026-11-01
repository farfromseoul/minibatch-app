"""실험 실행기 (실습리뷰쇼츠 H-D1·H-D6). docker 는 가짜 함수로 바꾼다. python3 -m unittest test_lab_runner"""
import json
import os
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import lab_runner as lr

TOKEN = "test-runner-token-0123456789"


class FakeDocker:
    def __init__(self, code=0, slow=False):
        self.calls, self.code, self.slow = [], code, slow

    def __call__(self, args, **kw):
        self.calls.append(args)
        if self.slow and args[1] == "run":
            raise subprocess.TimeoutExpired(args, kw.get("timeout"))
        if args[1] == "network":
            return subprocess.CompletedProcess(args, 0, "true\n", "")
        return subprocess.CompletedProcess(args, self.code, "", "")


def cfg(**kw):
    env = tempfile.NamedTemporaryFile("w", delete=False)
    env.write("CLAUDE_CODE_OAUTH_TOKEN=x\n")
    env.close()
    os.chmod(env.name, 0o600)
    return lr.Config(data_dir="/Volumes/Data/minibatch", env_file=env.name, token=TOKEN, **kw)


BODY = {"jobId": "short-20261101-001", "image": "ghcr.io/farfromseoul/minibatch-lab:abc1234",
        "tasks": [{"id": "t1", "timeoutSec": 300}, {"id": "t2"}]}


class ValidateTest(unittest.TestCase):
    def test_accepts_good_body_and_caps_timeout(self):
        r = lr.Runner(cfg(task_timeout_sec=200), run=FakeDocker())
        job, image, tasks = r.validate(BODY)
        self.assertEqual([t["timeoutSec"] for t in tasks], [200, 200])

    def test_rejects_bad_names_and_images(self):
        r = lr.Runner(cfg(), run=FakeDocker())
        for bad in ({**BODY, "jobId": "../etc"}, {**BODY, "image": "alpine:3"}, {**BODY, "image": "x; rm -rf /"},
                    {**BODY, "tasks": [{"id": "T1;ls"}]}, {**BODY, "tasks": []}, {**BODY, "tasks": [{"id": "a"}] * 4},
                    {**BODY, "tasks": [{"id": "a"}, {"id": "a"}]}):
            with self.assertRaises(ValueError, msg=bad):
                r.validate(bad)


class RunTest(unittest.TestCase):
    def test_container_options_isolate_the_task(self):
        d = FakeDocker()
        r = lr.Runner(cfg(), run=d)
        r.start(BODY, background=False)
        run = [c for c in d.calls if c[1] == "run"]
        self.assertEqual(len(run), 2)
        a = run[0]
        for flag in ("--rm", "--read-only", "--cap-drop", "--security-opt", "--pids-limit", "--memory", "--env-file"):
            self.assertIn(flag, a)
        self.assertEqual(a[a.index("--network") + 1], "minibatch-lab")
        self.assertEqual(a[a.index("--dns") + 1], "127.0.0.1")
        self.assertEqual(a[a.index("--user") + 1], "1000:1000")
        self.assertEqual(a[a.index("-v") + 1], "/Volumes/Data/minibatch/jobs/short-20261101-001/lab/t1:/work")
        self.assertIn("HTTPS_PROXY=http://172.31.250.2:3128", a)
        self.assertNotIn("/var/run/docker.sock", " ".join(a))
        self.assertEqual(a[-1], BODY["image"])
        self.assertEqual(r.runs[BODY["jobId"]]["status"], "done")
        self.assertEqual([t["status"] for t in r.runs[BODY["jobId"]]["tasks"]], ["done", "done"])

    def test_timeout_kills_the_container(self):
        d = FakeDocker(slow=True)
        r = lr.Runner(cfg(), run=d)
        r.start({**BODY, "tasks": [{"id": "t1"}]}, background=False)
        self.assertIn(["docker", "kill", "lab-short-20261101-001-t1"], [c[:3] for c in d.calls])
        self.assertEqual(r.runs[BODY["jobId"]]["tasks"][0]["status"], "killed")

    def test_one_job_at_a_time(self):
        r = lr.Runner(cfg(), run=FakeDocker())
        r._lock.acquire()
        with self.assertRaises(lr.BusyError):
            r.start(BODY, background=False)

    def test_health_checks_internal_network_and_env_file_mode(self):
        c = cfg()
        r = lr.Runner(c, run=FakeDocker())
        self.assertEqual(r.health()["status"], "ok")
        os.chmod(c.env_file, 0o644)
        self.assertEqual(r.health()["envFile"], "missing_or_open")


class HttpTest(unittest.TestCase):
    def setUp(self):
        self.runner = lr.Runner(cfg(), run=FakeDocker())
        self.server = lr.make_server(self.runner, "127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()

    def req(self, method, path, body=None, token=TOKEN):
        r = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                   headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=5) as res:
                return res.status, json.load(res)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_token_required_and_run_status(self):
        self.assertEqual(self.req("POST", "/runs", BODY, token="wrong")[0], 401)
        code, _ = self.req("POST", "/runs", BODY)
        self.assertEqual(code, 202)
        for _ in range(50):
            code, st = self.req("GET", f"/runs/{BODY['jobId']}")
            if st.get("status") == "done":
                break
        self.assertEqual(st["status"], "done")
        self.assertEqual(self.req("POST", "/runs", {**BODY, "image": "evil"})[0], 400)
        self.assertEqual(self.req("GET", "/healthz", token="")[0], 200)

    def test_config_reads_token_file(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(TOKEN + "\n")
        c = lr.Config.from_env({"LAB_TOKEN_FILE": f.name, "LAB_DATA_DIR": "/d", "LAB_ENV_FILE": "/e"})
        self.assertEqual((c.token, c.network, c.task_timeout_sec), (TOKEN, "minibatch-lab", 600))


if __name__ == "__main__":
    unittest.main()
