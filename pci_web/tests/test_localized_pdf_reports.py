import io

import pytest
from django.conf import settings
from django.urls import reverse
from pypdf import PdfReader

from tests.test_localized_pages import a_surveyed_road, a_user, an_analysed_project

pytestmark = pytest.mark.django_db


def pdf_text(client, url, language):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(url)
    assert response.status_code == 200
    reader = PdfReader(io.BytesIO(response.content))
    return " ".join(" ".join(page.extract_text() for page in reader.pages).split())


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", ["Road Condition Assessment Report", "Maintenance Recommendations", "Pothole"]),
        ("uz", ["Yo‘l holatini baholash hisoboti", "Ta’mirlash bo‘yicha tavsiyalar", "Chuqurcha"]),
        ("ru", ["Отчёт об оценке состояния дороги", "Рекомендации по ремонту", "Выбоина"]),
    ],
)
def test_session_report_is_written_in_the_chosen_language(client, django_user_model, language, expected):
    user = a_user(django_user_model)
    session = a_surveyed_road(user)
    client.force_login(user)

    text = pdf_text(client, reverse("sessions:pdf_report", args=[session.pk]), language)

    assert all(phrase in text for phrase in expected)


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", ["1 pothole detected"]),
        ("ru", ["Обнаружена 1 выбоина"]),
    ],
)
def test_session_report_recommends_pothole_repair_in_every_language(client, django_user_model, language, expected):
    user = a_user(django_user_model)
    session = a_surveyed_road(user)
    client.force_login(user)

    text = pdf_text(client, reverse("sessions:pdf_report", args=[session.pk]), language)

    assert all(phrase in text for phrase in expected)


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", ["Multi-Session Road Assessment Report", "Priority Roads for Maintenance"]),
        ("uz", ["Bir nechta sessiya bo‘yicha yo‘l holati hisoboti", "Ta’mirga muhtoj ustuvor yo‘llar"]),
        ("ru", ["Сводный отчёт о состоянии дорог", "Приоритетные дороги для ремонта"]),
    ],
)
def test_multi_session_report_is_written_in_the_chosen_language(client, django_user_model, language, expected):
    user = a_user(django_user_model)
    session = a_surveyed_road(user)
    client.force_login(user)

    text = pdf_text(client, reverse("sessions:multi_pdf_report") + f"?ids={session.pk}", language)

    assert all(phrase in text for phrase in expected)


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", ["PCI Assessment Report", "Very Poor"]),
        ("uz", ["PCI baholash hisoboti", "Juda yomon"]),
        ("ru", ["Отчёт об оценке PCI", "Очень плохое"]),
    ],
)
def test_project_report_is_written_in_the_chosen_language(client, django_user_model, settings, tmp_path, language, expected):
    settings.MEDIA_ROOT = str(tmp_path)
    user = a_user(django_user_model)
    project = an_analysed_project(user, tmp_path)
    client.force_login(user)

    text = pdf_text(client, reverse("analysis:export_pdf", args=[project.pk]), language)

    assert all(phrase in text for phrase in expected)
