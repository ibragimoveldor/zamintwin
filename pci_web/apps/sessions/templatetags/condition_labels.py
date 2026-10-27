from django import template
from django.utils.translation import gettext_lazy as _, pgettext_lazy

register = template.Library()

RATING_LABELS = {
    "good": _("Good"),
    "satisfactory": _("Satisfactory"),
    "fair": _("Fair"),
    "poor": _("Poor"),
    "very_poor": _("Very Poor"),
    "serious": _("Serious"),
    "failed": pgettext_lazy("pavement condition", "Failed"),
}

SEVERITY_LABELS = {
    "critical": _("Critical"),
    "high": _("High"),
    "medium": _("Medium"),
    "low": _("Low"),
}


@register.filter
def rating_label(rating):
    return RATING_LABELS.get(rating, rating)


@register.filter
def severity_label(severity):
    return SEVERITY_LABELS.get(severity, severity)


PAVEMENT_CONDITION_LABELS = {
    "Not Damaged": _("Not Damaged"),
    "Good": _("Good"),
    "Satisfactory": _("Satisfactory"),
    "Fair": _("Fair"),
    "Poor": _("Poor"),
    "Very Poor": _("Very Poor"),
    "Serious": _("Serious"),
    "Failed": pgettext_lazy("pavement condition", "Failed"),
    "Serious / Failed": _("Serious / Failed"),
}


@register.filter
def pavement_condition_label(condition):
    return PAVEMENT_CONDITION_LABELS.get(condition, condition)
