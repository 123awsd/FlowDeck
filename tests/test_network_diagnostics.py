import unittest

from codex_control_tower.network_diagnostics import _group_leaves, _selector_group, display_node_name


class NetworkDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.proxies = {
            "🤖AI网站": {"type": "Selector", "all": ["AI-A", "AI-B"]},
            "🚀节点选择": {"type": "Selector", "all": ["自动", "DIRECT"]},
            "自动": {"type": "URLTest", "all": ["通用-A", "通用-B"]},
            "AI-A": {"type": "Vmess", "alive": True},
            "AI-B": {"type": "Vmess", "alive": False},
            "通用-A": {"type": "Vmess", "alive": True},
            "通用-B": {"type": "Vmess", "alive": True},
            "DIRECT": {"type": "Direct", "alive": True},
        }

    def test_selects_separate_ai_and_general_groups(self):
        self.assertEqual(_selector_group(self.proxies, "Codex")[0], "🤖AI网站")
        self.assertEqual(_selector_group(self.proxies, "GitHub")[0], "🚀节点选择")

    def test_flattens_groups_and_excludes_dead_or_direct(self):
        self.assertEqual(_group_leaves(self.proxies, "🤖AI网站"), ["AI-A"])
        self.assertEqual(_group_leaves(self.proxies, "🚀节点选择"), ["通用-A", "通用-B"])

    def test_node_display_removes_unsupported_symbol_prefix(self):
        self.assertEqual(display_node_name("🇸🇬新加坡02 | 推荐"), "新加坡02 | 推荐")
        self.assertEqual(display_node_name("🤖AI网站"), "AI网站")


if __name__ == "__main__":
    unittest.main()
