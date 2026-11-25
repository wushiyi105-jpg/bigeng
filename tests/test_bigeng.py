"""笔耕离线单测:不联网、不花 token。"""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

from bigeng import agent, cli, mock, tools, web
from bigeng.db import Database

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "draft-sample.json")


def load_sample() -> dict:
    with open(SAMPLE, encoding="utf-8") as f:
        return json.load(f)


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(os.path.join(self.tmp.name, "t.db"))
        s = load_sample()
        self.did = self.db.create_draft(s["title"], s["body"])

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()


class TestTextLayer(unittest.TestCase):
    def test_numbers_extract(self):
        self.assertEqual(tools.numbers("14 天里 3.5% 的人,15 点"), ["14", "3.5%", "15"])

    def test_new_numbers_detects_fabrication(self):
        self.assertEqual(tools.new_numbers("连记 14 天", "连记 14 天,效率翻 3 倍"), ["3"])

    def test_sentences_split(self):
        self.assertEqual(len(tools.sentences("一。二!三?")), 3)

    def test_length_delta_ratio(self):
        d = tools.length_delta("1234", "12")
        self.assertEqual(d["ratio"], 0.5)

    def test_strip_fillers(self):
        self.assertNotIn("其实", tools.strip_fillers("其实这个方案挺好"))

    def test_clamp_title(self):
        self.assertEqual(len(tools.clamp_title("很" * 30)), 20)

    def test_title_candidates_nonempty(self):
        cands = tools.title_candidates(load_sample()["body"])
        self.assertTrue(cands)
        self.assertTrue(all(len(c) <= 20 for c in cands))


class TestDb(BaseCase):
    def test_roundtrip_by_title(self):
        d = self.db.get_draft("下午三点总卡住")
        self.assertEqual(d["id"], self.did)
        self.assertGreater(d["chars"], 100)

    def test_versions_latest(self):
        self.db.add_version(self.did, "polish", "润色后", "去掉了口语")
        v = self.db.latest_version(self.did, "polish")
        self.assertEqual(v["body"], "润色后")

    def test_update_body_and_stats(self):
        self.db.update_body(self.did, "短了")
        self.assertEqual(self.db.get_draft(self.did)["chars"], 2)
        st = self.db.stats()
        self.assertEqual(st["drafts"], 1)

    def test_delete_cascades(self):
        self.db.delete_draft(self.did)
        self.assertEqual(self.db.list_versions(self.did), [])


class TestOfflineAndChecks(BaseCase):
    def test_mock_polish_tidy(self):
        r = mock.polish("第一句 ,  第二句..")
        self.assertIn("第一句, 第二句。", r["body"])

    def test_mock_rewrite_formal(self):
        r = mock.rewrite("我搞了个记录本,挺有用", "formal")
        self.assertIn("做", r["body"])

    def test_mock_shrink_keeps_numbers(self):
        body = load_sample()["body"]
        r = mock.shrink(body)
        self.assertTrue(tools.numbers(r["body"]))
        self.assertLess(tools.chars(r["body"]), tools.chars(body))

    def test_checks_pass_and_fail(self):
        body = load_sample()["body"]
        self.assertEqual(agent.checks(body, body, "polish"), [])
        self.assertTrue(agent.checks(body, "只有一句话,还多出 99% 的数字", "shrink"))

    def test_transform_offline_marks(self):
        d = {"title": "t", "body": load_sample()["body"]}
        r = agent.transform(d, "polish", force_mock=True)
        self.assertTrue(r["offline"])
        self.assertEqual(r["stats"]["before"], tools.chars(d["body"]))


class TestCli(BaseCase):
    def _run(self, argv, db_path):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--db", db_path] + argv)
        return buf.getvalue()

    def test_new_polish_versions(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = os.path.join(tmp.name, "c.db")
        f = os.path.join(tmp.name, "d.txt")
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(load_sample()["body"])
        self.assertIn("已建稿", self._run(["new", f, "--title", "下午三点总卡住"], db_path))
        self.assertIn("离线模式", self._run(["--mock", "polish", "1", "--save"], db_path))
        out = self._run(["versions", "1"], db_path)
        self.assertIn("polish", out)
        self.assertIn("下午三点总卡住", self._run(["list"], db_path))
        tmp.cleanup()


class TestWeb(BaseCase):
    def test_api_run_and_status(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), web._make_handler(self.db, {"api_key": ""}, True))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        port = httpd.server_address[1]
        try:
            body = json.dumps({"id": self.did, "mode": "polish"}).encode("utf-8")
            req = Request(f"http://127.0.0.1:{port}/api/run", data=body,
                          headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=15) as resp:
                r = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(r["offline"])
            self.assertTrue(r["saved"])
            with urlopen(f"http://127.0.0.1:{port}/api/status", timeout=10) as resp:
                self.assertTrue(json.loads(resp.read().decode("utf-8"))["mock"])
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
