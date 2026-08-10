"""Shared configuration and optional runtime dependencies."""

try:
    import ruuvitag_sensor.log
    from ruuvitag_sensor.ruuvi import RuuviTagSensor

    ruuvitag_sensor.log.enable_console()
    RUUVITAG_AVAILABLE = True
except Exception:  # pragma: no cover - depends on runtime environment
    RuuviTagSensor = None
    RUUVITAG_AVAILABLE = False


RUUVITAG_SENSORS = [
    ("Makuuhuone", "F5:F5:9A:56:D1:4F"),
    ("Keittiö", "C1:33:99:C1:3E:79"),
    ("Terassi", "DC:7A:39:53:77:91"),
]

RUUVITAG_SENSOR_NAME = RUUVITAG_SENSORS[0][0]
RUUVITAG_SENSOR_MAC = RUUVITAG_SENSORS[0][1]
RUUVITAG_SENSOR = RUUVITAG_SENSORS[0]
