import pytest
from unittest.mock import patch
from app.escalation import should_escalate, run_with_escalation
from app.logger import log_request
from app.database import get_connection


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_callers(haiku_response, together_response=None, gpt4o_response=None):
    return {
        "claude-haiku-4-5":                        lambda p: haiku_response,
        "meta-llama/Llama-3.3-70B-Instruct-Turbo": lambda p: together_response or ("Together answer.", 80, 200),
        "gpt-4o":                                  lambda p: gpt4o_response or ("GPT-4o answer.", 100, 300),
    }


# ── Pattern Detection ─────────────────────────────────────────────────────────

class TestShouldEscalate:

    def test_triggers_on_i_dont_know(self):
        assert should_escalate("I don't know the answer to this.") is True

    def test_triggers_on_i_cannot(self):
        assert should_escalate("I cannot provide that information.") is True

    def test_triggers_on_i_am_not_sure(self):
        assert should_escalate("I'm not sure about this topic.") is True

    def test_triggers_on_i_am_unable(self):
        assert should_escalate("I am unable to answer this question.") is True

    def test_triggers_on_beyond_my_knowledge(self):
        assert should_escalate("This is beyond my knowledge.") is True

    def test_no_trigger_on_good_response(self):
        assert should_escalate("Paris is the capital of France.") is False

    def test_no_trigger_on_detailed_response(self):
        assert should_escalate("Here is a detailed architecture diagram...") is False

    def test_case_insensitive(self):
        assert should_escalate("I CANNOT help with this.") is True

    def test_pattern_in_middle_of_response(self):
        assert should_escalate("Great question! I don't know the exact answer though.") is True

    def test_no_false_positive_i_cannot_stress(self):
        assert should_escalate("I cannot stress enough how important this is.") is False

    def test_no_false_positive_i_cannot_emphasize(self):
        assert should_escalate("I cannot emphasize this enough.") is False

    def test_no_false_positive_i_cannot_overstate(self):
        assert should_escalate("I cannot overstate the significance of this finding.") is False

    def test_no_false_positive_i_cant_wait(self):
        assert should_escalate("I can't wait to show you this solution!") is False

    def test_no_false_positive_i_cant_believe(self):
        assert should_escalate("I can't believe how elegant this approach is.") is False

    def test_no_false_positive_i_cant_stress(self):
        assert should_escalate("I can't stress enough how important this is.") is False

    def test_triggers_on_i_cant_answer(self):
        assert should_escalate("I can't answer that question.") is True

    def test_triggers_on_i_cant_provide(self):
        assert should_escalate("I can't provide that information.") is True

    # Knowledge-cutoff / data-access hedges
    def test_triggers_on_dont_have_access(self):
        # exact phrase seen in production (Liechtenstein GDP screenshot)
        assert should_escalate("I don't have access to 2025 GDP data for Liechtenstein.") is True

    def test_triggers_on_knowledge_cutoff(self):
        assert should_escalate("My knowledge cutoff is early 2024, so I can't confirm this.") is True

    def test_triggers_on_training_data(self):
        assert should_escalate("My training data doesn't include events after 2023.") is True

    def test_triggers_on_as_of_my_knowledge(self):
        assert should_escalate("As of my knowledge cutoff, I cannot verify this.") is True

    def test_triggers_on_no_realtime_access(self):
        assert should_escalate("I don't have real-time data to answer this accurately.") is True


# ── Escalation Chain ──────────────────────────────────────────────────────────

class TestEscalationChain:

    def test_simple_escalates_to_medium_on_low_confidence(self):
        callers = make_callers(
            haiku_response=("I don't know the answer.", 50, 10),
            together_response=("Here is a detailed answer.", 80, 200),
        )
        with patch("app.escalation.MODEL_CALLERS", callers):
            result = run_with_escalation("Explain quantum entanglement.", initial_tag="simple")

        assert result["escalated"] is True
        assert result["model_used"] == "meta-llama/Llama-3.3-70B-Instruct-Turbo"
        assert result["difficulty_tag"] == "medium"

    def test_medium_escalates_to_complex_on_low_confidence(self):
        callers = {
            "claude-haiku-4-5":                        lambda p: ("Haiku answer.", 50, 10),
            "meta-llama/Llama-3.3-70B-Instruct-Turbo": lambda p: ("I'm not sure about this.", 80, 20),
            "gpt-4o":                                  lambda p: ("Here is a comprehensive answer.", 100, 400),
        }
        with patch("app.escalation.MODEL_CALLERS", callers):
            result = run_with_escalation("Design a distributed system.", initial_tag="medium")

        assert result["escalated"] is True
        assert result["model_used"] == "gpt-4o"

    def test_complex_does_not_escalate_even_on_weak_response(self):
        callers = make_callers(
            haiku_response=("Haiku answer.", 50, 10),
            gpt4o_response=("I'm not sure about this.", 100, 20),
        )
        with patch("app.escalation.MODEL_CALLERS", callers):
            result = run_with_escalation("Some complex prompt.", initial_tag="complex")

        # Top tier — returns as-is, no loop
        assert result["escalated"] is False
        assert result["model_used"] == "gpt-4o"

    def test_good_response_does_not_escalate(self):
        callers = make_callers(
            haiku_response=("Paris is the capital of France.", 20, 10),
        )
        with patch("app.escalation.MODEL_CALLERS", callers):
            result = run_with_escalation("What is the capital of France?", initial_tag="simple")

        assert result["escalated"] is False
        assert result["model_used"] == "claude-haiku-4-5"

    def test_escalated_flag_false_on_confident_response(self):
        callers = make_callers(
            haiku_response=("Clear confident answer here.", 30, 15),
        )
        with patch("app.escalation.MODEL_CALLERS", callers):
            result = run_with_escalation("Simple question.", initial_tag="simple")

        assert result["escalated"] is False


# ── DB Verification ───────────────────────────────────────────────────────────

@pytest.mark.integration
class TestEscalationDBLogging:

    def test_escalated_flag_writes_true_to_db(self):
        callers = make_callers(
            haiku_response=("I don't know.", 20, 5),
            together_response=("Here is a full answer.", 80, 200),
        )
        with patch("app.escalation.MODEL_CALLERS", callers):
            result = run_with_escalation("Test escalation DB write.", initial_tag="simple")

        assert result["escalated"] is True

        log_request(
            raw_prompt="Test escalation DB write.",
            difficulty_tag=result["difficulty_tag"],
            model_used=result["model_used"],
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            cost_usd=result["cost_usd"],
            latency_ms=999,
            escalated=result["escalated"]
        )

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT escalated FROM requests ORDER BY created_at DESC LIMIT 1"
                )
                row = cur.fetchone()

        assert row[0] is True

    def test_non_escalated_flag_writes_false_to_db(self):
        callers = make_callers(
            haiku_response=("Confident answer.", 20, 10),
        )
        with patch("app.escalation.MODEL_CALLERS", callers):
            result = run_with_escalation("Simple question.", initial_tag="simple")

        assert result["escalated"] is False

        log_request(
            raw_prompt="Simple non-escalated test.",
            difficulty_tag=result["difficulty_tag"],
            model_used=result["model_used"],
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            cost_usd=result["cost_usd"],
            latency_ms=100,
            escalated=result["escalated"]
        )

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT escalated FROM requests ORDER BY created_at DESC LIMIT 1"
                )
                row = cur.fetchone()

        assert row[0] is False