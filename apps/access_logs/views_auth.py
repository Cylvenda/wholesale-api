"""Sign-in endpoint that audits every attempt.

Replaces djoser's stock `TokenObtainPairView` so a successful login, a wrong
password and a login for an address that matches no account are all written to
the access log. The token response is unchanged, so the frontend needs no
changes to keep working.
"""

from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from apps.access_logs.models import AccessLog
from apps.access_logs.services import record, sync_last_login_ip

User = get_user_model()


def _issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class AuditedTokenObtainPairView(APIView):
    """POST {email, password} -> access/refresh, and an access log entry.

    JWT authentication is left enabled so a rejected sign-in answers 401 rather
    than DRF's 403: with no authenticator DRF has no `WWW-Authenticate` header to
    send and quietly downgrades the status.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        email = str(request.data.get("email") or request.data.get("username") or "").strip()
        password = str(request.data.get("password") or "")

        if not email or not password:
            record(
                AccessLog.Event.LOGIN_FAILURE,
                request=request,
                email=email,
                reason="Missing email or password",
            )
            return Response(
                {"detail": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request=request, username=email, password=password)

        if user is None:
            # A disabled account fails authentication the same way a wrong
            # password does, so the caller gets one uniform 401 and cannot tell
            # an address apart from a disabled one. The audit trail is where the
            # difference is recorded, so look the account up to label it.
            disabled = User.objects.filter(email__iexact=email).only("is_active").first()
            record(
                AccessLog.Event.LOGIN_FAILURE,
                request=request,
                user=None if disabled is None or disabled.is_active else disabled,
                email=email,
                reason=(
                    "Account is inactive"
                    if disabled is not None and not disabled.is_active
                    else "Incorrect email or password"
                ),
            )
            raise AuthenticationFailed("No active account found with the given credentials")

        entry = record(
            AccessLog.Event.LOGIN_SUCCESS,
            request=request,
            user=user,
            email=email,
        )
        sync_last_login_ip(user, request=request, ip_address=entry.ip_address if entry else None)
        # simplejwt's own bookkeeping, kept so `last_login` stays accurate.
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])

        return Response(_issue_tokens(user), status=status.HTTP_200_OK)


__all__ = ["AuditedTokenObtainPairView"]
