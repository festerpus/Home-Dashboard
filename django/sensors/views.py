from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from datetime import datetime
from django.utils import timezone
from django.conf import settings

from datetime import timedelta
from dateutil.relativedelta import relativedelta

import serial
import json
import time
import math
import secrets
import uuid

# from sensors.models import Device, Reading, State
from sensors.models import (
    DataStream,
    LocalStream,
    ExternalStream,
    Reading,
)

# class DeviceNotFound(Exception):
#     pass


def screen_message(request):
    return render(request, "screen_message.html", {})

@require_POST
def post_message(request):
    data = json.loads(request.body)

    ser = serial.Serial("COM5", 115200, timeout=3)

    ser.dtr = False
    ser.rts = False

    time.sleep(0.25)

    ser.write(f"{data['message']}\n".encode())
    ser.flush()

    return JsonResponse({"status":"ok"}, status=200)


"""
eps initially makes request on boot to register endpoint, checks if registered with current
up-to-date units, if not registered / up-to-date it updates, then just sends readings
"""

# API Key for devices, use one for all devices for now, will upgrade to bearer / whatever later on
# ESP32 should be hardcoded to send this api-key, if not req will be refused

def serialize_stream(stream, include_latest=True):
    """
    Convert a DataStream into the public API representation.
    """

    data = {
        "id": str(stream.id),
        "name": stream.name,
        "metrics": stream.metrics,
        "metadata": stream.metadata,
        "added_on": stream.added_on.isoformat(),
        "updated_on": stream.updated_on.isoformat(),
    }

    # Describe where this stream originates from
    try:
        data["source"] = {
            "type": "local",
            "device_id": stream.internal.device_id,
        }

        local = stream.internal

        last_seen_at = local.last_seen_at

        online = (
            last_seen_at is not None
            and timezone.now() - last_seen_at
            <= timedelta(
                seconds=settings.DEVICE_OFFLINE_AFTER_SECONDS
            )
        )
    except LocalStream.DoesNotExist:
        try:
            data["source"] = {
                "type": "external",
                "provider": stream.external.provider,
            }
        except ExternalStream.DoesNotExist:
            data["source"] = {
                "type": "unknown",
            }

    if include_latest:
        latest = (
            stream.readings
            .order_by("-observed_at")
            .first()
        )

        data["latest_reading"] = (
            {
                "id": str(latest.id),
                "observed_at": latest.observed_at.isoformat(),
                "received_at": latest.received_at.isoformat(),
                "measurements": latest.measurements,
            }
            if latest
            else None
        )

    data["state"] = {
        "status": "online" if online else "offline",
        "last_seen_at": (
            last_seen_at.isoformat()
            if last_seen_at
            else None
        ),
    }

    return data


def get_reading_range(request):
    """
    Parse relative time query parameters.

    Defaults to the last 24 hours.
    """

    allowed_params = {
        "months",
        "weeks",
        "days",
        "hours",
        "minutes",
        "seconds",
    }

    unknown = set(request.GET.keys()) - allowed_params

    if unknown:
        return None, JsonResponse({
            "error": "invalid_parameter",
            "message": (
                f"Unknown parameter(s): "
                f"{', '.join(sorted(unknown))}"
            )
        }, status=400)

    params = {
        "months": request.GET.get("months", "0"),
        "weeks": request.GET.get("weeks", "0"),
        "days": request.GET.get("days", "0"),
        "hours": request.GET.get("hours", "0"),
        "minutes": request.GET.get("minutes", "0"),
        "seconds": request.GET.get("seconds", "0"),
    }

    if not request.GET:
        params["days"] = "1"

    for key, value in params.items():
        try:
            value = int(value)
        except ValueError:
            return None, JsonResponse({
                "error": "invalid_parameter",
                "message": f"'{key}' must be an integer"
            }, status=400)

        if value < 0:
            return None, JsonResponse({
                "error": "invalid_parameter",
                "message": f"'{key}' must be 0 or greater"
            }, status=400)

        params[key] = value

    since = (
        timezone.now()
        - relativedelta(months=params["months"])
        - timedelta(
            weeks=params["weeks"],
            days=params["days"],
            hours=params["hours"],
            minutes=params["minutes"],
            seconds=params["seconds"],
        )
    )

    return since, None


