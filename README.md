# HA iOS Next Alarm

HA iOS Next Alarm is a custom integration for Home Assistant that exposes the next scheduled alarm from the iOS Clock application as a Home Assistant sensor. It allows you to react to your upcoming alarms inside automations, for example by preparing your smart home for when you wake up.

## Features

- Fetches the upcoming alarm configured in the iOS Clock application.
- Updates the sensor automatically whenever the shortcut runs.
- Provides entities that can be used in Home Assistant automations and dashboards.

## Requirements

- Home Assistant 2023.8 or newer.
- The **Shortcuts** app on iOS with the HA iOS Next Alarm shortcut installed.
- Home Assistant Companion App for iOS with notifications enabled (recommended).

## Installation

1. Copy the `custom_components/ha_ios_nextalarm` folder into your Home Assistant `config/custom_components` directory.
2. Restart Home Assistant.
3. In Home Assistant, go to **Settings → Devices & Services → Integrations** and click **Add Integration**.
4. Search for **HA iOS Next Alarm** and follow the onboarding flow.

## iOS Shortcut setup

1. Download the dedicated shortcut to your iPhone. You can import it directly into the **Shortcuts** app.
2. When prompted, provide your name exactly as it appears in Home Assistant. This name is used to associate the device with your Home Assistant user.
3. Allow the shortcut to access the Home Assistant instance defined in the integration configuration.

## Recommended automations

To keep the sensor up to date you must trigger the shortcut regularly:

- **Minimum recommendation:** create a personal automation in the **Shortcuts** app that runs the shortcut when you close the iOS **Clock** application.
- **Additional recommendation:** add automations that run the shortcut whenever power is connected or disconnected. This captures changes that occur when your device starts charging overnight or is unplugged in the morning.

The more frequently the shortcut runs, the more accurate your next alarm sensor will be. Personal automations can run without confirmation on iOS 15+; make sure to disable "Ask Before Running" so the shortcut executes automatically.

## Usage

Once configured, the integration provides a sensor entity named `sensor.<device_name>_next_alarm`. You can reference it in automations, scripts, or dashboards to trigger routines before your alarm rings. If no alarm is currently enabled on the device, the sensor state is reported as `unknown`.

If you encounter issues or have feature requests, please open an issue in the [GitHub repository](https://github.com/andrzejf1994/HA-iOS-NextAlarm).
