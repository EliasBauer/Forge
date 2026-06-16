from __future__ import annotations

import json

from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST


@csrf_exempt
@require_POST
def login_view(request: HttpRequest) -> JsonResponse:
    try:
        data: dict[str, str] = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Ungültige Anfrage."}, status=400
        )

    user = authenticate(
        request,
        username=data.get("username", ""),
        password=data.get("password", ""),
    )
    if user is None:
        return JsonResponse(
            {"success": False, "error": "Ungültige Anmeldedaten."}, status=401
        )

    auth_login(request, user)
    groups = list(user.groups.values_list("name", flat=True))
    return JsonResponse(
        {
            "success": True,
            "user": {
                "id": user.pk,
                "username": user.username,
                "groups": groups,
                "isStaff": user.is_staff,
            },
        }
    )


@csrf_exempt
@require_POST
def logout_view(request: HttpRequest) -> JsonResponse:
    auth_logout(request)
    return JsonResponse({"success": True})


@require_GET
def users_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return JsonResponse(None, safe=False, status=401)
    users = User.objects.filter(is_active=True, groups__name="Projektleiter").order_by(
        "username"
    )
    return JsonResponse(
        [{"id": u.pk, "username": u.username} for u in users], safe=False
    )


@require_GET
def current_user_view(request: HttpRequest) -> JsonResponse:
    if not request.user.is_authenticated:
        return JsonResponse(None, safe=False)
    groups = list(request.user.groups.values_list("name", flat=True))
    return JsonResponse(
        {
            "id": request.user.pk,
            "username": request.user.username,
            "groups": groups,
            "isStaff": request.user.is_staff,
        }
    )
