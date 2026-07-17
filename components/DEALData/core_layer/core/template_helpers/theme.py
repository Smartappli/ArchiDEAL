"""Theme helpers used by authentication views."""


class TemplateHelper:
    """Resolve template layout names for view contexts."""

    @staticmethod
    def set_layout(layout_name, context):
        """Return the requested layout template name."""
        del context
        return layout_name
