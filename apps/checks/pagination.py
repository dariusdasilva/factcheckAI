"""Pagination for the checks API — stable envelope for D's history/views."""

from rest_framework.pagination import PageNumberPagination


class CheckRunPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
