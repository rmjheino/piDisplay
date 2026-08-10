"""Shared configuration and optional runtime dependencies."""

try:
    import ruuvitag_sensor.log
    from ruuvitag_sensor.ruuvi import RuuviTagSensor

    ruuvitag_sensor.log.enable_console()
    RUUVITAG_AVAILABLE = True
except Exception:  # pragma: no cover - depends on runtime environment
    RuuviTagSensor = None
    RUUVITAG_AVAILABLE = False


RUUVITAG_SENSOR_NAME = "Makuuhuone"
RUUVITAG_SENSOR_MAC = "F5:F5:9A:56:D1:4F"
RUUVITAG_SENSOR = (RUUVITAG_SENSOR_NAME, RUUVITAG_SENSOR_MAC)
RUUVITAG_SENSORS = [RUUVITAG_SENSOR]
