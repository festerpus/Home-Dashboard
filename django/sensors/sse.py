import json
import time

from django.http import StreamingHttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from sensors.models import DataStream, LocalStream, Reading


SSE_POLL_INTERVAL = 0.5
SSE_HEARTBEAT_INTERVAL = 15


def _reading_payload(reading):
    return {
        "id": str(reading.id),
        "stream_id": str(reading.stream_id),
        "observed_at": reading.observed_at.isoformat(),
        "received_at": reading.received_at.isoformat(),
        "measurements": reading.measurements,
    }


def _sse_event(event, data, event_id=None):
    """
    Format an SSE event.

    Example:

        id: abc123
        event: reading
        data: {"temperature": 23.4}

    """

    parts = []

    if event_id is not None:
        parts.append(f"id: {event_id}")

    if event:
        parts.append(f"event: {event}")

    parts.append(
        f"data: {json.dumps(data, separators=(',', ':'))}"
    )

    return "\n".join(parts) + "\n\n"


def _stream_readings(stream=None):
    """
    SSE generator.

    If stream is supplied, only readings for that DataStream
    are emitted.

    Otherwise all new readings are emitted.
    """

    # Only send readings created after this connection begins.
    cursor = timezone.now()

    last_heartbeat = time.monotonic()

    # Initial acknowledgement so EventSource knows we're alive.
    yield _sse_event(
        "connected",
        {
            "status": "ok",
            "stream_id": str(stream.id) if stream else None,
        },
    )

    while True:
        queryset = (
            Reading.objects
            .filter(received_at__gt=cursor)
            .select_related("stream")
            .order_by("received_at")
        )

        if stream is not None:
            queryset = queryset.filter(stream=stream)

        readings = list(queryset)

        for reading in readings:
            yield _sse_event(
                "reading",
                _reading_payload(reading),
                event_id=str(reading.id),
            )

            cursor = reading.received_at

        now = time.monotonic()

        if now - last_heartbeat >= SSE_HEARTBEAT_INTERVAL:
            # SSE comment - browser ignores it, but it keeps
            # the HTTP connection/proxies alive.
            yield ": heartbeat\n\n"

            last_heartbeat = now

        time.sleep(SSE_POLL_INTERVAL)


def _response(generator):
    response = StreamingHttpResponse(
        generator,
        content_type="text/event-stream",
    )

    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"

    return response


@require_GET
def all_events(request):
    """
    Subscribe to readings from every DataStream.
    """

    return _response(
        _stream_readings()
    )


@require_GET
def stream_events(request, stream_id):
    """
    Subscribe to one DataStream by UUID.
    """

    try:
        stream = DataStream.objects.get(id=stream_id)

    except DataStream.DoesNotExist:
        return JsonResponse({
            "error": "stream_not_found",
            "message": f"Data stream '{stream_id}' was not found",
        }, status=404)

    return _response(
        _stream_readings(stream)
    )


@require_GET
def local_events(request, device_id):
    """
    Convenience endpoint for a LocalStream/device_id.
    """

    try:
        local = (
            LocalStream.objects
            .select_related("stream")
            .get(device_id=device_id)
        )

    except LocalStream.DoesNotExist:
        return JsonResponse({
            "error": "device_not_found",
            "message": f"Device '{device_id}' was not found",
        }, status=404)

    return _response(
        _stream_readings(local.stream)
    )