@csrf_exempt
@require_POST
def register_local(request):
    """
        Expected data shape recieved from local device:

        {
            "device_id": "example-device-1",
            "metrics": {
                "temperature": {
                    "name": "Temperature",
                    "unit": "°C",
                    "decimals": 2
                }
                ...
            },
            "metadata": {
                ...
            }
        }
    """

    """
        Validation:
    """

    api_key = request.headers.get("X-API-Key")

    if api_key != settings.DEVICE_API_KEY:
        return JsonResponse({
            "error": "Unauthorized"
        }, status=401)

    # Checking obj is valid JSON
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Invalid JSON"},
            status=400
        )

    # Validate top-level structure
    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Body must be a JSON object"},
            status=400
        )

    # Ensuring required object fields are correct
    required_fields = {
        "device_id",
        "metrics"
    }

    if not required_fields.issubset(data):
        return JsonResponse(
            {"error": "Missing required fields"},
            status=400
        )

    # if metadata present validate it:
    if "metadata" in data and not isinstance(data["metadata"], dict):
        return JsonResponse(
            {"error": "metadata must be an object"},
            status=400
        )

    # Type checking
    if not isinstance(data["device_id"], str):
        return JsonResponse(
            {"error": "device_id must be a string"},
            status=400
        )

    if not isinstance(data["metrics"], dict):
        return JsonResponse(
            {"error": "metrics must be an object"},
            status=400
        )

    # Validate every metric
    for key, metric in data["metrics"].items():

        if not isinstance(metric, dict):
            return JsonResponse(
                {"error": f"Metric '{key}' must be an object"},
                status=400
            )

        if not {"name", "unit", "decimals"}.issubset(metric):
            return JsonResponse(
                {"error": f"Metric '{key}' is missing required fields"},
                status=400
            )

        if not isinstance(metric["name"], str):
            return JsonResponse(
                {"error": f"Metric '{key}'.name must be a string"},
                status=400
            )

        if not isinstance(metric["unit"], str):
            return JsonResponse(
                {"error": f"Metric '{key}'.unit must be a string"},
                status=400
            )

        if not isinstance(metric["decimals"], int):
            return JsonResponse(
                {"error": f"Metric '{key}'.decimals must be an integer"},
                status=400
            )

    # Payload is now structually valid:

    # Now we need to create a datastream with the metrics
    # and a localStream object to handle the device + metadata

    # Check if the local stream exists first, if it does, we need to check
    # if the datastream has the correct metrics and metadata, if it doesnt
    # we need to create the datastream then the localstream

    with transaction.atomic():
        metadata = data.get('metadata', {})

        if LocalStream.objects.filter(device_id=data['device_id']).exists():
            ls = LocalStream.objects.get(device_id=data['device_id'])
            ds = ls.stream

            ds.metrics = data['metrics']
            ds.metadata = metadata

            ds.save()

            ls.last_seen_at = timezone.now()
            ls.save()

            created = False
        else:
            ds = DataStream.objects.create(
                metrics = data['metrics'],
                metadata = metadata
            )

            ls = LocalStream.objects.create(
                device_id = data['device_id'],
                stream=ds,
            )

            ls.last_seen_at = timezone.now()
            ls.save()

            created = True

    return JsonResponse({
        "status": "ok",
        "created": created
    }, status=200)



