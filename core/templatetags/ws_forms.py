from django import template

register = template.Library()


@register.simple_tag
def ws_widget(bound_field, **attrs):
    """
    Render a form widget with the accessibility wiring the design system expects:
    aria-describedby points at the help text and every error message,
    and aria-invalid is set while the field has errors.
    """
    described_by = []
    if bound_field.help_text:
        described_by.append(f"{bound_field.auto_id}_help")
    for index, _ in enumerate(bound_field.errors):
        described_by.append(f"{bound_field.auto_id}_error{index or ''}")
    widget_attrs = {}
    if described_by:
        widget_attrs["aria-describedby"] = " ".join(described_by)
    if bound_field.errors:
        widget_attrs["aria-invalid"] = "true"
    widget_attrs.update(attrs)
    return bound_field.as_widget(attrs=widget_attrs)
