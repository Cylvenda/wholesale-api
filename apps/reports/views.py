from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from .models import BusinessDetails, ReportSettings
from .serializers import BusinessDetailsSerializer, ReportSettingsSerializer
from .services import (
    build_purchases_excel,
    build_receipt_data,
    build_receipt_pdf,
    build_sales_excel,
    parse_report_date,
)
from ..sales.models import Sale


class BusinessDetailsViewSet(ModelViewSet):
    queryset = BusinessDetails.objects.select_related("created_by").order_by("-created_at")
    serializer_class = BusinessDetailsSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]


class ReportSettingsViewSet(ModelViewSet):
    queryset = ReportSettings.objects.select_related("created_by").order_by("-created_at")
    serializer_class = ReportSettingsSerializer
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"
    permission_classes = [IsAuthenticated]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_purchases_excel(request):
    from_date = parse_report_date(request.query_params.get("from"), "from")
    to_date = parse_report_date(request.query_params.get("to"), "to")

    return build_purchases_excel(
        from_date=from_date,
        to_date=to_date,
        product_uuid=request.query_params.get("product"),
        supplier_uuid=request.query_params.get("supplier"),
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def export_sales_excel(request):
    from_date = parse_report_date(request.query_params.get("from"), "from")
    to_date = parse_report_date(request.query_params.get("to"), "to")

    return build_sales_excel(
        from_date=from_date,
        to_date=to_date,
        product_uuid=request.query_params.get("product"),
        customer_uuid=request.query_params.get("customer"),
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sale_receipt(request, uuid):
    try:
        sale = (
            Sale.objects
            .select_related("customer", "created_by")
            .get(uuid=uuid)
        )
    except Sale.DoesNotExist as exc:
        raise NotFound("Sale not found.") from exc

    if sale.status != Sale.Status.COMPLETED:
        raise ValidationError("Only completed sales can generate receipts.")

    receipt = build_receipt_data(sale)
    if request.query_params.get("format") == "json":
        return Response({"success": True, "data": receipt}, status=status.HTTP_200_OK)

    response = HttpResponse(build_receipt_pdf(receipt).getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="receipt-{sale.uuid}.pdf"'
    )
    return response
