# Apple Shortcuts: single-day repeat bug

This integration relies on data refreshed from Apple Shortcuts. A known issue can
appear when a shortcut is configured to repeat **only on a single day** (for
example, Monday only). In some cases, the iOS Shortcuts repeat setting does not
return the expected schedule for a single selected weekday, which can result in
missing or inconsistent refreshes.

## Symptoms

- A shortcut that should run weekly on a single day does not refresh the
  integration reliably.
- The refresh timestamps stop updating even though the shortcut looks correct in
  the Shortcuts app.

## Workarounds

1. **Use multiple days.** Temporarily select two days (e.g., Monday + Tuesday)
   for the repeating schedule and test whether the refresh resumes.
2. **Duplicate the shortcut.** Create two shortcuts that run on alternating
   weeks or days if a single-day schedule fails.
3. **Re-save the automation.** Open the shortcut, change the repeat setting, and
   save it again to force iOS to refresh the schedule metadata.

## Reporting

If you can reproduce this behavior consistently, please include the following in
an issue:

- iOS version
- Shortcuts app version
- A description of the repeat schedule you configured
- The `refresh_problem` binary sensor state and last refresh timestamps
