"""Run with: python -m unittest   (from this folder)"""

import contextlib
import datetime as dt
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import send

MESSAGES = send.load_messages(Path(__file__).with_name("messages.txt"))
BOISE = ZoneInfo("America/Boise")
SEVEN_THIRTY = dt.time(7, 30)


class PickingMessages(unittest.TestCase):
    def test_no_repeats_until_the_whole_pool_is_used(self):
        pool = MESSAGES["general"]
        for start in (0, len(pool), 5 * len(pool)):
            picks = [send.rotate(pool, i, "general") for i in range(start, start + len(pool))]
            self.assertEqual(sorted(picks), sorted(pool))

    def test_never_the_same_message_two_days_running(self):
        for section, pool in MESSAGES.items():
            picks = [send.rotate(pool, i, section) for i in range(len(pool) * 30)]
            for yesterday, today in zip(picks, picks[1:]):
                self.assertNotEqual(yesterday, today, f"[{section}] repeated: {today!r}")

    def test_same_day_always_gets_the_same_message(self):
        day = dt.date(2026, 11, 3)
        self.assertEqual(send.pick_message(MESSAGES, day), send.pick_message(MESSAGES, day))

    def test_weekday_sections(self):
        self.assertEqual(send.pick_message(MESSAGES, dt.date(2026, 11, 2))[0], "monday")
        self.assertEqual(send.pick_message(MESSAGES, dt.date(2026, 11, 6))[0], "friday")
        self.assertEqual(send.pick_message(MESSAGES, dt.date(2026, 11, 4))[0], "general")

    def test_birthday_wins(self):
        self.assertEqual(send.pick_message(MESSAGES, dt.date(2026, 6, 12), (6, 12))[0], "birthday")
        self.assertEqual(send.pick_message(MESSAGES, dt.date(2026, 6, 13), (6, 12))[0], "general")

    def test_leap_day_birthday_falls_on_feb_28_in_other_years(self):
        self.assertTrue(send.is_birthday(dt.date(2027, 2, 28), (2, 29)))
        self.assertTrue(send.is_birthday(dt.date(2028, 2, 29), (2, 29)))
        self.assertFalse(send.is_birthday(dt.date(2028, 2, 28), (2, 29)))

    def test_compose(self):
        self.assertEqual(send.compose("Hi {name}.", "Emma"), "Hi Emma.")
        self.assertEqual(send.compose("Hi {name}.", "Emma", "- E"), "Hi Emma.\n- E")


class Publishing(unittest.TestCase):
    def test_upcoming_matches_what_each_day_would_send(self):
        start = dt.date(2026, 12, 30)
        data = send.upcoming(MESSAGES, start, 5, "Emma")
        self.assertEqual(list(data), ["2026-12-30", "2026-12-31", "2027-01-01", "2027-01-02", "2027-01-03"])
        for key, message in data.items():
            template = send.pick_message(MESSAGES, dt.date.fromisoformat(key))[1]
            self.assertEqual(message, send.compose(template, "Emma"))
        self.assertNotIn("{name}", "".join(data.values()))

    def test_publish_writes_json_covering_yesterday_through_two_weeks_out(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"TIMEZONE": "America/Boise"}):
            with contextlib.redirect_stdout(io.StringIO()):
                send.main(["--publish", tmp, "--date", "2026-11-01"])
            data = json.loads(Path(tmp, "upcoming.json").read_text())
        self.assertEqual(min(data), "2026-10-31")
        self.assertEqual(max(data), "2026-11-15")
        self.assertEqual(len(data), 16)

    def test_no_delivery_set_sends_nothing(self):
        env = {"DELIVERY": "", "SCHEDULE": ""}
        with mock.patch.dict(os.environ, env), mock.patch.object(send, "send_email") as email, \
                mock.patch.object(send, "send_sms") as sms, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(send.main([]), 0)
        email.assert_not_called()
        sms.assert_not_called()
        self.assertIn("nothing is sent", out.getvalue())


class Scheduling(unittest.TestCase):
    def test_boise_has_one_slot_for_daylight_time_and_one_for_standard(self):
        self.assertEqual(send.cron_slots(SEVEN_THIRTY, BOISE, 2026), [(13, 30), (14, 30)])

    def test_only_the_matching_slot_sends(self):
        january = dt.datetime(2026, 1, 15, 14, 45, tzinfo=dt.timezone.utc)
        july = dt.datetime(2026, 7, 15, 13, 45, tzinfo=dt.timezone.utc)
        self.assertTrue(send.should_send("30 14 * * *", january, SEVEN_THIRTY, BOISE))
        self.assertFalse(send.should_send("30 13 * * *", january, SEVEN_THIRTY, BOISE))
        self.assertTrue(send.should_send("30 13 * * *", july, SEVEN_THIRTY, BOISE))
        self.assertFalse(send.should_send("30 14 * * *", july, SEVEN_THIRTY, BOISE))

    def test_a_late_start_still_sends_from_the_right_slot(self):
        # GitHub started the 13:30 run nearly two hours late; it should still be the one.
        late = dt.datetime(2026, 7, 15, 15, 20, tzinfo=dt.timezone.utc)
        self.assertTrue(send.should_send("30 13 * * *", late, SEVEN_THIRTY, BOISE))

    def test_cron_that_does_not_match_the_settings_fails_loudly(self):
        now = dt.datetime(2026, 1, 15, 15, 0, tzinfo=dt.timezone.utc)
        with self.assertRaises(SystemExit):
            send.should_send("0 15 * * *", now, SEVEN_THIRTY, BOISE)

    def test_timezones_ahead_of_utc(self):
        # 7:30am in Tokyo is 22:30 UTC the evening before.
        tokyo = ZoneInfo("Asia/Tokyo")
        now = dt.datetime(2026, 3, 1, 22, 30, tzinfo=dt.timezone.utc)
        self.assertTrue(send.should_send("30 22 * * *", now, SEVEN_THIRTY, tokyo))


class MessageFile(unittest.TestCase):
    """Guards for when messages.txt gets edited."""

    CHEESE = re.compile(
        r"sunshine|rise and shine|queen|bestie|slay|blessed|#|!!|you('ve| have) got this|"
        r"carpe|today is a gift|live laugh|xoxo|<3",
        re.IGNORECASE,
    )

    def all_messages(self):
        for section, pool in MESSAGES.items():
            for message in pool:
                yield section, message

    def test_sections_are_known(self):
        known = {"general", "birthday", *send.WEEKDAYS}
        self.assertLessEqual(set(MESSAGES), known)

    def test_no_duplicates(self):
        seen = [m for _, m in self.all_messages()]
        self.assertEqual(len(seen), len(set(seen)))

    def test_fits_in_one_text(self):
        # Plain ASCII keeps a text in the cheap 160-character format; curly quotes or
        # emoji drop it to 70. Leave room for a sign-off.
        for section, message in self.all_messages():
            rendered = send.compose(message, "Emma")
            self.assertTrue(rendered.isascii(), f"[{section}] non-ASCII: {message!r}")
            self.assertLessEqual(len(rendered), 140, f"[{section}] too long: {message!r}")

    def test_not_cheesy(self):
        for section, message in self.all_messages():
            self.assertIsNone(self.CHEESE.search(message), f"[{section}] cheesy: {message!r}")


if __name__ == "__main__":
    unittest.main()