@csrf_exempt
@require_POST
def local_ingest(request):

    """
        Expected data shape recieved from local device:

        {
            "device_id": "example-device-1",
            "timestamp": "2026-09-06T16:32:14Z",
            "readings": {
                "temperature": 12.34,
                ...
            }
        }
    """

    # Validation:

    api_key = request.headers.get("X-API-Key")
    
    if not api_key or not secrets.compare_digest(api_key, settings.DEVICE_API_KEY):
        return JsonResponse({
            "error": "Unauthorized"
        }, status=401)

    # Checking obj is valid JSON
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Invalid JSON"},
            status=400
        )

    # Validate top-level structure
    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Body must be a JSON object"},
            status=400
        )

    # Ensuring required object fields are correct
    required_fields = {
        "device_id",
        "timestamp",
        "readings"
    }

    if not required_fields.issubset(data):
        return JsonResponse(
            {"error": "Missing required fields"},
            status=400
        )

    if not isinstance(data["device_id"], str) or not data["device_id"].strip():
        return JsonResponse(
            {"error": "device_id must be a non-empty string"},
            status=400
        )

    if not isinstance(data["timestamp"], str):
        return JsonResponse(
            {"error": "timestamp must be a string"},
            status=400
        )

    try:
        timestamp = datetime.fromisoformat(
            data["timestamp"].replace("Z", "+00:00")
        )

        if timestamp.tzinfo is None:
            raise ValueError

    except (ValueError, TypeError):
        return JsonResponse(
            {"error": "timestamp must be a timezone-aware ISO 8601 datetime"},
            status=400
        )


    if not isinstance(data["readings"], dict):
        return JsonResponse(
            {"error": "readings must be an object"},
            status=400
        )

    if not data["readings"]:
        return JsonResponse(
            {"error": "readings must not be empty"},
            status=400
        )

    
    # Validate every metric
    for key, metric in data["readings"].items():

        if not isinstance(key, str) or not key.strip():
            return JsonResponse(
                {"error": "Reading keys must be non-empty strings"},
                status=400
            )

        if (
            isinstance(metric, bool)
            or not isinstance(metric, (int, float))
            or not math.isfinite(metric)
        ):
            return JsonResponse(
                {"error": f"Reading '{key}' must be a finite number"},
                status=400
            )

    # Create the reading assigned to the datastream

    # Get the datastream based on the localstream
    try:
        ls = LocalStream.objects.select_related("stream").get(
            device_id=data["device_id"]
        )
    except LocalStream.DoesNotExist:
        return JsonResponse(
            {"error": "Unknown device"},
            status=404
        )

    # Ensuring the metrics in readings match what we've registered

    registered_metrics = ls.stream.metrics

    for key in data["readings"]:
        if key not in registered_metrics:
            return JsonResponse(
                {"error": f"Unknown metric '{key}'"},
                status=400
            )

    Reading.objects.create(
        stream=ls.stream,
        observed_at = timestamp,
        measurements = data['readings']
    )

    ls.last_seen_at = timezone.now()
    ls.save()

    return JsonResponse({
        "status": "ok",
    }, status=200)


@csrf_exempt
@require_POST
def bulk_local_ingest(request):
    """
        Expected data shape recieved from local device:

        {
            "device_id": "example-device-1",
            "measurements": [
                {
                    "timestamp": "2026-09-06T16:32:14Z",
                    "readings": {
                        "temperature": 12.34,
                        ...
                    }
                },
                ...
            ]
        }
    """

    # Config

    MAX_BULK_READINGS = 1000

    # Validation:

    api_key = request.headers.get("X-API-Key")
    
    if not api_key or not secrets.compare_digest(api_key, settings.DEVICE_API_KEY):
        return JsonResponse({
            "error": "Unauthorized"
        }, status=401)

    # Checking obj is valid JSON
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Invalid JSON"},
            status=400
        )

    # Validate top-level structure
    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "Body must be a JSON object"},
            status=400
        )

    # Ensuring required object fields are correct
    required_fields = {
        "device_id",
        "measurements"
    }

    if not required_fields.issubset(data):
        return JsonResponse(
            {"error": "Missing required fields"},
            status=400
        )

    # Type checking
    if not isinstance(data["device_id"], str) or not data["device_id"].strip():
        return JsonResponse(
            {"error": "device_id must be a non-empty string"},
            status=400
        )

    if not isinstance(data['measurements'], list):
        return JsonResponse(
            {"error": "measurements must be an array (list)"},
            status=400
        )

    if not data["measurements"]:
        return JsonResponse(
            {"error": "measurements must not be empty"},
            status=400
        )

    if len(data["measurements"]) > MAX_BULK_READINGS:
        return JsonResponse(
            {
                "error": f"Maximum batch size is {MAX_BULK_READINGS}"
            },
            status=400
        )

    # Checking individual readings, if 1 malformed ditch all
    for index, reading in enumerate(data['measurements']):
        if not isinstance(reading, dict):
            return JsonResponse(
                {"error": f"reading {index}: must be a JSON object"},
                status=400
            )

        # Checking reading has correct fields
        required_measurement_fields = {
            "timestamp",
            "readings"
        }

        if not required_measurement_fields.issubset(reading):
            return JsonResponse(
                {"error": f"reading {index}: missing required fields"},
                status=400
            )

        # Type checking reading fields
        if not isinstance(reading["timestamp"], str):
            return JsonResponse(
                {"error": f"reading {index}: timestamp must be a string"},
                status=400
            )

        try:
            reading_timestamp = datetime.fromisoformat(
                reading["timestamp"].replace("Z", "+00:00")
            )

            if reading_timestamp.tzinfo is None:
                raise ValueError

        except (ValueError, TypeError):
            return JsonResponse(
                {"error": f"reading {index}: timestamp must be a timezone-aware ISO 8601 datetime"},
                status=400
            )

        if not isinstance(reading["readings"], dict):
            return JsonResponse(
                {"error": f"reading {index}: readings must be an object"},
                status=400
            )

        if not reading["readings"]:
            return JsonResponse(
                {"error": f"reading {index}: readings must not be empty"},
                status=400
            )

        # Validate every metric
        for key, metric in reading["readings"].items():

            if not isinstance(key, str) or not key.strip():
                return JsonResponse(
                    {"error": f"reading {index}: Reading keys must be non-empty strings"},
                    status=400
                )

            if (
                isinstance(metric, bool)
                or not isinstance(metric, (int, float))
                or not math.isfinite(metric)
            ):
                return JsonResponse(
                    {"error": f"reading {index}: Reading '{key}' must be a finite number"},
                    status=400
                )

    # Get the datastream based on the localstream
    try:
        ls = LocalStream.objects.select_related("stream").get(
            device_id=data["device_id"]
        )
    except LocalStream.DoesNotExist:
        return JsonResponse(
            {"error": "Unknown device"},
            status=404
        )

    registered_metrics = ls.stream.metrics

    readings_to_create = []

    for reading in data["measurements"]:

        # Check every supplied metric is registered
        for key in reading["readings"]:
            if key not in registered_metrics:
                return JsonResponse(
                    {"error": f"Unknown metric '{key}'"},
                    status=400
                )

        reading_timestamp = datetime.fromisoformat(
            reading["timestamp"].replace("Z", "+00:00")
        )

        readings_to_create.append(
            Reading(
                stream=ls.stream,
                observed_at=reading_timestamp,
                measurements=reading["readings"],
            )
        )

    with transaction.atomic():
        Reading.objects.bulk_create(readings_to_create)

    ls.last_seen_at = timezone.now()
    ls.save()

    return JsonResponse(
        {
            "status": "ok",
            "created": len(readings_to_create)
        },
        status=200
    )


