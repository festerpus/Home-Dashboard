from django.db import models
import uuid
import json

class Device(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # Unique ID in the DB
    device_id = models.CharField(max_length=200, unique=True)                    # Unique ID of the Device
    name = models.CharField(max_length=200, blank=True)                          # Clean name for display
    added_on = models.DateTimeField(auto_now_add=True)
    units = models.JSONField()                                                   # Formatting for measurements

    def __str__(self):
        return self.name or self.device_id

    @classmethod
    def from_identifier(cls, identifier):
        try:
            device_uuid = uuid.UUID(str(identifier))

            device = cls.objects.filter(
                id=device_uuid
            ).first()

            if device:
                return device

        except ValueError:
            pass

        return cls.objects.filter(
            device_id=identifier
        ).first()



# State for tracking device uptime
class State(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    active = models.BooleanField(default=False)
    datetime = models.DateTimeField(auto_now_add=True)

    def _active(self):
        return "active" if self.active else "inactive"

    def __str__(self):
        return f"{self.device} became {self._active()} @ {self.datetime}"


class Reading(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(Device, on_delete=models.CASCADE)
    received_at = models.DateTimeField(auto_now_add=True)
    observed_at = models.DateTimeField()
    measurements = models.JSONField()

    def __str__(self):
        return f"{self.device} @ {self.received_at}"