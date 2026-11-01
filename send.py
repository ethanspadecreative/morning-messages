#!/usr/bin/env python3
"""Pick (and optionally send) one short good-morning message a day.

Messages live in messages.txt. The date alone decides which one goes out: the
list is walked in a shuffled order, so nothing repeats until every message has
been used, and re-running on the same day picks the same message. No database
or saved state needed.

Two ways to get it to her:
  --publish DIR   writes the next two weeks to DIR/upcoming.json; the workflow
                  posts that file publicly and a phone automation texts it
  DELIVERY=...    sends it from here by email (SMTP) and/or text (Twilio)

Standard library only. Python 3.9+.
"""

from __future__ import annotations

import argparse
import base64
import calendar
import datetime as dt
import json
import os
import random
import smtplib
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

HERE = Path(__file__).resolve().parent
EPOCH = dt.date(2024, 1, 1)  # a Monday; anchors the rotation
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DELIVERY_METHODS = ("email", "sms")


# --------------------------------------------------------------------------- config


def env(name: str, default: str = "") -> str:
    # GitHub passes unset repository variables as empty strings, so "" means unset.
    return os.environ.get(name, "").strip() or default


def require(name: str) -> str:
    value = env(name)
    if not value:
        sys.exit(f"Missing required setting: {name}")
    return value


def parse_time(value: str) -> dt.time:
    try:
        hour, minute = value.split(":")
        return dt.time(int(hour), int(minute))
    except ValueError:
        sys.exit(f"SEND_TIME should look like 07:30, got {value!r}")


def parse_birthday(value: str) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        month, day = (int(part) for part in value.split("-"))
        dt.date(2024, month, day)  # validate; 2024 is a leap year so 02-29 is allowed
    except ValueError:
        sys.exit(f"BIRTHDAY should look like MM-DD, got {value!r}")
    return month, day


def parse_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        sys.exit(f"TIMEZONE should be a name like America/Boise, got {value!r}")


# ------------------------------------------------------------------ picking a message


def load_messages(path: Path) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = "general"
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().lower()
            continue
        sections.setdefault(current, []).append(line)
    if not sections.get("general"):
        sys.exit(f"{path} has no messages in its [general] section")
    return sections


def _shuffled(pool: list[str], salt: str, cycle: int) -> list[str]:
    order = list(pool)
    random.Random(f"{salt}:{cycle}").shuffle(order)
    return order


def rotate(pool: list[str], index: int, salt: str) -> str:
    """Return the index-th message from a fresh shuffle of the pool each pass.

    Everything in the pool gets used once before anything comes around again.
    """
    cycle, position = divmod(index, len(pool))
    order = _shuffled(pool, salt, cycle)
    # Don't send the same message two days running where one pass ends and the next
    # begins. Swapping the first two leaves the previous pass's last entry untouched.
    if len(order) > 2 and order[0] == _shuffled(pool, salt, cycle - 1)[-1]:
        order[0], order[1] = order[1], order[0]
    return order[position]


def is_birthday(day: dt.date, birthday: tuple[int, int] | None) -> bool:
    if birthday is None:
        return False
    if birthday == (2, 29) and not calendar.isleap(day.year):
        return (day.month, day.day) == (2, 28)
    return (day.month, day.day) == birthday