@require_GET
def all_streams(request):
    streams = (
        DataStream.objects
        .select_related("internal", "external")
        .all()
    )

    return JsonResponse({
        "streams": [
            serialize_stream(stream)
            for stream in streams
        ]
    })


@require_GET
def single_stream(request, stream_id):
    try:
        stream = (
            DataStream.objects
            .select_related("internal", "external")
            .get(id=stream_id)
        )

    except (DataStream.DoesNotExist, ValueError):
        return JsonResponse({
            "error": "stream_not_found",
            "message": f"Data stream '{stream_id}' was not found"
        }, status=404)

    return JsonResponse(
        serialize_stream(stream),
        status=200
    )


@require_GET
def stream_readings(request, stream_id):
    try:
        stream = DataStream.objects.get(id=stream_id)

    except (DataStream.DoesNotExist, ValueError):
        return JsonResponse({
            "error": "stream_not_found",
            "message": f"Data stream '{stream_id}' was not found"
        }, status=404)

    since, error = get_reading_range(request)

    if error:
        return error

    readings = (
        Reading.objects
        .filter(
            stream=stream,
            observed_at__gte=since,
        )
        .order_by("observed_at")
    )

    return JsonResponse({
        "stream": serialize_stream(
            stream,
            include_latest=False,
        ),
        "from": since.isoformat(),
        "readings": [
            {
                "id": str(reading.id),
                "observed_at": reading.observed_at.isoformat(),
                "received_at": reading.received_at.isoformat(),
                "measurements": reading.measurements,
            }
            for reading in readings
        ],
    })


@require_GET
def local_stream(request, device_id):
    try:
        local = (
            LocalStream.objects
            .select_related("stream")
            .get(device_id=device_id)
        )

    except LocalStream.DoesNotExist:
        return JsonResponse({
            "error": "device_not_found",
            "message": f"Device '{device_id}' was not found"
        }, status=404)

    return JsonResponse(
        serialize_stream(local.stream),
        status=200
    )


@require_GET
def local_stream_readings(request, device_id):
    try:
        local = LocalStream.objects.get(
            device_id=device_id
        )

    except LocalStream.DoesNotExist:
        return JsonResponse({
            "error": "device_not_found",
            "message": f"Device '{device_id}' was not found"
        }, status=404)

    return stream_readings(
        request,
        local.stream.id,
    )

# @csrf_exempt
# @require_POST
# def local_ingest(request):
#     print(settings.DEVICE_API_KEY)



# @require_POST
# def local_ingest(request):
#     data = json.loads(request.body)

#     """
#         Expected data shape received from local device:
        
