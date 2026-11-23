from django.conf import settings


def outil(request):
    return {"formao_url": settings.FORMAO_URL if settings.FORMAO_URL else ""}
