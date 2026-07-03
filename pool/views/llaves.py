"""Vista de las llaves (bracket) del Mundial: árbol radial de dieciseisavos."""

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from pool.services.llaves import build_bracket
from pool.views.scope import with_quiniela
from pool.views.stages import _build_tabs


@login_required
@with_quiniela
def llaves_view(request: HttpRequest) -> HttpResponse:
    context = {
        "bracket": build_bracket(request.user, request.quiniela),
        "tabs": _build_tabs(request.quiniela),
    }
    return render(request, "llaves.html", context)
