"""scripts/new-dev-secrets.ps1 against a fake kubectl that keeps cluster state in a JSON
file. Needs pwsh on PATH and PyYAML; skipped on Windows, where the fake kubectl can't run.

    python -m unittest discover -s scripts/tests -v
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "new-dev-secrets.ps1")

FAKE_KUBECTL = r'''#!PYTHON
import json, os, sys, yaml
path = os.environ["FAKE_KUBE_STATE"]; st = json.load(open(path)); a = sys.argv[1:]
open(os.environ["FAKE_KUBE_LOG"], "a").write(" ".join(a) + "\n")
if a[:2] == ["get", "namespace"]:
    sys.exit(0 if a[2] in st["namespaces"] else 1)
if a[:2] == ["get", "secret"]:
    name, ns = a[2], a[a.index("-n") + 1]
    key = a[a.index("-o") + 1].split(".data.")[1].rstrip("}")
    sec = st["secrets"].get(ns + "/" + name)
    if sec is None:
        sys.stderr.write('Error from server (NotFound): secrets "%s" not found\n' % name); sys.exit(1)
    sys.stdout.write(sec.get(key, "")); sys.exit(0)
if a[:3] == ["apply", "-f", "-"]:
    d = yaml.safe_load(sys.stdin.read())
    st["secrets"][d["metadata"]["namespace"] + "/" + d["metadata"]["name"]] = d["data"]
    json.dump(st, open(path, "w")); sys.exit(0)
sys.stderr.write("fake kubectl: unsupported %s\n" % a); sys.exit(2)
'''


def b64(s):
    return base64.b64encode(s.encode()).decode()


@unittest.skipUnless(shutil.which("pwsh") and os.name == "posix", "needs pwsh and a POSIX shell")
class NewDevSecrets(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        bin_dir = os.path.join(self.tmp.name, "bin")
        os.mkdir(bin_dir)
        kubectl = os.path.join(bin_dir, "kubectl")
        with open(kubectl, "w") as fh:
            fh.write(FAKE_KUBECTL.replace("PYTHON", sys.executable, 1))
        os.chmod(kubectl, 0o755)
        self.state = os.path.join(self.tmp.name, "state.json")
        self.log = os.path.join(self.tmp.name, "calls.log")
        self.env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ["PATH"],
                        FAKE_KUBE_STATE=self.state, FAKE_KUBE_LOG=self.log)
        self.cluster(namespaces=["ai-platform", "agent-apps"])

    def tearDown(self):
        self.tmp.cleanup()

    def cluster(self, namespaces, secrets=None):
        with open(self.state, "w") as fh:
            json.dump({"namespaces": namespaces, "secrets": secrets or {}}, fh)
        open(self.log, "w").close()

    def run_script(self, *args):
        r = subprocess.run(["pwsh", "-NoLogo", "-NoProfile", "-File", SCRIPT, *args],
                           capture_output=True, text=True, env=self.env, timeout=120)
        return r.returncode, r.stdout + r.stderr

    def secrets(self):
        with open(self.state) as fh:
            raw = json.load(fh)["secrets"]
        return {k: {kk: base64.b64decode(v).decode() for kk, v in d.items()} for k, d in raw.items()}

    def test_fresh_cluster_gets_random_consistent_values(self):
        code, out = self.run_script()
        self.assertEqual(code, 0, out)
        s = self.secrets()
        pg, ll = s["ai-platform/postgres-secret"], s["ai-platform/litellm-secret"]
        lf, ag = s["ai-platform/langfuse-secret"], s["agent-apps/agent-secret"]
        self.assertRegex(pg["POSTGRES_PASSWORD"], r"^[A-Za-z0-9]{24}$")
        self.assertRegex(ll["LITELLM_MASTER_KEY"], r"^sk-[A-Za-z0-9]{32}$")
        self.assertEqual(ag["LITELLM_API_KEY"], ll["LITELLM_MASTER_KEY"])
        self.assertRegex(lf["ENCRYPTION_KEY"], r"^[0-9a-f]{64}$")
        self.assertEqual(ll["LANGFUSE_PUBLIC_KEY"], "")

    def test_rerun_keeps_every_value(self):
        self.run_script()
        first = self.secrets()
        code, out = self.run_script()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.secrets(), first)

    def test_langfuse_keys_are_added_without_touching_the_rest(self):
        self.run_script()
        before = self.secrets()["ai-platform/litellm-secret"]["LITELLM_MASTER_KEY"]
        self.run_script("-LangfusePublicKey", "pk-lf-test", "-LangfuseSecretKey", "sk-lf-test")
        ll = self.secrets()["ai-platform/litellm-secret"]
        self.assertEqual((ll["LANGFUSE_PUBLIC_KEY"], ll["LANGFUSE_SECRET_KEY"]), ("pk-lf-test", "sk-lf-test"))
        self.assertEqual(ll["LITELLM_MASTER_KEY"], before)

    def test_values_from_the_old_manifests_are_kept(self):
        self.cluster(["ai-platform", "agent-apps"], {
            "ai-platform/postgres-secret": {"POSTGRES_PASSWORD": b64("postgrespassword")},
            "ai-platform/langfuse-secret": {"ENCRYPTION_KEY": b64("0" * 64), "DATABASE_URL": b64("stale")},
        })
        code, out = self.run_script("-LiteLLMMasterKey", "sk-admin")
        self.assertEqual(code, 0, out)
        s = self.secrets()
        self.assertEqual(s["ai-platform/postgres-secret"]["POSTGRES_PASSWORD"], "postgrespassword")
        self.assertEqual(s["ai-platform/langfuse-secret"]["ENCRYPTION_KEY"], "0" * 64)
        self.assertNotIn("DATABASE_URL", s["ai-platform/langfuse-secret"])
        self.assertEqual(s["ai-platform/litellm-secret"]["LITELLM_MASTER_KEY"], "sk-admin")

    def test_missing_namespace_writes_nothing(self):
        self.cluster(["ai-platform"])
        code, out = self.run_script()
        self.assertNotEqual(code, 0)
        self.assertIn("agent-apps", out)
        self.assertEqual(self.secrets(), {})

    def test_master_key_without_sk_prefix_is_refused(self):
        code, out = self.run_script("-LiteLLMMasterKey", "admin")
        self.assertNotEqual(code, 0)
        self.assertIn("must start with 'sk-'", out)

    def test_secret_values_never_reach_a_command_line_or_the_output(self):
        code, out = self.run_script()
        values = [v for d in self.secrets().values() for v in d.values() if len(v) > 8]
        with open(self.log) as fh:
            calls = fh.read()
        self.assertFalse([v for v in values if v in calls], "a secret value was passed on a kubectl command line")
        self.assertFalse([v for v in values if v in out], "a secret value was printed")
        self.assertIsNone(re.search(r"--from-literal", calls))


if __name__ == "__main__":
    unittest.main()
