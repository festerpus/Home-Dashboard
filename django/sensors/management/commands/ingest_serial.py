import json
import time
import serial

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from sensors.models import Device, Reading, State


class Command(BaseCommand):
    help = "Continuously ingest readings from the Arduino"

    def add_arguments(self, parser):
        parser.add_argument(
            "--port",
            default="COM4",
            help="Serial port, e.g. COM4",
        )

        parser.add_argument(
            "--interval",
            type=float,
            default=10,
            help="Seconds between readings",
        )

        parser.add_argument(
            "--reconnect-delay",
            type=float,
            default=3,
            help="Seconds between serial reconnect attempts",
        )

    def handle(self, *args, **options):
        port = options["port"]
        interval = options["interval"]
        reconnect_delay = options["reconnect_delay"]

        current_device = None

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting Arduino ingestion on {port}"
            )
        )

        try:
            while True:
                ser = None

                try:
                    self.stdout.write(
                        f"Opening {port}..."
                    )

                    ser = serial.Serial(
                        port,
                        baudrate=9600,
                        timeout=3,
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Connected to {port}"
                        )
                    )

                    # UNO normally resets when serial opens
                    time.sleep(2)

                    while True:
                        current_device = self.ingest_once(ser)

                        close_old_connections()

                        time.sleep(interval)

                except (
                    serial.SerialException,
                    OSError,
                    RuntimeError,
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                ) as exc:

                    self.stderr.write(
                        self.style.ERROR(
                            f"Connection/read failed: {exc}"
                        )
                    )

                    if current_device:
                        self.set_state(
                            current_device,
                            active=False
                        )

                finally:
                    if ser and ser.is_open:
                        try:
                            ser.close()
                        except Exception:
                            pass

                    close_old_connections()

                self.stdout.write(
                    self.style.WARNING(
                        f"Retrying {port} in {reconnect_delay}s..."
                    )
                )

                time.sleep(reconnect_delay)

        except KeyboardInterrupt:
            self.stdout.write(
                self.style.WARNING(
                    "Stopping ingestion service"
                )
            )

            if current_device:
                self.set_state(
                    current_device,
                    active=False
                )

    def ingest_once(self, ser):
        ser.reset_input_buffer()

        ser.write(b"READ\n")
        ser.flush()

        line = ser.readline().decode("utf-8").strip()

        if not line:
            raise RuntimeError(
                "Arduino returned no data"
            )

        data = json.loads(line)

        device_id = data.pop("device_id")

        device, _ = Device.objects.get_or_create(
            device_id=device_id,
            units={
                "temperature_c": {
                    "name": "Temperature",
                    "unit": "°C",
                    "decimals": 2
                },
                "thermistor_ohms": {
                    "name": "Thermistor resistance",
                    "unit": "Ω",
                    "decimals": 0
                },
                "adc": {
                    "name": "ADC",
                    "unit": "",
                    "decimals": 0
                }
            }
        )

        self.set_state(
            device,
            active=True
        )

        Reading.objects.create(
            device=device,
            observed_at=timezone.now(),
            measurements=data
        )

        self.stdout.write(
            f"{device_id}: {data}"
        )

        return device

    def set_state(self, device, active):
        latest_state = (
            State.objects
            .filter(device=device)
            .order_by("-datetime")
            .first()
        )

        if latest_state is None or latest_state.active != active:
            State.objects.create(
                device=device,
                active=active
            )

            state_text = (
                "ACTIVE"
                if active
                else "INACTIVE"
            )

            self.stdout.write(
                self.style.WARNING(
                    f"{device.device_id} -> {state_text}"
                )
            )