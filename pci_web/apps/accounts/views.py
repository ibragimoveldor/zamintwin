from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.urls import reverse

from .forms import LoginForm, CreateUserForm


@login_required
def index(request):
    error = ""
    success = ""
    form = CreateUserForm()

    if request.method == "POST":
        form = CreateUserForm(request.POST)
        username = request.POST.get("username", "")
        email = request.POST.get("email", "")

        if " " in username:
            error = "Username should not contain spaces"
        elif User.objects.filter(username=username).exists():
            error = "This username is already in use"
        elif User.objects.filter(email=email).exists():
            error = "This email is already in use"
        elif form.is_valid():
            user = form.save(commit=False)
            user.password = make_password(username)
            user.save()
            success = "User created successfully"
            form = CreateUserForm()

    context = {
        "accounts_list": User.objects.order_by("-date_joined"),
        "success": success,
        "error": error,
        "form": form,
    }
    return render(request, "accounts/index.html", context)


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("email")
        password = request.POST.get("pws")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            next_url = request.GET.get("next", "/")
            return redirect(next_url)

        return render(
            request,
            "accounts/login.html",
            {"form": LoginForm(), "login_error": "Invalid email or password."},
        )

    return render(request, "accounts/login.html", {"form": LoginForm()})


def logout_view(request):
    logout(request)
    return redirect(reverse("accounts:login"))
