from datetime import datetime, timezone
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.analysis.models import PCIResult
from apps.projects.models import Project
from apps.sessions.models import Detection, RoadSegment, Session

pytestmark = pytest.mark.django_db

SURVEY_TIME = datetime(2026, 5, 4, 9, 30, tzinfo=timezone.utc)


def a_user(django_user_model):
    return django_user_model.objects.create_user(username="surveyor", password="pw-123456")


def a_session(user, **overrides):
    return Session.objects.create(**{
        "user": user,
        "session_id": "S-001",
        "city": "Tashkent",
        "road_name": "Amir Temur",
        "status": Session.Status.READY,
        "start_time": SURVEY_TIME,
        "distance_km": 1.2,
        "avg_pci": 48.0,
        "condition_rating": "poor",
        "total_defects": 1,
        "defect_summary": {"D40": 1},
        **overrides,
    })


def a_segment(session):
    return RoadSegment.objects.create(
        session=session, segment_index=0, start_km=0, end_km=0.1,
        start_lat=41.31, start_lon=69.28, end_lat=41.32, end_lon=69.29,
        track_points=[[41.31, 69.28], [41.32, 69.29]], pci_score=48.0, condition_rating="poor",
    )


def a_detection(session):
    return Detection.objects.create(
        session=session, detection_seq=1, defect_type="D40", confidence=0.91, severity="critical",
        lat=41.31, lon=69.28, frame_number=10, timestamp=SURVEY_TIME, distance_km=0.05,
    )


def a_surveyed_road(user):
    session = a_session(user)
    a_segment(session)
    a_detection(session)
    return session


def an_analysed_project(user, media_root):
    project = Project.objects.create(user=user, name="Ring Road", status=Project.Status.COMPLETED)
    result_dir = Path(media_root) / project.slug / "result"
    result_dir.mkdir(parents=True)
    (result_dir / "tile_001.jpg").write_bytes(b"jpg")
    PCIResult.objects.create(project=project, image_name="tile_001", pci_rating=35, pavement_condition="Very Poor")
    return project


def page(client, url, language):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    response = client.get(url)
    assert response.status_code == 200
    return response.content.decode()


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", ["No projects yet"]), ("uz", ["Hozircha loyihalar yo‘q"]), ("ru", ["Проектов пока нет"])],
)
def test_project_list_is_localized(client, django_user_model, language, expected):
    client.force_login(a_user(django_user_model))

    content = page(client, reverse("projects:index"), language)

    assert all(text in content for text in expected)


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "Upload Images"), ("uz", "Rasmlarni yuklash"), ("ru", "Загрузить изображения")],
)
def test_project_upload_page_is_localized(client, django_user_model, language, expected):
    user = a_user(django_user_model)
    project = Project.objects.create(user=user, name="Ring Road")
    client.force_login(user)

    assert expected in page(client, reverse("projects:upload", args=[project.pk]), language)


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", ["Open Map", "Surveyed"]), ("uz", ["Xaritani ochish", "Tekshirilgan"]), ("ru", ["Открыть карту", "Обследовано"])],
)
def test_city_selector_is_localized(client, django_user_model, language, expected):
    user = a_user(django_user_model)
    a_surveyed_road(user)
    client.force_login(user)

    content = page(client, reverse("sessions:city_selector"), language)

    assert all(text in content for text in expected)


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", ["Network PCI", "1 defect<"]), ("uz", ["Tarmoq PCI", "1 ta nuqson"]), ("ru", ["PCI сети", "1 дефект<"])],
)
def test_network_map_is_localized(client, django_user_model, language, expected):
    user = a_user(django_user_model)
    a_surveyed_road(user)
    client.force_login(user)

    content = page(client, reverse("sessions:network_map"), language)

    assert all(text in content for text in expected)


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", ["Defect Breakdown", "Pothole", "Critical (1)"]),
        ("uz", ["Nuqsonlar tarkibi", "Chuqurcha", "Kritik (1)"]),
        ("ru", ["Структура дефектов", "Выбоина", "Критический (1)"]),
    ],
)
def test_session_detail_is_localized(client, django_user_model, language, expected):
    user = a_user(django_user_model)
    session = a_surveyed_road(user)
    client.force_login(user)

    content = page(client, reverse("sessions:detail", args=[session.pk]), language)

    assert all(text in content for text in expected)


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "Review 1 session"), ("uz", "1 ta sessiyani ko‘rib chiqish"), ("ru", "Просмотр 1 сессии")],
)
def test_multi_session_review_is_localized(client, django_user_model, language, expected):
    user = a_user(django_user_model)
    session = a_surveyed_road(user)
    client.force_login(user)

    assert expected in page(client, reverse("sessions:multi_review") + f"?ids={session.pk}", language)


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", ["Section Results", "Very Poor"]), ("uz", ["Uchastkalar natijalari", "Juda yomon"]), ("ru", ["Результаты по участкам", "Очень плохое"])],
)
def test_analysis_dashboard_is_localized(client, django_user_model, settings, tmp_path, language, expected):
    settings.MEDIA_ROOT = str(tmp_path)
    user = a_user(django_user_model)
    project = an_analysed_project(user, tmp_path)
    client.force_login(user)

    content = page(client, reverse("analysis:results", args=[project.pk]), language)

    assert all(text in content for text in expected)


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "Tile Detail"), ("uz", "Bo‘lak tafsilotlari"), ("ru", "Детали участка")],
)
def test_analysis_map_is_localized(client, django_user_model, settings, tmp_path, language, expected):
    settings.MEDIA_ROOT = str(tmp_path)
    user = a_user(django_user_model)
    project = an_analysed_project(user, tmp_path)
    client.force_login(user)

    assert expected in page(client, reverse("analysis:mapview", args=[project.pk]), language)


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "Create Account"), ("uz", "Hisob yaratish"), ("ru", "Создать учётную запись")],
)
def test_account_settings_are_localized(client, django_user_model, language, expected):
    client.force_login(a_user(django_user_model))

    assert expected in page(client, reverse("accounts:index"), language)


@pytest.mark.parametrize(
    ("language", "expected"),
    [("en", "System Reports."), ("uz", "Tizim hisobotlari."), ("ru", "Системные отчёты.")],
)
def test_reports_page_is_localized(client, django_user_model, language, expected):
    client.force_login(a_user(django_user_model))

    assert expected in page(client, reverse("reports:index"), language)


def test_verification_status_keeps_its_machine_name_in_every_language(client, django_user_model):
    user = a_user(django_user_model)
    session = a_surveyed_road(user)
    client.force_login(user)

    content = page(client, reverse("sessions:detail", args=[session.pk]), "ru")

    assert '"verification": "pending"' in content


def test_failed_project_and_failed_road_use_different_words(client, django_user_model):
    user = a_user(django_user_model)
    Project.objects.create(user=user, name="Broken run", status=Project.Status.FAILED)
    a_surveyed_road(user)
    client.force_login(user)

    projects = page(client, reverse("projects:index"), "uz")
    road_map = page(client, reverse("sessions:network_map"), "uz")

    assert "Muvaffaqiyatsiz" in projects
    assert "Yaroqsiz" in road_map
