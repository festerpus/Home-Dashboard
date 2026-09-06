from django.urls import path

from dashboard import views

urlpatterns = [
    path("", views.index, name="index"),
    path("streams/<uuid:stream_id>/", views.stream, name="stream")#
]