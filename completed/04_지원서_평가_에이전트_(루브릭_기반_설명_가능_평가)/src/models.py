from datetime import datetime
from pydantic import BaseModel, Field


class RubricBonusRule(BaseModel):
    condition: str
    bonus: float


class RubricItem(BaseModel):
    name: str
    max_score: float
    weight: float = 1.0
    scoring_anchors: dict[str, str]
    evidence_guide: str | None = None
    academic_basis: str | None = None
    bonus_rules: list[RubricBonusRule] | None = None


class RubricSection(BaseModel):
    name: str
    scoring_type: str = "standard"
    total_subscore: float | None = None
    items: list[RubricItem]


class Rubric(BaseModel):
    name: str
    description: str
    total_score: float
    sections: list[RubricSection]


class EvidenceExtract(BaseModel):
    item_name: str
    extracted_text: str
    relevance_note: str


class ItemScore(BaseModel):
    item_name: str
    section_name: str
    max_score: float
    score: float
    anchor_range: str = ""
    scoring_rationale: str = ""
    deduction_rationale: str = ""
    academic_justification: str = ""
    evidence_quotes: list[str] = Field(default_factory=list)


class BiasCheck(BaseModel):
    blind_mode: bool = False
    flags: list[str] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    applicant_name: str
    file_path: str
    rubric_name: str
    total_score: float
    max_total: float
    item_scores: list[ItemScore]
    strengths_top3: list[str] = Field(default_factory=list)
    improvements_top3: list[str] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(default_factory=list)
    bias_check: BiasCheck = Field(default_factory=BiasCheck)
    evaluated_at: datetime = Field(default_factory=datetime.now)


class CalibrationEntry(BaseModel):
    item_name: str
    human_score: float
    agent_score: float
    deviation: float
    adjustment_prompt: str = ""


class CalibrationProfile(BaseModel):
    rubric_name: str
    entries: list[CalibrationEntry]
    overall_agreement_rate: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)


class ConsistencyResult(BaseModel):
    item_name: str
    scores: list[float]
    mean: float
    std_dev: float
    is_stable: bool


class FeedbackReport(BaseModel):
    applicant_name: str
    strengths: list[str]
    improvement_suggestions: list[str]
    generated_at: datetime = Field(default_factory=datetime.now)


class BatchStatistics(BaseModel):
    rubric_name: str
    total_applicants: int
    score_distribution: dict = Field(default_factory=dict)
    item_averages: dict[str, float] = Field(default_factory=dict)
    item_std_devs: dict[str, float] = Field(default_factory=dict)
    cutoff_score: float | None = None
    passed_applicants: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)
