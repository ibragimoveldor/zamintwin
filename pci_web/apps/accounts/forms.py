from django.utils.translation import gettext_lazy as _
from django import forms
from django.contrib.auth.models import User


class LoginForm(forms.Form):
    email = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("Username")})
    )
    pws = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": _("Password")})
    )


class CreateUserForm(forms.ModelForm):
    nickname = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control"}), required=True
    )
    user_type = forms.ChoiceField(
        choices=[(0, _("Regular")), (1, _("Admin")), (2, _("Staff"))],
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = User
        fields = ["username", "email"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
        }
