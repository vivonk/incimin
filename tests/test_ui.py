import unittest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# graph.py calls build_llm() at import; allow UI unit tests without a real key.
if not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = "test-placeholder"

class TestUI(unittest.TestCase):
    @patch('src.ui.app.agent_app')
    def test_run_agent_sync(self, mock_agent_app):
        # We need to test the logic of run_agent_sync to ensure no asyncio errors
        from src.ui.app import run_agent_sync
        
        async def mock_astream(*args, **kwargs):
            yield {"agent": {"messages": []}}
        
        mock_agent_app.astream = mock_astream
        
        updates = run_agent_sync("test message", [])
        self.assertEqual(len(updates), 1)
        self.assertIn("agent", updates[0])

if __name__ == '__main__':
    unittest.main()
