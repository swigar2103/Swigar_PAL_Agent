"""Tool registry."""

from __future__ import annotations

from swigar_tools.evaluator import EvaluatorTool
from swigar_tools.llm import DashScopeLLMClient, get_llm_client
from swigar_tools.question_bank import QuestionBankTool, create_question_bank
from swigar_tools.safety import SafetyFilterTool


class ToolRegistry:
    def __init__(self, llm: DashScopeLLMClient | None = None, question_bank: QuestionBankTool | None = None):
        self.question_bank = question_bank or create_question_bank()
        self.evaluator = EvaluatorTool()
        self.safety = SafetyFilterTool()
        self.llm = llm or get_llm_client()
