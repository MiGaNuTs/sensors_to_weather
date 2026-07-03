"""Sensors to Weather entity."""
from __future__ import annotations

import logging
import math
import statistics
from collections import Counter
from datetime import time, timedelta

from homeassistant.components.weather import WeatherEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
import homeassistant.util.dt as dt_util

from .const import (
    DOMAIN,
    ROLE_TEMPERATURE, ROLE_HUMIDITY, ROLE_PRESSURE,
    ROLE_WIND_SPEED, ROLE_WIND_GUST, ROLE_WIND_BEARING,
    ROLE_VISIBILITY, ROLE_CLOUD_COVERAGE, ROLE_PRECIPITATION,
    ROLE_PRECIPITATION_RATE, ROLE_CONDITION,
    detect_role,
)

_LOGGER = logging.getLogger(__name__)

CONDITION_VALUES = {
    "sunny", "clear-night", "partlycloudy", "windy-variant", "windy",
    "fog", "cloudy", "hail", "snowy", "snowy-rainy", "rainy",
    "pouring", "lightning", "lightning-rainy", "exceptional",
}

ALL_ROLES = [
    ROLE_TEMPERATURE, ROLE_HUMIDITY, ROLE_PRESSURE,
    ROLE_WIND_SPEED, ROLE_WIND_GUST, ROLE_WIND_BEARING,
    ROLE_VISIBILITY, ROLE_CLOUD_COVERAGE, ROLE_PRECIPITATION,
    ROLE_PRECIPITATION_RATE, ROLE_CONDITION,
]

# One published state per minute, aggregated from every raw sample collected
# during that window — smooths out noisy sensors emitting several points/min.
PUBLISH_INTERVAL = timedelta(minutes=1)

# Modified z-score threshold (Iglewicz & Hoaglin) for rejecting outliers
# within a single aggregation window before taking the median.
OUTLIER_THRESHOLD = 3.5


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    sensors = entry.options.get("sensors", entry.data.get("sensors", []))
    name = entry.options.get("name", entry.data.get("name", "Station météo"))
    async_add_entities([SensorsToWeatherEntity(hass, entry, sensors, name)])


