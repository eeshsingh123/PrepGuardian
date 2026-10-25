import unittest

from pydantic import ValidationError

from app.interview.tracks import TRACKS, InterviewType, get_track
from app.schemas import LiveSessionConfig


class InterviewTrackTests(unittest.TestCase):
    def test_every_interview_type_has_a_track(self):
        self.assertEqual(set(TRACKS), set(InterviewType))

    def test_schedule_covers_full_duration_without_gaps(self):
        for track in TRACKS.values():
            windows = track.schedule(45 * 60)
            self.assertEqual(windows[0].start_seconds, 0)
            self.assertEqual(windows[-1].end_seconds, 45 * 60)
            for previous, current in zip(windows, windows[1:]):
                self.assertEqual(previous.end_seconds, current.start_seconds)

    def test_both_tracks_cover_concurrency(self):
        for track in TRACKS.values():
            self.assertIn("concurrency", [p.key for p in track.phases])

    def test_phase_at_returns_current_and_clamps_past_end(self):
        track = get_track(InterviewType.LLD)
        self.assertEqual(track.phase_at(0, 1800).phase.key, "requirements")
        self.assertEqual(track.phase_at(99999, 1800).phase.key, "wrap_up")


class LiveSessionConfigTests(unittest.TestCase):
    def test_defaults(self):
        config = LiveSessionConfig()
        self.assertEqual(config.interview_type, InterviewType.LLD)
        self.assertEqual(config.duration_seconds, config.duration_minutes * 60)

    def test_rejects_unknown_duration_and_type(self):
        with self.assertRaises(ValidationError):
            LiveSessionConfig(duration_minutes=17)
        with self.assertRaises(ValidationError):
            LiveSessionConfig(interview_type="behavioral")
