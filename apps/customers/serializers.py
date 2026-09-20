from config.serializers import BaseSerializer
from .models import Customer

class CustomerSerializer(BaseSerializer):
    class Meta:
        model = Customer
        fields = ["uuid", "name", "phone", "email", "business_location", "is_active", "created_at", ]
        read_only_fields = ["uuid", "created_at", ]
