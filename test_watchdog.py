"""The watchdog task: its settings, when it's added or removed, and the
"closed on purpose" marker."""
import os
import tempfile
import time
import unittest
from unittest import mock

import startup_utils as S


class WatchdogXml(unittest.TestCase):
    def test_never_stops_the_monitor(self):
        root = os.path.dirname(os.path.abspath(__file__))
        xml = S.watchdog_xml(root)
        if xml is None:
            self.skipTest("no pythonw here")
        for setting in ("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>",
                        "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>",
                        "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>",
                        "<Priority>4</Priority>",
                        "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>",
                        f"<Interval>PT{S.WATCHDOG_MINUTES}M</Interval>",
                        "--headless --watchdog"):
            self.assertIn(setting, xml)

    def test_paths_are_escaped(self):
        with mock.patch.object(S, "build_headless_command",
                               return_value=("C:\\A&B\\pythonw.exe", "C:\\A&B\\TCGLiveMonitor.py", "x")):
            xml = S.watchdog_xml("C:\\A&B")
        self.assertIn("A&amp;B", xml)
        self.assertNotIn("A&B", xml)


class EnsureWatchdog(unittest.TestCase):
    def run_ensure(self, registered, ours, current_action):
        calls = []
        with mock.patch.object(S, "build_headless_command", return_value=("py", "mon.py", '"py" "mon.py" --headless')), \
                mock.patch.object(S, "is_registry_registered", return_value=registered), \
                mock.patch.object(S, "startup_is_ours", return_value=ours), \
                mock.patch.object(S, "_watchdog_action", return_value=current_action), \
                mock.patch.object(S, "add_watchdog", side_effect=lambda r: calls.append("add") or (True, None)), \
                mock.patch.object(S, "remove_watchdog", side_effect=lambda: calls.append("remove") or True), \
                mock.patch.object(S.os, "name", "nt"):
            return S.ensure_watchdog("root"), calls

    def test_auto_start_off_removes_it(self):
        self.assertEqual(self.run_ensure(False, False, ""), ("removed", ["remove"]))

    def test_another_copys_startup_is_left_alone(self):
        self.assertEqual(self.run_ensure(True, False, ""), ("skipped", []))

    def test_missing_is_added(self):
        self.assertEqual(self.run_ensure(True, True, ""), ("added", ["add"]))

    def test_pointing_elsewhere_is_replaced(self):
        self.assertEqual(self.run_ensure(True, True, 'other "x.py" --headless --watchdog'), ("added", ["add"]))

    def test_up_to_date_is_kept(self):
        self.assertEqual(self.run_ensure(True, True, 'py  "MON.py" --headless --watchdog'), ("ok", []))


class TaskManagerStartupSwitch(unittest.TestCase):
    def switched_off(self, data):
        key = mock.MagicMock()
        key.__enter__.return_value = key
        with mock.patch.object(S.winreg, "OpenKey", return_value=key), \
                mock.patch.object(S.winreg, "QueryValueEx",
                                  side_effect=FileNotFoundError if data is None else (lambda k, v: (data, 3))):
            return S.startup_switched_off()

    def test_switch_states(self):
        self.assertFalse(self.switched_off(None))                    # never touched: on
        self.assertFalse(self.switched_off(b"\x02" + b"\x00" * 11))  # on
        self.assertTrue(self.switched_off(b"\x03" + b"\x00" * 11))   # off in Task Manager
        self.assertTrue(self.switched_off(b"\x07" + b"\x00" * 11))   # off (another flag set)

    def test_switched_off_removes_the_watchdog(self):
        with mock.patch.object(S, "build_headless_command", return_value=("py", "mon.py", "x")), \
                mock.patch.object(S, "is_registry_registered", return_value=True), \
                mock.patch.object(S, "startup_switched_off", return_value=True), \
                mock.patch.object(S, "remove_watchdog", return_value=True), \
                mock.patch.object(S.os, "name", "nt"):
            self.assertEqual(S.ensure_watchdog("root"), "removed")


class StoppedMarker(unittest.TestCase):
    def test_closed_since_sign_in(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertFalse(S.stopped_on_purpose(root))
            S.mark_stopped(root)
            with mock.patch("psutil.boot_time", return_value=time.time() - 60):
                self.assertTrue(S.stopped_on_purpose(root))
            with mock.patch("psutil.boot_time", return_value=time.time() + 60):   # restarted since
                self.assertFalse(S.stopped_on_purpose(root))
            S.clear_stopped(root)
            self.assertFalse(S.stopped_on_purpose(root))


class LastRunReport(unittest.TestCase):
    def setUp(self):
        import TCGLiveMonitor
        self.report = TCGLiveMonitor.last_run_report

    def test_normal_exit_or_first_run_says_nothing(self):
        self.assertIsNone(self.report("", False, 1000))
        self.assertIsNone(self.report("exited 42 900", False, 1000))
        self.assertIsNone(self.report("garbage", False, 1000))

    def test_killed_from_outside(self):
        line = self.report("alive 42 400", False, 1000)
        self.assertIn("ended from outside", line)
        self.assertIn("pid 42", line)
        self.assertIn("about 10 min", line)
        self.assertNotIn("Down for", self.report("alive 42 990", False, 1000))

    def test_task_manager_kill_stays_closed(self):
        import TCGLiveMonitor as T
        with mock.patch.object(T, "_pid_is_monitor", return_value=False):
            self.assertTrue(T.closed_from_task_manager("alive 42 400 1"))
            self.assertFalse(T.closed_from_task_manager("alive 42 400 0"))   # another program: restored
            self.assertFalse(T.closed_from_task_manager("alive 42 400"))     # older heartbeat format
            self.assertFalse(T.closed_from_task_manager("exited 42 400 1"))  # normal exit
        with mock.patch.object(T, "_pid_is_monitor", return_value=True):
            self.assertFalse(T.closed_from_task_manager("alive 42 400 1"))   # still running
        self.assertIn("from Task Manager", self.report("alive 42 400 1", False, 1000))

    def test_closed_from_the_dashboard(self):
        self.assertIn("from the dashboard", self.report("alive 42 400", False, 1000, closed_by_user=True))

    def test_windows_restarted(self):
        self.assertIn("Windows restarted", self.report("alive 42 400", False, 1000, booted_at=500))
        self.assertIn("from outside", self.report("alive 42 600", False, 1000, booted_at=500))

    def test_crashed(self):
        self.assertIn("crashed", self.report("alive 42 400", True, 1000))


if __name__ == "__main__":
    import sys

    class Lines(unittest.TextTestResult):
        def addSuccess(self, test):
            super().addSuccess(test)
            print("PASS", test.id().split(".", 1)[1])

        def addFailure(self, test, err):
            super().addFailure(test, err)
            print("FAIL", test.id().split(".", 1)[1])

        def addError(self, test, err):
            super().addError(test, err)
            print("FAIL", test.id().split(".", 1)[1])

        def addSkip(self, test, reason):
            super().addSkip(test, reason)
            print("SKIP", test.id().split(".", 1)[1])

    result = unittest.TextTestRunner(resultclass=Lines, verbosity=0).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    sys.exit(0 if result.wasSuccessful() else 1)
