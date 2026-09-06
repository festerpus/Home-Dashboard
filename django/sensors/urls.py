from django.urls import path

from sensors import views, sse

urlpatterns = [
    # path("", views.index, name="index")
    # path("", views.all_sensors, name="all_sensors"),
    # path("<str:identifier>/", views.single_sensor, name="single_sensor"),
    # path("<str:identifier>/history/", views.sensor_history, name="single_sensor_history"),
    path("send-message/", views.screen_message, name="send_message"),
    path("post-message/", views.post_message, name="post_message"),

    path("register-local/", views.register_local, name="register_local"),
    path("local-ingest/", views.local_ingest, name="local_ingest"),

    path("bulk-local-ingest/", views.bulk_local_ingest, name="bulk_local_ingest"),

    # SSE
    path("events/", sse.all_events, name="all_events"),
    path("streams/<uuid:stream_id>/events/", sse.stream_events, name="stream_events"),
    path("local/<str:device_id>/events/", sse.local_events, name="local_events"),

    path("streams/", views.all_streams, name="all_streams"),
    path("streams/<uuid:stream_id>/", views.single_stream,name="single_stream"),
    path("streams/<uuid:stream_id>/readings/", views.stream_readings, name="stream_readings"),

    # Local-device convenience API
    path("local/<str:device_id>/", views.local_stream, name="local_stream"),
    path("local/<str:device_id>/readings/", views.local_stream_readings, name="local_stream_readings"),
]