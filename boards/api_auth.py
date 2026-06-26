from django.utils import timezone

from .models import AgentToken


class AgentTokenAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info.startswith("/api/v1/"):
            token = self._bearer_token(request)
            if token:
                agent_token = self._authenticate(token)
                if agent_token:
                    request.easy_api_user = agent_token.user
                    request.easy_agent_token = agent_token
                    request.csrf_processing_done = True
                    AgentToken.objects.filter(pk=agent_token.pk).update(last_used_at=timezone.now())
        return self.get_response(request)

    def _bearer_token(self, request):
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return ""
        return token.strip()

    def _authenticate(self, raw_token):
        prefix = raw_token[:12]
        candidates = AgentToken.objects.select_related("user").filter(token_prefix=prefix, is_active=True, user__is_active=True)
        for candidate in candidates:
            if not candidate.is_expired and candidate.matches(raw_token):
                return candidate
        return None
