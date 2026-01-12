# Apple Shortcuts bug: single-day repeating alarms crash

This document explains a confirmed bug in Apple Shortcuts that affects the **HA iOS NextAlarm** integration.

## Summary

If **any alarm** in the iOS Clock app is configured to repeat on **only one day of the week**, Apple Shortcuts may **crash or terminate execution** when trying to read alarm repeat data.

When this happens:

- The shortcut fails silently or returns incomplete data.
- Home Assistant does not receive updated alarm information.
- The integration may report **refresh problems**, stale values, or missing alarms.

This is **not a bug in Home Assistant or this integration**. It is an Apple Shortcuts issue.

---

## What exactly happens?

The HA iOS NextAlarm shortcut reads the alarm configuration from the Clock app, including the list of repeat days.

When an alarm repeats on **exactly one day**, Shortcuts sometimes returns a malformed value for the `Repeat Days` field. This causes:

- A runtime error inside Shortcuts
- Or the shortcut to exit before sending data to Home Assistant

As a result, Home Assistant never receives the updated alarm state.

---

## How to fix the problem

### ✅ Recommended fix (simple)

Open the iOS **Clock** app and locate the alarm that:

- Is set to repeat on **only one day**

Then choose one of the following:

- **Remove repeating entirely**, or
- **Add at least one more day** so the alarm repeats on **two or more days per week**

Once no single-day repeating alarms exist, the shortcut will run correctly again.

---

### ⚠️ Advanced workaround (not recommended)

You can manually edit the shortcut:

1. Open the shortcut in the **Shortcuts** app.
2. Locate the dictionary at the very bottom of the shortcut.
3. Remove the `Repeat Days` key entirely.

This avoids the crash, but has side effects:

- Repeating alarms will **not refresh automatically**.
- Alarm data will only update when the shortcut is manually or externally triggered again.

This workaround is only suggested for advanced users who fully understand the implications.

---

## How to recognize this bug in Home Assistant

You may see:

- Binary sensors reporting a **refresh problem**
- Log entries indicating failed refresh or incomplete data
- No updates even though alarms were changed on the iPhone

If this happens, check your alarms in the iOS Clock app first.

---

## External references

This issue is documented by the community and reported in Apple forums:

- Apple Discussions:  
  https://discussions.apple.com/thread/256008048?sortBy=rank
- Reddit thread:  
  https://www.reddit.com/r/shortcuts/comments/1bhsul5/days_of_repetition_alarm_crash/

These reports confirm that the issue is caused by Apple Shortcuts when handling alarms that repeat on only one weekday.

---

## Final note

If you encounter refresh errors in HA iOS NextAlarm, **always verify your iOS alarms first**.

➡️ **There must be no alarms that repeat on only one day of the week.**  
➡️ Use either **no repeating** or **at least two days per week**.

Once corrected, the integration will resume normal operation.
