# Morning messages

Texts Emma one short, warm message every morning at 7:30. GitHub sends it automatically from a texting service's number, not yours, so your phone isn't involved. The messages aim to sound like a person, not a greeting card.

A few from the list:

> Drink some water before the coffee. Or after. I'm not in charge of you.
>
> Hi Emma. Hope today is boring in the good way.
>
> I think about how lucky I got in the cousin department more than you'd guess.
>
> It's Friday, so today counts as half a day in spirit.

There are about 80 everyday messages, plus a few for Mondays, Fridays, and her birthday. Nothing repeats until the whole list has been used, and she never gets the same message two days running.

## Cost

GitHub Actions is free. The texts go through [Textbelt](https://textbelt.com), which charges per text with no subscription or carrier paperwork. It's about $3 for 50 texts, so roughly $2 a month for one text a day. Check their site for current prices.

Sending a real text from a number that isn't yours costs something no matter which service you use. Textbelt is the cheapest and fastest to set up. Other options are listed [below](#other-ways-to-send).

## Setup (about 5 minutes)

### 1. Buy Textbelt credits

Go to [textbelt.com](https://textbelt.com), buy the smallest pack, and copy the **API key** it gives you.

### 2. Add two secrets to this repo

On GitHub, go to **Settings → Secrets and variables → Actions → Secrets → New repository secret**:

| Secret | Value |
|---|---|
| `TEXTBELT_KEY` | the key from Textbelt |
| `SMS_TO` | **your own** number for now, like `+12085551234` (you'll switch it to Emma's after testing) |

### 3. Sign the texts

The texts come from a Textbelt number she won't recognize, so they need your name. Go to the **Variables** tab (next to Secrets), click **New repository variable**, and add:

| Variable | Value |
|---|---|
| `SIGN_OFF` | `- ` plus your name, e.g. `- E` |

Every text then ends with that on its own line.

### 4. Test it

Go to **Actions → Send morning text → Run workflow**, uncheck **Dry run**, and click **Run workflow**. Today's message should reach your phone within a minute or so.

### 5. Point it at Emma

Edit the `SMS_TO` secret and put in Emma's number. That's it: from now on she gets a text every morning at 7:30 Mountain time.

## Good to know

- **Credits.** When fewer than a week's worth are left, the run shows a warning on GitHub. Once they run out, the run fails and GitHub emails you, so you'll know to top up.
- **Replies** go to Textbelt, not to you. The sending number can also change from day to day. The sign-off is how she knows it's you, and you might give her a heads-up before the first one.
- **Timing.** GitHub often starts scheduled runs a few minutes late, so a text might land at 7:40. Very rarely GitHub skips a run entirely.
- **Her timezone.** If Emma isn't on Mountain time, set the `TIMEZONE` variable (e.g. `America/Chicago`). Then run `python send.py --print-cron` and paste the output over the two `cron` lines in [`.github/workflows/send.yml`](.github/workflows/send.yml). The same goes for changing `SEND_TIME`. If the two don't match, the run fails and says why.
- **To check without sending:** run the workflow with **Dry run** checked. It prints today's message and how many Textbelt credits are left.

## Changing things

**The messages** are in [`messages.txt`](messages.txt), one per line, and you can edit them right on GitHub. `{name}` becomes her name. Delete any that don't sound like you, and add your own. Inside jokes beat anything on that list.

**Settings** are all optional. They go under **Settings → Secrets and variables → Actions → Variables**.

| Variable | Default | What it does |
|---|---|---|
| `SIGN_OFF` | none | Added on its own line at the end of each text |
| `RECIPIENT_NAME` | `Emma` | Fills in `{name}` in messages |
| `BIRTHDAY` | none | `MM-DD`. That day gets a birthday message. |
| `TIMEZONE` | `America/Boise` | Emma's timezone (see above) |
| `SEND_TIME` | `07:30` | Local time to send, 24-hour (see above) |

To see what's coming up, or to check the list after editing:

```sh
python send.py --preview 14   # next two weeks
python -m unittest            # checks every message: plain text, fits one SMS, no duplicates, nothing cheesy
```

## Other ways to send

Whichever service has its secrets filled in gets used automatically. To pick explicitly, set the `DELIVERY` variable to `textbelt`, `twilio`, `email`, or a combination like `textbelt,email`.

- **Twilio:** texts from one fixed number that's yours to keep, and she can reply to it. Costs about $20 up front for the US carrier registration, then a few dollars a month, and approval takes one to two weeks. Secrets: `SMS_TO`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM`, which is your Twilio number or a Messaging Service SID starting with `MG`.
- **Email (free):** sends from a Gmail account. You could make a separate one just for this. Secrets: `EMAIL_TO`, `SMTP_USERNAME` (the Gmail address), and `SMTP_PASSWORD`, a [Google app password](https://myaccount.google.com/apppasswords) that requires 2-Step Verification. Optionally add a variable `EMAIL_FROM_NAME`.
