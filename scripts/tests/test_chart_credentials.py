"""The Helm chart's generated credentials. Needs helm on PATH and PyYAML.

    python -m unittest discover -s scripts/tests -v
"""
import os
import re
import shutil
import subprocess
import unittest

import yaml

CHART = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "helm", "besa-agent-platform")
DEV_VALUES = os.path.join(CHART, "values-dev-8086.yaml")
# Every fixed credential the chart and manifests used to ship with.
OLD_DEFAULTS = re.compile(r"sk-admin|postgrespassword|langfuse-secret-32-chars|langfuse-salt-token|"
                          r"0123456789abcdef0123456789abcdef")


def render(*args):
    out = subprocess.run(["helm", "template", "ci", CHART, *args],
                         capture_output=True, text=True, check=True).stdout
    objects = {(d["kind"], d["metadata"]["name"]): (d.get("stringData") or d.get("data") or {})
               for d in yaml.safe_load_all(out) if d and d.get("kind") in ("Secret", "ConfigMap")}
    return out, objects


@unittest.skipUnless(shutil.which("helm"), "helm is not installed")
class ChartCredentials(unittest.TestCase):
    def test_generated_credentials_are_consistent(self):
        for args in ([], ["-f", DEV_VALUES]):
            with self.subTest(values="dev-8086" if args else "default"):
                text, obj = render(*args)
                self.assertIsNone(OLD_DEFAULTS.search(text), "a fixed default credential is back")
                pg = obj[("Secret", "postgres-secret")]["POSTGRES_PASSWORD"]
                litellm = obj[("Secret", "litellm-secret")]
                langfuse = obj[("Secret", "langfuse-secret")]
                self.assertRegex(pg, r"^[A-Za-z0-9]{24}$")
                # One password per render, even though three templates embed it.
                self.assertIn(f":{pg}@", litellm["DATABASE_URL"])
                self.assertIn(f":{pg}@", langfuse["DATABASE_URL"])
                self.assertRegex(litellm["LITELLM_MASTER_KEY"], r"^sk-[A-Za-z0-9]{32}$")
                self.assertRegex(langfuse["ENCRYPTION_KEY"], r"^[0-9a-f]{64}$")
                self.assertEqual(obj[("Secret", "agent-secret")]["LITELLM_API_KEY"], litellm["LITELLM_MASTER_KEY"])
                self.assertNotIn("LITELLM_API_KEY", obj[("ConfigMap", "agent-config")])

    def test_each_render_generates_new_values(self):
        _, a = render()
        _, b = render()
        for secret, key in [("postgres-secret", "POSTGRES_PASSWORD"), ("litellm-secret", "LITELLM_MASTER_KEY"),
                            ("langfuse-secret", "SALT"), ("langfuse-secret", "ENCRYPTION_KEY")]:
            self.assertNotEqual(a[("Secret", secret)][key], b[("Secret", secret)][key], f"{secret}/{key}")

    def test_explicit_values_win(self):
        _, obj = render("--set", "platform.postgres.password=MyOwnPassword1",
                        "--set", "platform.litellm.masterKey=sk-mine")
        self.assertEqual(obj[("Secret", "postgres-secret")]["POSTGRES_PASSWORD"], "MyOwnPassword1")
        self.assertIn(":MyOwnPassword1@", obj[("Secret", "langfuse-secret")]["DATABASE_URL"])
        self.assertEqual(obj[("Secret", "agent-secret")]["LITELLM_API_KEY"], "sk-mine")


if __name__ == "__main__":
    unittest.main()
