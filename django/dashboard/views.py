from django.shortcuts import render

def index(request):
    return render(request, "index.html", {})

def stream(request, stream_id):
    return render(request, "stream.html", {"stream_id": stream_id})