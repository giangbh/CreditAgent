from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from credit_agent_poc.llm_synthesizer import DeepSeekCreditSynthesizer
from credit_agent_poc.orchestrator import CreditOrchestrator


class TestDeepSeekCreditSynthesizer(unittest.TestCase):
    def setUp(self):
        self.orchestrator = CreditOrchestrator()
        self.result = self.orchestrator.run("escalate_policy_exception")
        self.state = self.result.state

    def test_synthesizer_initialization(self):
        synth = DeepSeekCreditSynthesizer(api_key="test-key", model="deepseek-chat")
        self.assertEqual(synth.api_key, "test-key")
        self.assertEqual(synth.model, "deepseek-chat")
        self.assertTrue(synth.is_configured())

    def test_prompt_generation_structure(self):
        synth = DeepSeekCreditSynthesizer()
        sys_prompt, user_prompt = synth.build_prompt(self.state)
        self.assertIn("Senior Credit Underwriter", sys_prompt)
        self.assertIn("TỜ TRÌNH PHÂN TÍCH TÍN DỤNG CHUYÊN SÂU", sys_prompt)
        self.assertIn("CASE-ESCALATE_POLICY_EXCEPTION", user_prompt)
        self.assertIn("RULE-TENOR-003", user_prompt)

    def test_deterministic_fallback_generation(self):
        synth = DeepSeekCreditSynthesizer(api_key="")  # Unconfigured
        self.assertFalse(synth.is_configured())
        memo = synth.generate_credit_memo(self.state)

        self.assertIn("TỜ TRÌNH PHÂN TÍCH TÍN DỤNG CHUYÊN SÂU", memo)
        self.assertIn("1. TỔNG QUAN KHÁCH HÀNG", memo)
        self.assertIn("2. ĐÁNH GIÁ NĂNG LỰC TÀI CHÍNH", memo)
        self.assertIn("3. PHÂN TÍCH LIÊM CHÍNH GIAO DỊCH", memo)
        self.assertIn("4. TÓM LƯỢC TRANH BIỆN ĐỐI KHÁNG", memo)
        self.assertIn("5. ĐÁNH GIÁ HỘI ĐỒNG RỦI RO", memo)
        self.assertIn("6. Ý KIẾN TƯ VẤN ĐỒNG PHÊ DUYỆT", memo)

        html_memo = synth.generate_credit_memo_html(self.state)
        self.assertIn("<!doctype html>", html_memo)
        self.assertIn("DEEPSEEK LLM SYNTHESIS", html_memo)

    @patch("urllib.request.urlopen")
    def test_mocked_deepseek_api_call(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"choices":[{"message":{"content":"# AI UNDERWRITING MEMO\\n\\nAnalyzed successfully."}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        synth = DeepSeekCreditSynthesizer(api_key="sk-valid-key")
        self.assertTrue(synth.is_configured())
        memo = synth.generate_credit_memo(self.state)

        self.assertEqual(memo, "# AI UNDERWRITING MEMO\n\nAnalyzed successfully.")
        self.assertTrue(mock_urlopen.called)


if __name__ == "__main__":
    unittest.main()
