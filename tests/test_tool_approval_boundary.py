"""Regression checks for model-requested tools; no real providers are called."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import agent_runtime


class ToolApprovalBoundaryTests(unittest.TestCase):
    def test_gate_denial_prevents_dispatch(self):
        gate = Mock()
        gate.check.return_value = {"allowed": False}
        with patch(
            "orchestration.service", return_value=SimpleNamespace(gate=gate)
        ), patch.object(agent_runtime, "_execute_existing") as dispatch:
            with self.assertRaises(PermissionError):
                agent_runtime.execute(object(), "tasks_read", {}, "Read my tasks")
        dispatch.assert_not_called()

    def test_unknown_tool_is_classified_as_blocked(self):
        gate = Mock()
        gate.check.return_value = {"allowed": False}
        with patch("orchestration.service", return_value=SimpleNamespace(gate=gate)):
            with self.assertRaises(PermissionError):
                agent_runtime.execute(object(), "arbitrary_action", {}, "Do it")
        self.assertEqual(gate.check.call_args.args[2], "BLOCKED")

    def test_api_request_creates_pending_approval_without_execution(self):
        automation = Mock()
        automation.public_tools.return_value = [{"id": "example-api", "enabled": True}]
        automation.create_approval.return_value = "approval-example"
        app = SimpleNamespace(automation=automation)
        gate = Mock()
        gate.check.return_value = {"allowed": True}
        with patch("orchestration.service", return_value=SimpleNamespace(gate=gate)):
            result = agent_runtime.execute(
                app,
                "request_api_call",
                {"tool_id": "example-api", "instructions": "Create a draft"},
                "Prepare this request",
            )
        self.assertEqual(result["status"], "pending_user_approval")
        self.assertFalse(result["executed"])
        automation.create_approval.assert_called_once()
        automation.run_tool.assert_not_called()

    def test_disabled_api_cannot_create_an_approval(self):
        automation = Mock()
        automation.public_tools.return_value = [{"id": "example-api", "enabled": False}]
        with self.assertRaises(ValueError):
            agent_runtime._execute_existing(
                SimpleNamespace(automation=automation),
                "request_api_call",
                {"tool_id": "example-api", "instructions": "Create a draft"},
                "Prepare it",
            )
        automation.create_approval.assert_not_called()
        automation.run_tool.assert_not_called()

    def test_mcp_request_prepares_an_approval_without_calling_the_tool(self):
        with patch.object(
            agent_runtime.mcp_bridge, "prepare", return_value={"id": "approval-example"}
        ) as prepare, patch.object(agent_runtime.mcp_bridge, "request") as request:
            result = agent_runtime._execute_existing(
                object(),
                "request_mcp_call",
                {"server_id": "example-server", "tool": "draft", "arguments": {}},
                "Prepare a draft",
            )
        prepare.assert_called_once()
        request.assert_not_called()
        self.assertFalse(result["executed"])
        self.assertEqual(result["status"], "pending_user_approval")


if __name__ == "__main__":
    unittest.main()
