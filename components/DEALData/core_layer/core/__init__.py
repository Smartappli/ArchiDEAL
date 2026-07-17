"""Core Django project package."""


class TemplateLayout:
    """Minimal layout initializer used by authentication templates."""

    @staticmethod
    def init(view, context):
        """Return the template context unchanged."""
        del view
        return context
