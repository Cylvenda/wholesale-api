from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from config.destroy import SafeDestroyMixin
from .models import User
from .serializers import UserCreateSerializer, UserSerializer


class UserViewSet(SafeDestroyMixin, viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("-date_joined")
    lookup_field = "uuid"
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer

        return UserSerializer

    def destroy_instance(self, instance):
        """A user keeps their own history, so nobody can delete themselves."""
        if instance == self.request.user:
            raise ValidationError(
                "You cannot delete the account you are signed in with."
            )
        super().destroy_instance(instance)

