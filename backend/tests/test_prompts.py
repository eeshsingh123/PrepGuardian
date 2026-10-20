import unittest

from app.constants import InterviewerConstants
from app.interview.tracks import (
    ALLOWED_DURATIONS_MINUTES,
    TRACKS,
    InterviewTrack,
    InterviewType,
    Phase,
    get_track,
)
from app.prompts import (
    AGENT_DESCRIPTION,
    CONFIDENCE_AGENT_PROMPT,
    MARKET_GAP_AGENT_PROMPT,
    RADAR_AGENT_PROMPT,
    REPORT_COMPILER_PROMPT,
    build_clock_cue,
    build_live_instruction,
)
from app.schemas.live import CandidateContext


CANDIDATE = CandidateContext(
    name="Eesh Singh",
    experience="8 years",
    target_company="Google",
    target_level="Senior",
    preferences="Prefers concrete examples and clear trade-offs",
)


class LiveInstructionTests(unittest.TestCase):
    def test_word_limit_holds_for_every_track_and_duration(self):
        for track in TRACKS.values():
            for duration in ALLOWED_DURATIONS_MINUTES:
                text = build_live_instruction(track, CANDIDATE, duration)
                self.assertLessEqual(len(text.split()), 1200, (track.type, duration))

    def test_every_phase_title_appears(self):
        for track in TRACKS.values():
            text = build_live_instruction(track, CANDIDATE, 45)
            for phase in track.phases:
                self.assertIn(phase.title, text)

    def test_phase_minutes_are_computed_from_share_and_duration(self):
        for track in TRACKS.values():
            for duration in ALLOWED_DURATIONS_MINUTES:
                text = build_live_instruction(track, CANDIDATE, duration)
                for phase in track.phases:
                    expected = f"{phase.title} (~{max(1, round(phase.share * duration))} min)"
                    self.assertIn(expected, text)

    def test_flow_follows_track_data_without_editing_prompts(self):
        custom_track = InterviewTrack(
            type=InterviewType.LLD,
            title="Custom Track",
            problems="a custom problem",
            looking_for="a custom outcome",
            phases=(
                Phase(
                    "requirements",
                    "Discovery",
                    0.5,
                    "Find the core problem.",
                    probe="Ask for a concrete example.",
                ),
                Phase("wrap_up", "Close", 0.5, "Close cleanly."),
            ),
        )

        text = build_live_instruction(custom_track, CANDIDATE, 45)

        self.assertIn("Custom Track", text)
        self.assertIn("a custom problem", text)
        self.assertIn("a custom outcome", text)
        self.assertIn("Discovery", text)
        self.assertIn("Ask for a concrete example.", text)
        self.assertIn("Close", text)

    def test_problem_and_probe_data_come_from_the_track(self):
        for track in TRACKS.values():
            text = build_live_instruction(track, CANDIDATE, 45)
            self.assertIn(track.problems, text)
            self.assertIn(track.looking_for, text)
            for phase in track.phases:
                if phase.probe:
                    self.assertIn(phase.probe, text)

    def test_no_template_placeholders_remain(self):
        for track in TRACKS.values():
            text = build_live_instruction(track, CANDIDATE, 60)
            self.assertNotIn("{", text)
            self.assertNotIn("}", text)

    def test_candidate_profile_is_inserted(self):
        text = build_live_instruction(get_track(InterviewType.LLD), CANDIDATE, 45)

        for value in CANDIDATE.model_dump().values():
            self.assertIn(value, text)
        self.assertIn("Candidate background:", text)
        self.assertIn("greet the candidate by name", text)

    def test_unknown_candidate_renders_no_placeholder_text(self):
        text = build_live_instruction(get_track(InterviewType.LLD), CandidateContext(), 30)
        first_line = text.splitlines()[0]

        self.assertNotIn("Not specified", text)
        self.assertNotIn("not specified", text.lower())
        self.assertNotIn("Candidate background:", text)
        self.assertNotIn("greet the candidate by name", text)
        self.assertIn("greet the candidate,", text)
        self.assertEqual(
            first_line,
            f"You are {InterviewerConstants.NAME}, a senior software engineer running a live "
            "Low-Level Design interview.",
        )

    def test_partial_profile_renders_only_known_fields(self):
        candidate = CandidateContext(experience="8 years")
        text = build_live_instruction(get_track(InterviewType.LLD), candidate, 30)

        self.assertIn("Experience: 8 years", text)
        self.assertNotIn("Not specified", text)
        self.assertNotIn("greet the candidate by name", text)
        self.assertNotIn("interview with", text.splitlines()[0])

    def test_blank_profile_values_are_treated_as_unknown(self):
        candidate = CandidateContext(name="  ", experience="")
        text = build_live_instruction(get_track(InterviewType.LLD), candidate, 30)

        self.assertNotIn("Candidate background:", text)
        self.assertNotIn("greet the candidate by name", text)
        self.assertTrue(text.splitlines()[0].endswith("interview."))

    def test_required_tools_are_named(self):
        text = build_live_instruction(get_track(InterviewType.LLD), CANDIDATE, 45)

        self.assertIn("get_interview_status()", text)
        self.assertIn("save_interview_note(note)", text)

    def test_agent_description_uses_the_interviewer_name(self):
        self.assertEqual(
            AGENT_DESCRIPTION,
            f"{InterviewerConstants.NAME}, a senior engineer running a live mock interview.",
        )


class ClockCueTests(unittest.TestCase):
    def setUp(self):
        self.track = get_track(InterviewType.LLD)
        self.window = self.track.phase_at(0, 45 * 60)

    def test_cue_names_phase_minutes_and_next_phase(self):
        cue = build_clock_cue(30, self.window, self.track)

        self.assertIn(self.window.phase.title, cue)
        self.assertIn("30 minutes", cue)
        self.assertIn("Entities & Relationships", cue)

    def test_cue_wraps_up_in_last_two_minutes(self):
        cue = build_clock_cue(2, self.window, self.track)
        lowered = cue.lower()

        self.assertIn(self.window.phase.title, cue)
        self.assertIn("2 minutes", cue)
        self.assertIn("impression", lowered)
        self.assertIn("questions", lowered)
        self.assertIn("goodbye", lowered)


class InsightPromptTests(unittest.TestCase):
    def test_insight_prompts_still_importable_from_package(self):
        self.assertIn("{raw_transcript}", CONFIDENCE_AGENT_PROMPT)
        self.assertIn("{raw_transcript}", RADAR_AGENT_PROMPT)
        self.assertIn("{candidate_profile}", MARKET_GAP_AGENT_PROMPT)
        self.assertIn("{market_gap_data}", REPORT_COMPILER_PROMPT)
