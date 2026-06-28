from django.conf import settings


def easy_branding(request):
    return {
        "easy_app_name": settings.EASY_APP_NAME,
        "easy_mfa_display_name": settings.EASY_MFA_DISPLAY_NAME,
    }