def pick_message(
    sections: dict[str, list[str]], day: dt.date, birthday: tuple[int, int] | None = None
) -> tuple[str, str]:
    """Return (section, message template) for the given date."""
    if is_birthday(day, birthday) and sections.get("birthday"):
        return "birthday", rotate(sections["birthday"], day.year, "birthday")
    days = (day - EPOCH).days
    weekday = WEEKDAYS[day.weekday()]
    if sections.get(weekday):
        return weekday, rotate(sections[weekday], days // 7, weekday)
    return "general", rotate(sections["general"], days, "general")


def compose(template: str, name: str, sign_off: str = "") -> str:
    text = template.replace("{name}", name)
    return f"{text}\n{sign_off}" if sign_off else text


def upcoming(
    sections: dict[str, list[str]],
    start: dt.date,
    days: int,
    name: str,
    sign_off: str = "",
    birthday: tuple[int, int] | None = None,
) -> dict[str, str]:
    """{"YYYY-MM-DD": message} for `days` days from `start`."""
    out = {}
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        out[day.isoformat()] = compose(pick_message(sections, day, birthday)[1], name, sign_off)
    return out


# ------------------------------------------------------------------------ scheduling


def utc_slot(day: dt.date, send_time: dt.time, tz: ZoneInfo) -> tuple[int, int]:
    """(hour, minute) in UTC when send_time happens in tz on that day."""
    utc = dt.datetime.combine(day, send_time, tzinfo=tz).astimezone(dt.timezone.utc)
    return utc.hour, utc.minute


def cron_slots(send_time: dt.time, tz: ZoneInfo, year: int) -> list[tuple[int, int]]:
    """Every UTC (hour, minute) send_time lands on during the year: two if tz has DST."""
    return sorted({utc_slot(dt.date(year, month, 15), send_time, tz) for month in range(1, 13)})


def parse_cron_slot(cron: str) -> tuple[int, int]:
    fields = cron.split()
    try:
        return int(fields[1]), int(fields[0])
    except (IndexError, ValueError):
        sys.exit(f"Expected a cron with a fixed minute and hour like '30 14 * * *', got {cron!r}")


def should_send(cron: str, now_utc: dt.datetime, send_time: dt.time, tz: ZoneInfo) -> bool:
    """Is this scheduled run the one that should send today?

    GitHub cron runs on UTC, so the workflow has one cron line per UTC offset the
    timezone uses (daylight and standard time). Only the line that matches today's
    offset sends; the other exits quietly. The check uses the run's *scheduled*
    slot, not the clock, so GitHub's habit of starting runs late can't cause a
    skipped or doubled message.
    """
    slot = parse_cron_slot(cron)
    today = now_utc.astimezone(tz).date()
    if slot not in cron_slots(send_time, tz, today.year):
        sys.exit(
            f"The workflow cron {cron!r} doesn't match SEND_TIME {send_time:%H:%M} in {tz.key}. "
            "Run `python send.py --print-cron` and paste its output into the workflow file."
        )
    return slot == utc_slot(today, send_time, tz)


# -------------------------------------------------------------------------- delivery


def send_email(body: str, subject: str) -> None:
    host = env("SMTP_HOST", "smtp.gmail.com")
    port = int(env("SMTP_PORT", "465"))
    username = require("SMTP_USERNAME")
    password = require("SMTP_PASSWORD")
    if host == "smtp.gmail.com":
        password = password.replace(" ", "")  # Google shows app passwords in groups of four

    msg = EmailMessage()
    msg["From"] = formataddr((env("EMAIL_FROM_NAME"), env("EMAIL_FROM", username)))
    msg["To"] = require("EMAIL_TO")
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(body)

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            smtp.login(username, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            smtp.send_message(msg)
    print("Sent by email.")


def send_sms(body: str) -> None:
    sid = require("TWILIO_ACCOUNT_SID")
    token = require("TWILIO_AUTH_TOKEN")
    sender = require("TWILIO_FROM")
    fields = {"To": require("SMS_TO"), "Body": body}
    # A Messaging Service SID (starts with MG) is what US A2P-registered senders use.
    fields["MessagingServiceSid" if sender.startswith("MG") else "From"] = sender

    request = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=urllib.parse.urlencode(fields).encode(),
        method="POST",
    )
    credentials = base64.b64encode(f"{sid}:{token}".encode()).decode()
    request.add_header("Authorization", f"Basic {credentials}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"Twilio rejected the message ({error.code}): {error.read().decode(errors='replace')}")
    print(f"Sent by text (Twilio status: {result.get('status')}).")


# ------------------------------------------------------------------------------ main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send today's good-morning message.")
    parser.add_argument("--dry-run", action="store_true", help="print the message instead of sending it")
    parser.add_argument("--preview", type=int, metavar="DAYS", help="print the next DAYS messages and exit")
    parser.add_argument("--date", type=dt.date.fromisoformat, help="act as if today were YYYY-MM-DD")
    parser.add_argument(
        "--print-cron", action="store_true", help="print the workflow cron lines for SEND_TIME and TIMEZONE"
    )
    parser.add_argument(
        "--publish", type=Path, metavar="DIR", help="write the next two weeks to DIR/upcoming.json and exit"
    )
    args = parser.parse_args(argv)

    name = env("RECIPIENT_NAME", "Emma")
    tz = parse_timezone(env("TIMEZONE", "America/Boise"))
    send_time = parse_time(env("SEND_TIME", "07:30"))
    birthday = parse_birthday(env("BIRTHDAY"))
    sign_off = env("SIGN_OFF")
    sections = load_messages(Path(env("MESSAGES_FILE", str(HERE / "messages.txt"))))

    now = dt.datetime.now(dt.timezone.utc)
    today = args.date or now.astimezone(tz).date()

    if args.print_cron:
        print(f"# {send_time:%H:%M} in {tz.key}")
        for hour, minute in cron_slots(send_time, tz, today.year):
            print(f'    - cron: "{minute} {hour} * * *"')
        return 0

    if args.preview:
        for offset in range(args.preview):
            day = today + dt.timedelta(days=offset)
            section, template = pick_message(sections, day, birthday)
            tag = "" if section == "general" else f"  [{section}]"
            print(f"{day:%a %b %d}{tag}")
            print(textwrap.indent(compose(template, name, sign_off), "  "))
        return 0

    if args.publish:
        # Start a day back so a phone a timezone or two away still finds "today".
        # Two weeks ahead means a few failed runs in a row don't leave it empty.
        data = upcoming(sections, today - dt.timedelta(days=1), 16, name, sign_off, birthday)
        args.publish.mkdir(parents=True, exist_ok=True)
        path = args.publish / "upcoming.json"
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(data)} days ({min(data)} to {max(data)}) to {path}")
        return 0

    methods = [m.strip().lower() for m in env("DELIVERY").split(",") if m.strip()]
    unknown = [m for m in methods if m not in DELIVERY_METHODS]
    if unknown:
        sys.exit(f"DELIVERY should be email, sms, or email,sms. Got {env('DELIVERY')!r}")

    schedule = env("SCHEDULE")  # the cron line that started this run; empty for manual runs
    if schedule and not args.date and not should_send(schedule, now, send_time, tz):
        print(f"Not this slot. The other cron line covers {tz.key}'s UTC offset today.")
        return 0

    _, template = pick_message(sections, today, birthday)
    body = compose(template, name, sign_off)

    print(f"Message for {today:%a %b %d}:\n{textwrap.indent(body, '  ')}")
    if not methods:
        print("DELIVERY isn't set, so nothing is sent from here (the phone automation does the sending).")
        return 0
    if args.dry_run:
        print(f"Dry run, nothing sent. Would have gone by: {', '.join(methods)}.")
        return 0

    subject = (
        env("EMAIL_SUBJECT", "Morning, {date}")
        .replace("{name}", name)
        .replace("{date}", f"{today:%b} {today.day}")
        .replace("{weekday}", f"{today:%A}")
    )
    for method in methods:
        if method == "email":
            send_email(body, subject)
        else:
            send_sms(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
