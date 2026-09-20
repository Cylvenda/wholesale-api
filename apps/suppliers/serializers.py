from config.serializers import BaseSerializer
from .models import Supplier


class SupplierSerializer(BaseSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "uuid", "name", "phone", "email", "address", "is_active", "created_at", ]
        read_only_fields = ["id", "uuid", "created_at", ]
