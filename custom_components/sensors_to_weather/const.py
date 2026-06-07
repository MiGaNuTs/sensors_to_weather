"""Constants and sensor role detection for Sensors to Weather."""

DOMAIN = "sensors_to_weather"

# Sensor roles
ROLE_TEMPERATURE = "temperature"
ROLE_HUMIDITY = "humidity"
ROLE_PRESSURE = "pressure"
ROLE_WIND_SPEED = "wind_speed"
ROLE_WIND_GUST = "wind_gust_speed"
ROLE_WIND_BEARING = "wind_bearing"
ROLE_VISIBILITY = "visibility"
ROLE_CLOUD_COVERAGE = "cloud_coverage"
ROLE_PRECIPITATION = "precipitation"
ROLE_PRECIPITATION_RATE = "precipitation_rate"

TEMPERATURE_UNITS = {"°C", "°F", "K"}
PRESSURE_UNITS = {"hPa", "mbar", "Pa", "inHg"}
WIND_SPEED_UNITS = {"km/h", "m/s", "mph", "kn"}
VISIBILITY_UNITS = {"km", "mi", "m"}
PRECIPITATION_UNITS = {"mm", "in"}
PRECIPITATION_RATE_UNITS = {"mm/h", "in/h"}


def detect_role(state) -> str | None:
    """Detect the weather role of a sensor based on device_class and unit."""
    if state is None:
        return None

    attrs = state.attributes
    unit = attrs.get("unit_of_measurement", "")
    dc = attrs.get("device_class", "")
    entity_id = state.entity_id.lower()

    if dc == "temperature" or unit in TEMPERATURE_UNITS:
        return ROLE_TEMPERATURE

    if dc == "humidity":
        return ROLE_HUMIDITY

    if dc == "pressure" or unit in PRESSURE_UNITS:
        return ROLE_PRESSURE

    if dc == "wind_speed" and unit in WIND_SPEED_UNITS:
        return ROLE_WIND_SPEED

    # Rafales : wind_speed device_class mais avec "gust" dans le nom
    if dc == "wind_speed" and "gust" in entity_id:
        return ROLE_WIND_GUST

    if dc == "wind_direction" or (unit == "°" and "bearing" in entity_id):
        return ROLE_WIND_BEARING

    if dc == "distance" and unit in VISIBILITY_UNITS:
        return ROLE_VISIBILITY

    if dc == "cloud_coverage" or ("cloud" in entity_id and unit == "%"):
        return ROLE_CLOUD_COVERAGE

    if dc == "precipitation_intensity" or unit in PRECIPITATION_RATE_UNITS:
        return ROLE_PRECIPITATION_RATE

    if dc == "precipitation" or unit in PRECIPITATION_UNITS:
        return ROLE_PRECIPITATION

    return None
