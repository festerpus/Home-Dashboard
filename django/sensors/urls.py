from django.urls import path

from sensors import views

urlpatterns = [
    # path("", views.index, name="index")
    path("", views.all_sensors, name="all_sensors"),
    path("<str:identifier>/", views.single_sensor, name="single_sensor"),
    path("<str:identifier>/history/", views.sensor_history, name="single_sensor_history"),
]