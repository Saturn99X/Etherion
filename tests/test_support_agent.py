import unittest
from src.agents.Support.support_response_drafter_agent import create_support_response_drafter_agent
from src.utils.llm_loader import get_gemini_llm

class TestSupportResponseDrafterAgent(unittest.TestCase):
    def test_create_support_response_drafter_agent(self):
        # Test that the agent can be created
        llm = get_gemini_llm(model_tier='flash')
        agent = create_support_response_drafter_agent(llm)
        self.assertIsNotNone(agent)

if __name__ == '__main__':
    unittest.main()