#         {
#             "device_id": "example-device-1",
#             "units": {
#                 "reading_1": {
#                     "name": "Temperature",
#                     "unit": "°C",
#                     "decimals": 2
#                 },
#                 ...
#             },
#             "readings": {
#                 "reading_1": 12.34,
#                 ...
#             }
#         }
#     """



# def sensor_latest(identifier):
#     device = Device.from_identifier(identifier)

#     if device is None:
#         # raise Http404("Device not found")
#         raise DeviceNotFound(f"Device '{identifier}' not found")

#     latest_reading = (
#         Reading.objects
#         .filter(device=device)
#         .order_by("-received_at")
#         .first()
#     )

#     latest_state = (
#         State.objects
#         .filter(device=device)
#         .order_by("-datetime")
#         .first()
#     )

#     return {
#         "device": device,
#         "data": {
#             "id": str(device.id),
#             "device_id": device.device_id,
#             "name": str(device),
#             "active": latest_state.active if latest_state else None,
#             "state_changed_at": latest_state.datetime.isoformat() if latest_state else None,
#             "latest_reading_received_at": latest_reading.received_at.isoformat() if latest_reading else None,
#             "latest_reading": latest_reading.measurements if latest_reading else None
#         }
#     }


# def single_sensor(request, identifier):
#     try:
#         device_data = sensor_latest(identifier)

#         return JsonResponse(device_data['data'], status=200)

#     except DeviceNotFound as exc:
#         return JsonResponse({
#             "error": "device_not_found",
#             "message": str(exc)
#         }, status=404)

#     except Exception as exc:
#         return JsonResponse({
#             "error": "internal_server_error",
#             "message": str(exc)
#         }, status=500)


# def all_sensors(request):
#     try:
#         devices = Device.objects.all()

#         return JsonResponse({
#             "sensors": [sensor_latest(device.device_id)['data'] for device in devices]
#         }, status=200)

#     except Exception as exc:
#         return JsonResponse({
#             "error": "internal_server_error",
#             "message": str(exc)
#         }, status=500)


# def sensor_history(request, identifier):

#     # Identifier validation

#     try:
#         device_data = sensor_latest(identifier)

#         device = device_data['device']
#         data = device_data['data']

#     except DeviceNotFound as exc:
#         return JsonResponse({
#             "error": "device_not_found",
#             "message": str(exc)
#         }, status=404)

#     except Exception as exc:
#         return JsonResponse({
#             "error": "internal_server_error",
#             "message": str(exc)
#         }, status=500)


#     # Parameters validation 

#     def invalid_parameter_error(message):
#         return JsonResponse({
#             "error": "invalid_parameter",
#             "message": message
#         }, status=400)

#     allowed_params = {
#         "months",
#         "weeks",
#         "days",
#         "hours",
#         "minutes",
#         "seconds"
#     }

#     unknown_params = set(request.GET.keys()) - allowed_params

#     if unknown_params:
#         return invalid_parameter_error(f"Unknown parameter(s): {', '.join(sorted(unknown_params))}")

#     params = {
#         "months": request.GET.get("months", "0"),
#         "weeks": request.GET.get("weeks", "0"),
#         "days": request.GET.get("days", "0"),
#         "hours": request.GET.get("hours", "0"),
#         "minutes": request.GET.get("minutes", "0"),
#         "seconds": request.GET.get("seconds", "0")
#     }

#     if not request.GET:
#         params['days'] = "1"

#     for param, value in params.items():
#         try:
#             value = int(value)
#         except ValueError:
#             return invalid_parameter_error(f"'{param}' must be an integer")

#         if value < 0:
#             return invalid_parameter_error(f"'{param}' must be 0 or greater")

#         params[param] = value

#     # Using given parameters to calculate the date range

#     since = (
#         timezone.now()
#         - relativedelta(months=params['months'])
#         - timedelta(
#             weeks=params['weeks'],
#             days=params['days'],
#             hours=params['hours'],
#             minutes=params['minutes'],
#             seconds=params['seconds']
#         )
#     )

#     # Getting reading from device in date range 

#     readings = (
#         Reading.objects
#         .filter(
#             device=device,
#             received_at__gte=since
#         )
#         .order_by("received_at")
#     )

#     data.pop("latest_reading", None)
#     data['readings'] = [
#         {
#             "received_at": reading.received_at.isoformat(),
#             "measurements": reading.measurements
#         } for reading in readings
#     ]

#     return JsonResponse(data, status=200)