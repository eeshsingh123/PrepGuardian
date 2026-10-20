import unittest

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
            phases=(
                Phase("requirements", "Discovery", 0.5, "Find the core problem."),
                Phase("wrap_up", "Close", 0.5, "Close cleanly."),
            ),
        )

        text = build_live_instruction(custom_track, CANDIDATE, 45)

        self.assertIn("Custom Track", text)
        self.assertIn("Discovery", text)
        self.assertIn("Close", text)

    def test_no_template_placeholders_remain(self):
        for track in TRACKS.values():
            text = build_live_instruction(track, CANDIDATE, 60)
            self.assertNotIn("{", text)
            self.assertNotIn("}", text)

    def test_candidate_profile_is_inserted(self):
        text = build_live_instruction(get_track(InterviewType.LLD), CANDIDATE, 45)

        for value in CANDIDATE.model_dump().values():
            self.assertIn(value, text)

    def test_required_tools_are_named(self):
        text = build_live_instruction(get_track(InterviewType.LLD), CANDIDATE, 45)

        self.assertIn("get_interview_status()", text)
        self.assertIn("save_interview_note(note)", text)

    def test_agent_description_names_the_interviewer(self):
        self.assertIn("Maya", AGENT_DESCRIPTION)


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
