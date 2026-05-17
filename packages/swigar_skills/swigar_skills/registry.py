from swigar_skills.diagnosis import DiagnosisSkill
from swigar_skills.plan import PlanSkill
from swigar_skills.quest_mapping import QuestMappingSkill
from swigar_skills.report import ReportSkill
from swigar_skills.paper_plan import PaperPlanSkill
from swigar_skills.question_retrieve import QuestionRetrieveSkill
from swigar_skills.question_generate import QuestionGenerateSkill
from swigar_skills.question_validate import QuestionValidateSkill
from swigar_skills.next_paper_adapt import NextPaperAdaptSkill


class SkillRegistry:
    def __init__(self, tools):
        self.diagnosis = DiagnosisSkill(tools)
        self.plan = PlanSkill(tools)
        self.quest_mapping = QuestMappingSkill(tools)
        self.report = ReportSkill()
        self.paper_plan = PaperPlanSkill(tools)
        self.question_retrieve = QuestionRetrieveSkill(tools)
        self.question_generate = QuestionGenerateSkill(tools)
        self.question_validate = QuestionValidateSkill(tools)
        self.next_paper_adapt = NextPaperAdaptSkill()
