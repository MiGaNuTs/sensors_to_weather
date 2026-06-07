# Sensors to Weather

A Home Assistant custom component that turns local sensors into a native `weather.*` entity — perfect for weather stations, DIY sensors, or any combination of physical sensors.

## How it works

Select any sensors in the config flow. The integration automatically detects each sensor's role based on its `device_class` and `unit_of_measurement`:

| Role | device_class | Units |
|---|---|---|
| Temperature | `temperature` | °C, °F, K |
| Humidity | `humidity` | % |
| Pressure | `pressure` | hPa, mbar, Pa, inHg |
| Wind speed | `wind_speed` | km/h, m/s, mph, kn |
| Wind gust | `wind_speed` + "gust" in name | km/h, m/s, mph, kn |
| Wind bearing | `wind_direction` | ° |
| Visibility | `distance` | km, mi, m |
| Cloud coverage | `cloud_coverage` | % |
| Precipitation | `precipitation` | mm, in |

Unrecognized sensors are silently ignored.

## Features

- **Multiple sensors per role** → median aggregation (robust against outliers)
- **Dew point** → calculated from temperature + humidity (Magnus formula)
- **Apparent temperature** → calculated from temperature + dew point (Steadman formula), only if humidity is available
- **Condition** → derived from available data (precipitation → rainy, wind → windy, cloud coverage → cloudy/partlycloudy/sunny/clear-night)
- **Daily min/max temperature** → tracked since midnight, reset automatically at midnight
- Reactive: updates instantly when any source sensor changes

## Installation

### Via HACS (recommended)

1. In HACS, go to **Integrations → Custom repositories**
2. Add this repository URL, category: **Integration**
3. Install **Sensors to Weather**
4. Restart Home Assistant

### Manual

1. Copy `custom_components/sensors_to_weather/` into your HA `/config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings → Devices & Services → Add Integration → Sensors to Weather**
2. Give it a name and select your sensors
3. A `weather.*` entity appears, ready to use in dashboards alongside cloud-based weather entities

## Requirements

- Home Assistant 2024.1 or newer
- At least one temperature sensor

## License

MIT
