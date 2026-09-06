from django.db import models
import uuid
import json


class DataStream(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, blank=True)
    added_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    metrics = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)

    def __str__(self):
        return self.name


# State for tracking data stream uptime
# class State(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     stream = models.ForeignKey(DataStream, on_delete=models.CASCADE)
#     active = models.BooleanField(default=False)
#     reason = models.CharField(max_length=200, blank=True)
#     datetime = models.DateTimeField(auto_now_add=True)

#     def _active(self):
#         return "active" if self.active else "inactive"

#     def __str__(self):
#         return f"{self.device} became {self._active()} @ {self.datetime}"


class LocalStream(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stream = models.OneToOneField(DataStream, on_delete=models.CASCADE, related_name="internal")
    device_id = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.stream.name or self.device_id


class ExternalStream(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stream = models.OneToOneField(DataStream, on_delete=models.CASCADE, related_name="external")
    provider = models.CharField(max_length=200, unique=True)

    def __str__(self):
            return self.stream.name or self.provider
    

class Reading(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stream = models.ForeignKey(DataStream, on_delete=models.CASCADE, related_name="readings")
    received_at = models.DateTimeField(auto_now_add=True)
    observed_at = models.DateTimeField()
    measurements = models.JSONField()

    def __str__(self):
        return f"{self.device} @ {self.received_at}"




# class Device(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)  # Unique ID in the DB
#     device_id = models.CharField(max_length=200, unique=True)                    # Unique ID of the Device
#     name = models.CharField(max_length=200, blank=True)                          # Clean name for display
#     added_on = models.DateTimeField(auto_now_add=True)
#     units = models.JSONField()                                                   # Formatting for measurements

#     def __str__(self):
#         return self.name or self.device_id

#     @classmethod
#     def from_identifier(cls, identifier):
#         try:
#             device_uuid = uuid.UUID(str(identifier))

#             device = cls.objects.filter(
#                 id=device_uuid
#             ).first()

#             if device:
#                 return device

#         except ValueError:
#             pass

#         return cls.objects.filter(
#             device_id=identifier
#         ).first()



# # State for tracking device uptime
# class State(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     device = models.ForeignKey(Device, on_delete=models.CASCADE)
#     active = models.BooleanField(default=False)
#     datetime = models.DateTimeField(auto_now_add=True)

#     def _active(self):
#         return "active" if self.active else "inactive"

#     def __str__(self):
#         return f"{self.device} became {self._active()} @ {self.datetime}"


