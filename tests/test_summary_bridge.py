"""The dashboard imports the explicit handoff, never a second copy of the package.

Hermes host integration is opt-in: HERMES_BRIDGE_HOST_TEST=1. The live lane
(HERMES_BRIDGE_LIVE=1) never stubs inference and may spend provider tokens.
Run with Hermes' Python and PYTHONPATH pointing at its source checkout.
"""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_plugin import load_package

HANDOFF = "blogwatcher_dashboard_summary_bridge"
ROOT = Path(__file__).resolve().parents[1]


class BridgeTests(unittest.TestCase):
    def test_bridge_does_not_repeat_failed_facade_call(self):
        package = load_package()
        bridge = importlib.import_module(package.__name__ + ".summary_bridge")
        calls = []
        failure = TimeoutError("provider timeout")
        def complete(**kw):
            calls.append(kw)
            raise failure
        bridge.bind_context(SimpleNamespace(llm=SimpleNamespace(complete=complete)))
        with self.assertRaises(TimeoutError) as caught:
            bridge.summarize_text("Article", "https://example.org")
        self.assertIs(caught.exception, failure)
        self.assertEqual(len(calls), 1)

    def test_missing_llm_capability_has_typed_error(self):
        package = load_package()
        bridge = importlib.import_module(package.__name__ + ".summary_bridge")
        for ctx in (SimpleNamespace(), SimpleNamespace(llm=None), SimpleNamespace(llm=SimpleNamespace())):
            bridge.bind_context(ctx)
            with self.assertRaises(bridge.CapabilityUnavailable):
                bridge.summarize_text("Article", "https://example.org")

    def test_rejects_unbounded_input_before_inference(self):
        package = load_package()
        bridge = importlib.import_module(package.__name__ + ".summary_bridge")
        calls = []
        def complete(**kw):
            calls.append(kw)
            return {"text": "fixture", "provider": "fixture", "model": "fixture", "usage": {}}
        ctx = SimpleNamespace(llm=SimpleNamespace(complete=complete), on_unload=lambda cb: None)
        bridge.bind_context(ctx)
        for text in ("", " ", "x" * 30001, None):
            with self.subTest(text_length=len(text) if isinstance(text, str) else None):
                with self.assertRaises(ValueError):
                    bridge.summarize_text(text, "https://example.org")
        self.assertEqual(calls, [])

    def test_register_hands_same_package_module_to_dashboard(self):
        package = load_package()
        calls = []
        class Llm:
            def complete(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(text="Fixture summary", provider="fixture", model="fixture-model", usage={"total_tokens": 3})
        callbacks = []
        ctx = SimpleNamespace(llm=Llm(), register_tool=lambda **kw: None, on_unload=callbacks.append)
        package.register(ctx)
        bridge = importlib.import_module(HANDOFF)
        self.assertIs(bridge, importlib.import_module(package.__name__ + ".summary_bridge"))
        result = bridge.summarize_text("Article body", "https://example.org/article")
        self.assertEqual(result, {"text": "Fixture summary", "provider": "fixture", "model": "fixture-model", "usage": {"total_tokens": 3}})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["timeout"], 60)
        self.assertEqual(calls[0]["max_tokens"], 800)
        self.assertFalse(set(calls[0]) & {"provider", "model", "profile", "agent_id", "tools"})
        self.assertIn("Article body", calls[0]["messages"][-1]["content"])
        self.assertEqual(len(callbacks), 1)
        callbacks[0]()
        with self.assertRaises(bridge.CapabilityUnavailable):
            bridge.summarize_text("Article body", "https://example.org/article")


