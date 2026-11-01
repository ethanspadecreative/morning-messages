# Morning messages

Texts Emma one short, warm message every morning, from your own number, for free. You don't type anything. The messages aim to sound like you, not a greeting card.

A few from the list:

> Drink some water before the coffee. Or after. I'm not in charge of you.
>
> Hi Emma. Hope today is boring in the good way.
>
> I think about how lucky I got in the cousin department more than you'd guess.
>
> It's Friday, so today counts as half a day in spirit.

There are about 80 everyday messages, plus a few for Mondays, Fridays, and her birthday. Nothing repeats until the whole list has been used, and she never gets the same message two days running.

## How it works

1. Every day, GitHub Actions (free) picks the messages for the next two weeks and posts them at
   <https://raw.githubusercontent.com/ethanspadecreative/morning-messages/messages/upcoming.json>
2. Every morning, a Shortcuts automation on your iPhone reads today's message from that link and texts it to Emma from your number.

You set it up once and never touch it again. GitHub can't send texts by itself for free, so your phone does the sending. That's also why she sees it coming from you.

## Setup (about 10 minutes, once)

### 1. Make the repo public

Your phone can only read the link without a password if the repo is public.

**Settings → General →** scroll to **Danger Zone → Change visibility → Make public.**

That makes the code, the message list, and Emma's first name visible to anyone. It also makes the Actions logs public, and they show the day's message. Secrets (anything under Settings → Secrets) stay hidden.

### 2. Check the link works

Open **Actions → Morning message → Run workflow → Run workflow**. When it's done (about 30 seconds), the link above should show a list of dates and messages. It also refreshes on its own every day and whenever you edit `messages.txt`.

### 3. Set up the automation on your iPhone

In the **Shortcuts** app:

1. Go to the **Automation** tab, tap **+**, and choose **Time of Day**.
2. Set the time (say 7:30 AM) and **Daily**. Pick **Run Immediately** and turn off **Notify When Run**. Tap **Next**, then **New Blank Automation**.
3. Add these actions in order. Use the search bar at the bottom to find each one.
   1. **Format Date**: leave the date as *Current Date*. Set *Date Format* to **Custom** and the format string to `yyyy-MM-dd`.
   2. **Get Contents of URL**: paste
      `https://raw.githubusercontent.com/ethanspadecreative/morning-messages/messages/upcoming.json`
   3. **Get Dictionary from Input**: it picks up *Contents of URL* automatically.
   4. **Get Dictionary Value**: set it to *Get **Value** for **Formatted Date** in **Dictionary***. For the key, tap the field and pick the *Formatted Date* variable.
   5. **If**: set it to *Dictionary Value* **has any value**.
   6. **Send Message**: drag it inside the *If*. Set the message to *Dictionary Value* and the recipient to **Emma**. Tap the arrow on the action and turn off **Show When Run**.
4. Tap **Done**.

**Test it on yourself first.** Set the recipient to yourself and tap ▶︎ at the bottom of the editor. You should get today's message. Then switch the recipient back to Emma.

The *If* step means that if something ever breaks on GitHub's side, your phone sends nothing. It won't send her an error message. Your phone needs to be on at send time, but it can be locked. If it's dead that morning, the message for that day is skipped.

**On Android?** The same setup works with an automation app like Tasker or MacroDroid. It fetches the link and sends an SMS.

## Changing things

**The messages** are in [`messages.txt`](messages.txt), one per line. You can edit it right on GitHub. `{name}` becomes her name. Delete any that don't sound like you, and add your own. Inside jokes beat anything on that list. Your edits reach the link within a minute or so.

**Settings.** These go under **Settings → Secrets and variables → Actions → Variables**. All are optional.

| Variable | Default | What it does |
|---|---|---|
| `RECIPIENT_NAME` | `Emma` | Fills in `{name}` in messages |
| `BIRTHDAY` | none | `MM-DD`. That day gets a birthday message. |
| `SIGN_OFF` | none | Added on its own line at the end of each message |

The send time lives in the iPhone automation, so change it there.

To see what's coming up, or to check messages after editing:

```sh
python send.py --preview 14   # next two weeks
python -m unittest            # checks every message: plain text, fits one SMS, no duplicates, nothing cheesy
```

## Optional: send from GitHub instead of your phone

If you'd rather not depend on your phone, the workflow can send by email (free, through your Gmail) or by text through Twilio (paid, from a separate number). Set the `DELIVERY` variable to `email`, `sms`, or `email,sms`, and add the matching secrets:

- **Email:** `EMAIL_TO`, `SMTP_USERNAME` (your Gmail), and `SMTP_PASSWORD`. The password is a [Google app password](https://myaccount.google.com/apppasswords), which needs 2-Step Verification turned on. Optionally add a variable `EMAIL_FROM_NAME`.
- **Twilio:** `SMS_TO` (like `+12085551234`), `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM`. Costs a few dollars a month, and US carriers require a registration that takes a few days. Set `SIGN_OFF` so she knows who it's from.

This mode sends at `SEND_TIME` (default `07:30`) in `TIMEZONE` (default `America/Boise`). If you change either, run `python send.py --print-cron` and paste the output over the two `cron` lines in [`.github/workflows/morning-message.yml`](.github/workflows/morning-message.yml). If they don't match, the run fails and tells you why.

## Good to know

- The link always holds yesterday plus the next two weeks. Even if GitHub has a bad few days, the phone still finds today's message.
- GitHub pauses scheduled workflows in public repos after 60 days without activity. The workflow pings GitHub every day to prevent that.
- The date alone picks the message, so the same day always gets the same one.