class SensorsToWeatherEntity(WeatherEntity, RestoreEntity):
    """A weather entity built from local sensors."""

    _attr_has_entity_name = True
    _attr_native_temperature_unit = "°C"
    _attr_native_pressure_unit = "hPa"
    _attr_native_wind_speed_unit = "km/h"
    _attr_native_wind_gust_speed_unit = "km/h"
    _attr_native_visibility_unit = "km"
    _attr_native_precipitation_unit = "mm"

    def __init__(self, hass, entry, sensors, name):
        self.hass = hass
        self._entry = entry
        self._sensors = sensors
        self._attr_unique_id = entry.entry_id
        self._attr_name = name
        self._attr_condition = None
        self._attr_native_temperature = None
        self._attr_humidity = None
        self._attr_native_pressure = None
        self._attr_native_wind_speed = None
        self._attr_native_wind_gust_speed = None
        self._attr_wind_bearing = None
        self._attr_cloud_coverage = None
        self._attr_native_visibility = None
        self._attr_native_dew_point = None
        self._attr_native_apparent_temperature = None
        self._temp_min: float | None = None
        self._temp_max: float | None = None
        self._buffers: dict[str, list] = {role: [] for role in ALL_ROLES}
        try:
            self._collect_sample()
            self._flush()
        except Exception as err:
            _LOGGER.exception("Error during initial update: %s", err)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._restore_daily_min_max()
        self._setup_tracking()
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                self._handle_midnight_reset,
                hour=0, minute=0, second=0,
            )
        )
        self.async_on_remove(
            async_track_time_interval(
                self.hass,
                self._handle_flush,
                PUBLISH_INTERVAL,
            )
        )

    async def _restore_daily_min_max(self) -> None:
        """Restore temperature_min/max from the last known state, same day only."""
        last_state = await self.async_get_last_state()
        if last_state is None:
            return

        if dt_util.as_local(last_state.last_changed).date() != dt_util.now().date():
            # Last known state is from a previous day — a midnight reset
            # would have happened anyway, so start fresh.
            return

        temp_min = last_state.attributes.get("temperature_min")
        temp_max = last_state.attributes.get("temperature_max")
        if temp_min is not None:
            self._temp_min = temp_min
        if temp_max is not None:
            self._temp_max = temp_max
        _LOGGER.debug(
            "Restored daily min/max after restart: min=%s, max=%s",
            self._temp_min, self._temp_max,
        )

    def _setup_tracking(self) -> None:
        if not self._sensors:
            return
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._sensors,
                self._handle_sensor_update,
            )
        )

    @callback
    def _handle_sensor_update(self, event) -> None:
        try:
            self._collect_sample()
        except Exception as err:
            _LOGGER.exception("Error collecting sensor sample: %s", err)

    @callback
    def _handle_flush(self, _now=None) -> None:
        try:
            self._flush()
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.exception("Error flushing aggregated weather state: %s", err)

    @callback
    def _handle_midnight_reset(self, _now=None) -> None:
        try:
            _LOGGER.debug("Midnight reset of daily temperature min/max.")
            self._temp_min = None
            self._temp_max = None
            self.async_write_ha_state()
        except Exception as err:
            _LOGGER.exception("Error during midnight reset: %s", err)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _reject_outliers(values: list, threshold: float = OUTLIER_THRESHOLD) -> list:
        """Drop samples too far from the median (modified z-score via MAD).

        Needs at least 3 samples to say anything meaningful about outliers;
        below that, everything is kept as-is.
        """
        clean = [v for v in values if v is not None]
        if len(clean) < 3:
            return clean
        med = statistics.median(clean)
        abs_devs = [abs(v - med) for v in clean]
        mad = statistics.median(abs_devs)
        if mad == 0:
            return clean
        filtered = [v for v, d in zip(clean, abs_devs) if (0.6745 * d / mad) <= threshold]
        return filtered if filtered else clean

    @staticmethod
    def _median(values: list) -> float | None:
        clean = [v for v in values if v is not None]
        if not clean:
            return None
        return round(statistics.median(clean), 1)

    @staticmethod
    def _circular_median(bearings: list) -> float | None:
        clean = [b for b in bearings if b is not None]
        if not clean:
            return None
        sin_avg = sum(math.sin(math.radians(b)) for b in clean) / len(clean)
        cos_avg = sum(math.cos(math.radians(b)) for b in clean) / len(clean)
        return round(math.degrees(math.atan2(sin_avg, cos_avg)) % 360, 1)

    @staticmethod
    def _compute_dew_point(temp, humidity):
        if temp is None or humidity is None or humidity <= 0:
            return None
        try:
            gamma = math.log(humidity / 100) + (7.5 * temp) / (237.7 + temp)
            return round(237.7 * gamma / (7.5 - gamma), 1)
        except Exception:
            return None

    @staticmethod
    def _compute_apparent_temp(temp, dew_point):
        if temp is None or dew_point is None:
            return None
        try:
            e = 6.11 * (10 ** ((7.5 * dew_point) / (237.7 + dew_point)))
            return round(temp + 0.5555 * (e - 10), 1)
        except Exception:
            return None

    # ── Sampling (called on every source sensor change) ─────────────────────

    def _collect_sample(self) -> None:
        """Read current source states and append raw values to the buffers."""
        for entity_id in self._sensors:
            try:
                state = self.hass.states.get(entity_id)
                if state is None or state.state in ("unavailable", "unknown", ""):
                    continue

                # Condition sensor — entity_id ends with _state
                if entity_id.endswith("_state"):
                    if state.state in CONDITION_VALUES:
                        self._buffers[ROLE_CONDITION].append(state.state)
                    continue

                role = detect_role(state)
                if role is None:
                    _LOGGER.debug("Sensor %s: unrecognized role, skipping.", entity_id)
                    continue

                # All other roles — numeric value
                try:
                    value = float(state.state)
                except (ValueError, TypeError):
                    _LOGGER.debug("Sensor %s has non-numeric state, skipping.", entity_id)
                    continue

                self._buffers[role].append(value)

            except Exception as err:
                _LOGGER.warning("Unexpected error reading sensor %s: %s", entity_id, err)

    # ── Flush (called once per PUBLISH_INTERVAL) ─────────────────────────────

    def _flush(self) -> None:
        """Aggregate the buffered samples into the published state."""
        buffers = self._buffers
        self._buffers = {role: [] for role in ALL_ROLES}

        # Aggregate numeric values — outliers dropped before taking the median
        temp = self._median(self._reject_outliers(buffers[ROLE_TEMPERATURE]))
        humidity = self._median(self._reject_outliers(buffers[ROLE_HUMIDITY]))

        self._attr_native_temperature = temp
        self._attr_humidity = humidity
        self._attr_native_pressure = self._median(self._reject_outliers(buffers[ROLE_PRESSURE]))
        self._attr_native_wind_speed = self._median(self._reject_outliers(buffers[ROLE_WIND_SPEED]))
        self._attr_native_wind_gust_speed = self._median(self._reject_outliers(buffers[ROLE_WIND_GUST]))
        # Circular data (bearing) isn't compatible with the MAD rejection above.
        self._attr_wind_bearing = self._circular_median(buffers[ROLE_WIND_BEARING])
        self._attr_cloud_coverage = self._median(self._reject_outliers(buffers[ROLE_CLOUD_COVERAGE]))
        self._attr_native_visibility = self._median(self._reject_outliers(buffers[ROLE_VISIBILITY]))

        # Condition — majority vote over the window. Keep the last known
        # condition if nothing came in this window rather than blanking it.
        conditions = buffers[ROLE_CONDITION]
        if conditions:
            self._attr_condition = Counter(conditions).most_common(1)[0][0]

        # Dew point and apparent temp only if humidity available
        if humidity is not None:
            self._attr_native_dew_point = self._compute_dew_point(temp, humidity)
            self._attr_native_apparent_temperature = self._compute_apparent_temp(
                temp, self._attr_native_dew_point
            )
        else:
            self._attr_native_dew_point = None
            self._attr_native_apparent_temperature = None

        # Daily min/max temperature tracking
        if temp is not None:
            if self._temp_min is None or temp < self._temp_min:
                self._temp_min = temp
            if self._temp_max is None or temp > self._temp_max:
                self._temp_max = temp

        self._attr_available = temp is not None

        _LOGGER.debug(
            "Flushed: temp=%s (min=%s, max=%s), humidity=%s, condition=%s, samples=%d",
            temp, self._temp_min, self._temp_max,
            humidity, self._attr_condition,
            sum(len(v) for v in buffers.values()),
        )

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "temperature_min": self._temp_min,
            "temperature_max": self._temp_max,
            "temperature_unit": self._attr_native_temperature_unit,
        }
