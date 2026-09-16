"""Diagnostic sensor showing the last successful import."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SnoPUDCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SnoPUDCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SnoPUDLastImportSensor(coordinator, entry)])


class SnoPUDLastImportSensor(CoordinatorEntity[SnoPUDCoordinator], SensorEntity):
    """Reports the total kWh in the most recent import window (diagnostic)."""

    _attr_has_entity_name = True
    _attr_name = "Last import total"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SnoPUDCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_import_total"

    @property
    def native_value(self) -> float | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("total_kwh")

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        return {
            "hours_imported": data.get("hours"),
            "last_hour_utc": str(data.get("last_hour")) if data.get("last_hour") else None,
        }
