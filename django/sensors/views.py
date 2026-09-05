from datetime import timedelta
from dateutil.relativedelta import relativedelta

from django.http import JsonResponse
from django.utils import timezone

from sensors.models import Device, Reading, State


class DeviceNotFound(Exception):
    pass


def sensor_latest(identifier):
    device = Device.from_identifier(identifier)

    if device is None:
        # raise Http404("Device not found")
        raise DeviceNotFound(f"Device '{identifier}' not found")

    latest_reading = (
        Reading.objects
        .filter(device=device)
        .order_by("-received_at")
        .first()
    )

    latest_state = (
        State.objects
        .filter(device=device)
        .order_by("-datetime")
        .first()
    )

    return {
        "device": device,
        "data": {
            "id": str(device.id),
            "device_id": device.device_id,
            "name": str(device),
            "active": latest_state.active if latest_state else None,
            "state_changed_at": latest_state.datetime.isoformat() if latest_state else None,
            "latest_reading_received_at": latest_reading.received_at.isoformat() if latest_reading else None,
            "latest_reading": latest_reading.measurements if latest_reading else None
        }
    }


def single_sensor(request, identifier):
    try:
        device_data = sensor_latest(identifier)

        return JsonResponse(device_data['data'], status=200)

    except DeviceNotFound as exc:
        return JsonResponse({
            "error": "device_not_found",
            "message": str(exc)
        }, status=404)

    except Exception as exc:
        return JsonResponse({
            "error": "internal_server_error",
            "message": str(exc)
        }, status=500)


def all_sensors(request):
    try:
        devices = Device.objects.all()

        return JsonResponse({
            "sensors": [sensor_latest(device.device_id)['data'] for device in devices]
        }, status=200)

    except Exception as exc:
        return JsonResponse({
            "error": "internal_server_error",
            "message": str(exc)
        }, status=500)


def sensor_history(request, identifier):

    # Identifier validation

    try:
        device_data = sensor_latest(identifier)

        device = device_data['device']
        data = device_data['data']

    except DeviceNotFound as exc:
        return JsonResponse({
            "error": "device_not_found",
            "message": str(exc)
        }, status=404)

    except Exception as exc:
        return JsonResponse({
            "error": "internal_server_error",
            "message": str(exc)
        }, status=500)


    # Parameters validation 

    def invalid_parameter_error(message):
        return JsonResponse({
            "error": "invalid_parameter",
            "message": message
        }, status=400)

    allowed_params = {
        "months",
        "weeks",
        "days",
        "hours",
        "minutes",
        "seconds"
    }

    unknown_params = set(request.GET.keys()) - allowed_params

    if unknown_params:
        return invalid_parameter_error(f"Unknown parameter(s): {', '.join(sorted(unknown_params))}")

    params = {
        "months": request.GET.get("months", "0"),
        "weeks": request.GET.get("weeks", "0"),
        "days": request.GET.get("days", "0"),
        "hours": request.GET.get("hours", "0"),
        "minutes": request.GET.get("minutes", "0"),
        "seconds": request.GET.get("seconds", "0")
    }

    if not request.GET:
        params['days'] = "1"

    for param, value in params.items():
        try:
            value = int(value)
        except ValueError:
            return invalid_parameter_error(f"'{param}' must be an integer")

        if value < 0:
            return invalid_parameter_error(f"'{param}' must be 0 or greater")

        params[param] = value

    # Using given parameters to calculate the date range

    since = (
        timezone.now()
        - relativedelta(months=params['months'])
        - timedelta(
            weeks=params['weeks'],
            days=params['days'],
            hours=params['hours'],
            minutes=params['minutes'],
            seconds=params['seconds']
        )
    )

    # Getting reading from device in date range 

    readings = (
        Reading.objects
        .filter(
            device=device,
            received_at__gte=since
        )
        .order_by("received_at")
    )

    data.pop("latest_reading", None)
    data['readings'] = [
        {
            "received_at": reading.received_at.isoformat(),
            "measurements": reading.measurements
        } for reading in readings
    ]

    return JsonResponse(data, status=200)