import unittest

from codex_control_tower.ui import select_bridge_info


class WindowIdentityTests(unittest.TestCase):
    def test_live_bridge_overrides_stale_same_name_workspace_path(self):
        live = {"pid": 20, "at": 200, "name": "catkin_ws", "paths": ["/home/uav/桌面/catkin_ws"], "bridgeVersion": "0.2.0", "focused": False}
        selected = select_bridge_info("/root/catkin_ws", "catkin_ws", [live])
        self.assertEqual(selected["pid"], 20)
        self.assertEqual(selected["paths"][0], "/home/uav/桌面/catkin_ws")

    def test_exact_path_wins_over_same_name_fallback(self):
        rows = [
            {"pid": 10, "at": 100, "name": "catkin_ws", "paths": ["/root/catkin_ws"], "bridgeVersion": "0.2.0", "focused": False},
            {"pid": 20, "at": 200, "name": "catkin_ws", "paths": ["/home/uav/桌面/catkin_ws"], "bridgeVersion": "0.2.0", "focused": True},
        ]
        self.assertEqual(select_bridge_info("/root/catkin_ws", "catkin_ws", rows)["pid"], 10)

    def test_ambiguous_unfocused_name_is_not_guessed(self):
        rows = [
            {"pid": 10, "at": 100, "name": "catkin_ws", "paths": ["/root/catkin_ws"], "bridgeVersion": "0.2.0", "focused": False},
            {"pid": 20, "at": 200, "name": "catkin_ws", "paths": ["/home/uav/桌面/catkin_ws"], "bridgeVersion": "0.2.0", "focused": False},
        ]
        self.assertEqual(select_bridge_info("/unknown/catkin_ws", "catkin_ws", rows), {})


if __name__ == "__main__":
    unittest.main()
