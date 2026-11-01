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

1. Every hour, GitHub Actions (free) posts today's message at a public link:
   - **Android:** <https://raw.githubusercontent.com/ethanspadecreative/morning-messages/messages/today.txt>, which holds just today's message
   - **iPhone:** <https://raw.githubusercontent.com/ethanspadecreative/morning-messages/messages/upcoming.json>, which holds the next two weeks
2. Every morning, an automation on your phone reads the link and texts the message to Emma from your number.

You set it up once and never touch it again. GitHub can't send texts by itself for free, so your phone does the sending. That's also why she sees it coming from you.

## Android setup (Samsung Galaxy etc.)

Takes about 10 minutes, once. It uses **MacroDroid**, a free automation app. The free version allows 5 automations, and this needs 1.

### 1. Build the automation

1. Install **MacroDroid** from the Play Store, open it, and tap **Add Macro**. Name it something like *Morning text*.
2. **Trigger:** tap **+** under Triggers, then **Date/Time → Day/Time Trigger**. Set **7:30 AM**, select **all seven days**, and tap **OK**.
3. **Actions:** tap **+** under Actions and add these four, in order. Each picker has a search icon. If a name differs slightly in your version, search for it.
   1. **Set Variable**: create a new local **integer** variable named `code` and set it to `0`.
   2. **HTTP Request**: method **GET**, URL
      `https://raw.githubusercontent.com/ethanspadecreative/morning-messages/messages/today.txt`
      In its options, save the **response** to a new local **string** variable named `message`. Save the **response code** to the `code` variable.
   3. **If Clause**: add a condition for the variable `code`, set to **equals 200**. MacroDroid adds an **End If** for you.
   4. **Send SMS**: put it between the *If* and the *End If*. Choose **Emma** from your contacts. For the message text, tap the magic-text button (the **…** or **[ ]** icon) and pick the local variable `message`. The field should end up showing `[lv=message]`.
4. Tap the **✓** to save. Allow SMS permission when MacroDroid asks.

The *code = 200* check means that if the internet or GitHub is down that morning, nothing gets sent. She'll never get an error message or a repeat.

### 2. Stop Samsung from putting MacroDroid to sleep

Samsung phones aggressively freeze background apps, and a frozen MacroDroid misses the 7:30 trigger. Do both of these:

- **Settings → Apps → MacroDroid → Battery →** choose **Unrestricted**.
- **Settings → Battery → Background usage limits:** make sure MacroDroid isn't under *Sleeping apps* or *Deep sleeping apps*, then add it to **Never sleeping apps**.

### 3. Test it on yourself

Temporarily change the Send SMS recipient to **your own number**. Then change the trigger time to two minutes from now, save, and wait. You should get today's message. Then put Emma back as the recipient and the time back to 7:30.

The texts go out as normal SMS from your number, and they should show up in your Messages conversation with her like any text you send.

## iPhone setup

In the **Shortcuts** app:

1. Go to the **Automation** tab, tap **+**, and choose **Time of Day**. Set **7:30 AM** and **Daily**, pick **Run Immediately**, and turn off **Notify When Run**. Tap **Next**, then **New Blank Automation**.
2. Add these actions in order:
   1. **Format Date**: date *Current Date*, format **Custom**, format string `yyyy-MM-dd`.
   2. **Get Contents of URL**: `https://raw.githubusercontent.com/ethanspadecreative/morning-messages/messages/upcoming.json`
   3. **Get Dictionary from Input**
   4. **Get Dictionary Value**: get **Value** for key *Formatted Date* in *Dictionary*.
   5. **If**: *Dictionary Value* **has any value**.
   6. **Send Message**: put it inside the *If*. Message *Dictionary Value*, recipient **Emma**. Expand the action and turn off **Show When Run**.
3. Tap **Done**. Test it by setting the recipient to yourself and tapping ▶︎.

## Changing things

**The messages** are in [`messages.txt`](messages.txt), one per line. You can edit it right on GitHub. `{name}` becomes her name. Delete any that don't sound like you, and add your own. Inside jokes beat anything on that list. Your edits reach the link within a minute or so.

**Settings.** These go under **Settings → Secrets and variables → Actions → Variables**. All are optional.

| Variable | Default | What it does |
|---|---|---|
| `RECIPIENT_NAME` | `Emma` | Fills in `{name}` in messages |
| `BIRTHDAY` | none | `MM-DD`. That day gets a birthday message. |
| `SIGN_OFF` | none | Added on its own line at the end of each message |
| `TIMEZONE` | `America/Boise` | Decides when "today" starts. Set it to your phone's timezone if you move. |

The send time lives in the phone automation, so change it there.

To preview what's coming, or to check messages after editing:

```sh
python send.py --preview 14   # next two weeks
python -m unittest            # checks every message: plain text, fits one SMS, no duplicates, nothing cheesy
```

## Optional: send from GitHub instead of your phone

If you'd rather not depend on your phone, [`send.yml`](.github/workflows/send.yml) can send by email (free, through your Gmail) or by text through Twilio (paid, from a separate number). Set the `DELIVERY` variable to `email`, `sms`, or `email,sms`, and add the matching secrets:

- **Email:** `EMAIL_TO`, `SMTP_USERNAME` (your Gmail), and `SMTP_PASSWORD`. The password is a [Google app password](https://myaccount.google.com/apppasswords), which needs 2-Step Verification turned on. Optionally add a variable `EMAIL_FROM_NAME`.
- **Twilio:** `SMS_TO` (like `+12085551234`), `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_FROM`. Costs a few dollars a month, and US carriers require a registration that takes a few days. Set `SIGN_OFF` so she knows who it's from.

This mode sends at `SEND_TIME` (default `07:30`) in `TIMEZONE`. If you change either, run `python send.py --print-cron` and paste the output over the two `cron` lines in `send.yml`. If they don't match, the run fails and tells you why.

## Good to know

- `today.txt` refreshes every hour, so it switches to the new day within an hour after midnight.
- If GitHub were down all night (very rare), `today.txt` would still hold yesterday's message, and the Android automation would send it again. The iPhone version looks up the date and would skip the day instead.
- GitHub pauses scheduled workflows in public repos after 60 days without activity. The workflow pings GitHub every hour to prevent that.
- The date alone picks the message, so the same day always gets the same one.
