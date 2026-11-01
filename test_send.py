"""Run with: python -m unittest   (from this folder)"""

import contextlib
import datetime as dt
import io
import json
import os
import re
import unittest
import urllib.parse
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


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_textbelt(reply):
    """Stand-in for urlopen that records requests and answers with `reply`."""
    calls = []

    def urlopen(request, timeout=None):
        calls.append(request)
        return FakeResponse(json.dumps(reply).encode())

    return urlopen, calls


NO_DELIVERY_ENV = {
    k: "" for k in ("DELIVERY", "TEXTBELT_KEY", "TWILIO_ACCOUNT_SID", "EMAIL_TO", "SMTP_USERNAME", "SCHEDULE")
}


class Delivery(unittest.TestCase):
    def run_main(self, env, argv=()):
        with mock.patch.dict(os.environ, {**NO_DELIVERY_ENV, **env}), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            code = send.main(list(argv))
        return code, out.getvalue()

    def test_picks_delivery_from_whichever_secrets_are_set(self):
        cases = [
            ({}, []),
            ({"TEXTBELT_KEY": "k"}, ["textbelt"]),
            ({"TWILIO_ACCOUNT_SID": "AC1"}, ["twilio"]),
            ({"TEXTBELT_KEY": "k", "TWILIO_ACCOUNT_SID": "AC1"}, ["textbelt"]),
            ({"EMAIL_TO": "e@x.com", "SMTP_USERNAME": "me@x.com"}, ["email"]),
            ({"DELIVERY": "sms, email"}, ["twilio", "email"]),
        ]
        for env, expected in cases:
            with mock.patch.dict(os.environ, {**NO_DELIVERY_ENV, **env}):
                self.assertEqual(send.delivery_methods(), expected, env)

    def test_unknown_delivery_fails(self):
        with mock.patch.dict(os.environ, {**NO_DELIVERY_ENV, "DELIVERY": "pigeon"}):
            with self.assertRaises(SystemExit):
                send.delivery_methods()

    def test_nothing_set_up_sends_nothing_and_does_not_fail(self):
        with mock.patch.object(send.urllib.request, "urlopen") as urlopen:
            code, out = self.run_main({})
        self.assertEqual(code, 0)
        urlopen.assert_not_called()
        self.assertIn("Nothing is set up", out)

    def test_textbelt_sends_todays_message_with_sign_off(self):
        urlopen, calls = fake_textbelt({"success": True, "textId": "1", "quotaRemaining": 40})
        env = {"TEXTBELT_KEY": "abc", "SMS_TO": "+12085550100", "SIGN_OFF": "- E"}
        with mock.patch.object(send.urllib.request, "urlopen", urlopen):
            code, out = self.run_main(env, ["--date", "2026-11-04"])
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].full_url, "https://textbelt.com/text")
        form = dict(urllib.parse.parse_qsl(calls[0].data.decode()))
        expected = send.compose(send.pick_message(MESSAGES, dt.date(2026, 11, 4))[1], "Emma", "- E")
        self.assertEqual(form, {"phone": "+12085550100", "message": expected, "key": "abc"})
        self.assertIn("Texts left: 40", out)
        self.assertNotIn("::warning::", out)

    def test_textbelt_warns_when_credits_run_low(self):
        urlopen, _ = fake_textbelt({"success": True, "quotaRemaining": 3})
        env = {"TEXTBELT_KEY": "abc", "SMS_TO": "+12085550100", "SIGN_OFF": "- E"}
        with mock.patch.object(send.urllib.request, "urlopen", urlopen):
            _, out = self.run_main(env)
        self.assertIn("::warning::Only 3 Textbelt texts left", out)

    def test_textbelt_failure_fails_the_run(self):
        urlopen, _ = fake_textbelt({"success": False, "error": "Out of quota"})
        env = {"TEXTBELT_KEY": "abc", "SMS_TO": "+12085550100", "SIGN_OFF": "- E"}
        with mock.patch.object(send.urllib.request, "urlopen", urlopen):
            with self.assertRaises(SystemExit) as raised:
                self.run_main(env)
        self.assertIn("Out of quota", str(raised.exception))

    def test_texting_without_a_sign_off_warns(self):
        urlopen, _ = fake_textbelt({"success": True, "quotaRemaining": 40})
        with mock.patch.object(send.urllib.request, "urlopen", urlopen):
            _, out = self.run_main({"TEXTBELT_KEY": "abc", "SMS_TO": "+12085550100"})
        self.assertIn("SIGN_OFF isn't set", out)

    def test_dry_run_checks_credits_but_sends_nothing(self):
        urlopen, calls = fake_textbelt({"success": True, "quotaRemaining": 48})
        env = {"TEXTBELT_KEY": "abc", "SMS_TO": "+12085550100", "SIGN_OFF": "- E"}
        with mock.patch.object(send.urllib.request, "urlopen", urlopen):
            _, out = self.run_main(env, ["--dry-run"])
        self.assertEqual([c.full_url for c in calls], ["https://textbelt.com/quota/abc"])
        self.assertIn("Textbelt texts left: 48", out)


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