@unittest.skipUnless(os.environ.get("HERMES_BRIDGE_HOST_TEST") == "1", "requires installed Hermes runtime")
class HostBridgeTests(unittest.TestCase):
    def test_real_host_dashboard_route_uses_registered_context(self):
        import json
        import shutil
        import hermes_yaml as yaml
        from hermes_cli.plugins import PluginManager, PluginManifest
        from hermes_constants import get_hermes_home
        active_home = str(get_hermes_home())
        from agent.plugin_llm import PluginLlm, PluginLlmCompleteResult, PluginLlmUsage
        live = os.environ.get("HERMES_BRIDGE_LIVE") == "1"
        with tempfile.TemporaryDirectory(prefix="bridge-", dir=os.environ.get("TMPDIR")) as tmp:
            home = Path(tmp)
            plugin = home / "plugins" / "hermes-blogwatcher"
            plugin.mkdir(parents=True)
            for name in ("__init__.py", "blogwatcher_core.py", "plugin.yaml", "summary_bridge.py"):
                if (ROOT / name).exists():
                    shutil.copyfile(ROOT / name, plugin / name)
            dashboard = plugin / "dashboard"
            dashboard.mkdir()
            # This route is an isolated probe, NOT an edit to the production API.
            (dashboard / "probe.py").write_text('''import os
from fastapi import APIRouter
import blogwatcher_dashboard_summary_bridge as bridge
router = APIRouter()
@router.post("/probe")
def probe():
    return {"pid": os.getpid(), "bridge_module": bridge.__name__, "result": bridge.summarize_text("The observatory opened on Monday. It studies stars.", "https://example.org/probe")}
''')
            config = {"plugins": {"enabled": ["hermes-blogwatcher"], "isolation": "host"}}
            if live:
                from hermes_cli.config import load_config
                active = load_config().get("model", {})
                config["model"] = {key: active[key] for key in ("provider", "model") if key in active}
            (home / "config.yaml").write_text(yaml.safe_dump(config))
            fixture_calls = []
            def fixture_complete(facade, **kwargs):
                fixture_calls.append((facade._plugin_id, kwargs, os.getpid()))
                return PluginLlmCompleteResult(text="Host fixture summary", provider="fixture", model="fixture-model", agent_id="", usage=PluginLlmUsage(total_tokens=3), audit={})
            from contextlib import nullcontext
            inference = nullcontext() if live else patch.object(PluginLlm, "complete", fixture_complete)
            # Live auth remains in the existing Hermes-owned profile. The plugin
            # source and HTTP probe remain temporary; nothing is installed there.
            target_home = active_home if live else str(home)
            with patch.dict(os.environ, {"HERMES_HOME": target_home}), inference:
                manager = PluginManager(scope_key=target_home)
                try:
                    if live:
                        from hermes_cli.plugins import PluginContext
                        manifest = PluginManifest(name="hermes-blogwatcher", version="0.1.0", path=str(plugin), source="user")
                        host = manager._plugin_host()
                        host.load(manifest, PluginContext(manifest, manager), module_name=manager._directory_module_name(manifest), entrypoint=False)
                    else:
                        manager.discover_and_load()
                        loaded = manager._plugins["hermes-blogwatcher"]
                        self.assertIsNone(loaded.error)
                        host = manager._plugin_host()
                    response = host.asgi_request("hermes-blogwatcher", str(dashboard), "probe.py", "POST", "/probe", "", [], b"")
                    self.assertEqual(response["status"], 200)
                    payload = json.loads(response["body"])
                    self.assertNotEqual(payload["pid"], os.getpid())
                    self.assertEqual(payload["pid"], host.pid)
                    self.assertTrue(payload["bridge_module"].startswith("hermes_plugins.hermes_blogwatcher"))
                    self.assertTrue(payload["bridge_module"].endswith(".summary_bridge"))
                    self.assertTrue(payload["result"]["text"].strip())
                    self.assertTrue(payload["result"]["provider"])
                    if not live:
                        self.assertEqual(len(fixture_calls), 1)
                        self.assertEqual(fixture_calls[0][0], "hermes-blogwatcher")
                        self.assertEqual(fixture_calls[0][2], os.getpid())
                    else:
                        print("LIVE_BRIDGE_RESULT " + json.dumps(payload))
                finally:
                    manager.unload()
                    host = manager._plugin_host()
                    process = host._proc
                    host.shutdown()
                    # The runtime's shutdown leaves its stderr pipe open.
                    if process is not None:
                        for stream in (process.stdin, process.stdout, process.stderr):
                            if stream is not None and not stream.closed:
                                stream.close()


if __name__ == "__main__":
    unittest.main()
