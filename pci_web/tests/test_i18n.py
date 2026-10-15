from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

pytestmark = pytest.mark.django_db

LOCALE_DIR = Path(settings.BASE_DIR) / "locale"


def visit(client, url, language=None):
    if language:
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    return client.get(url).content.decode()


def logged_in(client, django_user_model):
    user = django_user_model.objects.create_user(username="surveyor", password="pw-123456")
    client.force_login(user)
    return client


@pytest.mark.parametrize(
    ("language", "heading", "button"),
    [
        (None, "Welcome back", "Sign In"),
        ("en", "Welcome back", "Sign In"),
        ("uz", "Xush kelibsiz", "Kirish"),
        ("ru", "С возвращением", "Войти"),
    ],
)
def test_login_page_speaks_the_chosen_language(client, language, heading, button):
    page = visit(client, reverse("accounts:login"), language)

    assert heading in page
    assert button in page


def test_login_page_declares_its_language_on_the_html_element(client):
    page = visit(client, reverse("accounts:login"), "ru")

    assert '<html lang="ru"' in page


def test_failed_login_explains_the_error_in_the_chosen_language(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "uz"

    page = client.post(reverse("accounts:login"), {"email": "nobody", "pws": "wrong"}).content.decode()

    assert "Login yoki parol noto‘g‘ri." in page


def test_login_page_offers_all_three_languages(client):
    page = visit(client, reverse("accounts:login"))

    assert 'value="en"' in page
    assert 'value="uz"' in page
    assert 'value="ru"' in page


def test_choosing_a_language_is_remembered_for_later_pages(client):
    client.post(reverse("set_language"), {"language": "ru", "next": "/"})

    page = client.get(reverse("accounts:login")).content.decode()

    assert "С возвращением" in page


def test_unsupported_language_falls_back_to_english(client):
    page = visit(client, reverse("accounts:login"), "de")

    assert "Welcome back" in page


@pytest.mark.parametrize(
    ("language", "label"),
    [("en", "Road Inspection"), ("uz", "Yo‘llarni tekshirish"), ("ru", "Обследование дорог")],
)
def test_app_navigation_speaks_the_chosen_language(client, django_user_model, language, label):
    page = visit(logged_in(client, django_user_model), reverse("sessions:network_map"), language)

    assert label in page


@pytest.mark.parametrize("language", ["uz", "ru"])
def test_every_message_has_a_translation(language):
    catalog = (LOCALE_DIR / language / "LC_MESSAGES" / "django.po").read_text(encoding="utf-8")

    assert untranslated_entries(catalog) == []
    assert "#, fuzzy" not in catalog


def untranslated_entries(catalog):
    entries = catalog.split("\n\n")[1:]
    return [entry for entry in entries if entry.rstrip().endswith('msgstr ""')]
