from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from django.test.client import RequestFactory

from apps.hosting.views import (
    AutoDiscoverView,
    HostedApplicationViewSet,
    ManagementAutoDiscoverView,
    ManagementInterfaceView,
    ModuleViewSet,
    ToolViewSet,
)


class HostingEventPublishingTests(SimpleTestCase):
    @patch("apps.hosting.views.publish_event")
    def test_module_perform_create_emits_event(self, publish_mock):
        serializer = Mock()
        serializer.save.return_value = SimpleNamespace(id=1, slug="core", enabled=True)

        ModuleViewSet().perform_create(serializer)

        publish_mock.assert_called_once()

    @patch("apps.hosting.views.publish_event")
    def test_module_perform_update_emits_event(self, publish_mock):
        serializer = Mock()
        serializer.save.return_value = SimpleNamespace(id=4, slug="core", enabled=False)

        ModuleViewSet().perform_update(serializer)

        publish_mock.assert_called_once()

    @patch("apps.hosting.views.publish_event")
    def test_module_perform_destroy_emits_event(self, publish_mock):
        instance = Mock(id=8, slug="core")
        view = ModuleViewSet()

        with patch(
            "rest_framework.viewsets.ModelViewSet.perform_destroy"
        ) as destroy_super:
            view.perform_destroy(instance)

        destroy_super.assert_called_once_with(instance)
        publish_mock.assert_called_once()

    @patch("apps.hosting.views.publish_event")
    def test_tool_perform_create_emits_event(self, publish_mock):
        serializer = Mock()
        serializer.save.return_value = SimpleNamespace(
            id=10, slug="catalog", enabled=True
        )

        ToolViewSet().perform_create(serializer)

        publish_mock.assert_called_once()

    @patch("apps.hosting.views.publish_event")
    def test_tool_perform_update_emits_event(self, publish_mock):
        serializer = Mock()
        serializer.save.return_value = SimpleNamespace(
            id=2,
            slug="catalog",
            enabled=False,
        )

        ToolViewSet().perform_update(serializer)

        publish_mock.assert_called_once()

    @patch("apps.hosting.views.publish_event")
    def test_tool_perform_destroy_emits_event(self, publish_mock):
        instance = Mock(id=9, slug="catalog")
        view = ToolViewSet()

        with patch(
            "rest_framework.viewsets.ModelViewSet.perform_destroy"
        ) as destroy_super:
            view.perform_destroy(instance)

        destroy_super.assert_called_once_with(instance)
        publish_mock.assert_called_once()

    @patch("apps.hosting.views.publish_event")
    def test_application_perform_destroy_emits_event(self, publish_mock):
        instance = Mock(id=3, slug="frontend")
        view = HostedApplicationViewSet()

        with patch(
            "rest_framework.viewsets.ModelViewSet.perform_destroy"
        ) as destroy_super:
            view.perform_destroy(instance)

        destroy_super.assert_called_once()
        publish_mock.assert_called_once()

    @patch("apps.hosting.views.publish_event")
    def test_application_perform_create_emits_event(self, publish_mock):
        serializer = Mock()
        serializer.save.return_value = SimpleNamespace(
            id=5, slug="storefront", enabled=True, revision=1
        )

        HostedApplicationViewSet().perform_create(serializer)

        publish_mock.assert_called_once()

    @patch("apps.hosting.views.publish_event")
    def test_application_perform_update_emits_event(self, publish_mock):
        serializer = Mock()
        serializer.instance = SimpleNamespace(revision=1)
        serializer.save.return_value = SimpleNamespace(
            id=6, slug="storefront", enabled=False, revision=2
        )

        HostedApplicationViewSet().perform_update(serializer)

        serializer.save.assert_called_once_with(revision=2)
        publish_mock.assert_called_once()

    @patch("rest_framework.viewsets.ModelViewSet.get_queryset")
    def test_module_get_queryset_filters_enabled_query_param(self, super_queryset):
        queryset = Mock()
        queryset.filter.return_value = "filtered"
        super_queryset.return_value = queryset
        view = ModuleViewSet()
        view.request = SimpleNamespace(query_params={"enabled": "TRUE"})

        result = view.get_queryset()

        self.assertEqual(result, "filtered")
        queryset.filter.assert_called_once_with(enabled=True)

    @patch("rest_framework.viewsets.ModelViewSet.get_queryset")
    def test_module_get_queryset_applies_repository_routing_filters(
        self,
        super_queryset,
    ):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.exclude.return_value = queryset
        super_queryset.return_value = queryset
        view = ModuleViewSet()
        view.request = SimpleNamespace(
            query_params={
                "repository": "Smartappli/DEALIoT",
                "deployment_target": "kubernetes",
                "has_public_route": "true",
            },
        )

        result = view.get_queryset()

        self.assertEqual(result, queryset)
        queryset.filter.assert_any_call(
            repository_owner="Smartappli",
            repository_name="DEALIoT",
        )
        queryset.filter.assert_any_call(deployment_target="kubernetes")
        queryset.filter.assert_any_call(upstream_port__isnull=False)
        queryset.exclude.assert_any_call(public_path="")
        queryset.exclude.assert_any_call(upstream_host="")

    @patch("rest_framework.viewsets.ModelViewSet.get_queryset")
    def test_tool_get_queryset_applies_all_filters(self, super_queryset):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.distinct.return_value = "distinct-queryset"
        super_queryset.return_value = queryset
        view = ToolViewSet()
        view.request = SimpleNamespace(
            query_params={
                "enabled": "false",
                "module_slug": "module-core",
                "current_version": "1.2.3",
            },
        )

        result = view.get_queryset()

        self.assertEqual(result, "distinct-queryset")
        queryset.filter.assert_any_call(enabled=False)
        queryset.filter.assert_any_call(modules__slug="module-core")
        queryset.filter.assert_any_call(current_version="1.2.3")
        queryset.distinct.assert_called_once()

    @patch("rest_framework.viewsets.ModelViewSet.get_queryset")
    def test_application_get_queryset_applies_all_filters(self, super_queryset):
        queryset = Mock()
        queryset.filter.return_value = queryset
        queryset.distinct.return_value = "distinct-queryset"
        super_queryset.return_value = queryset
        view = HostedApplicationViewSet()
        view.request = SimpleNamespace(
            query_params={
                "enabled": "true",
                "module_slug": "module-core",
                "current_version": "2.0.1",
            },
        )

        result = view.get_queryset()

        self.assertEqual(result, "distinct-queryset")
        queryset.filter.assert_any_call(enabled=True)
        queryset.filter.assert_any_call(modules__slug="module-core")
        queryset.filter.assert_any_call(current_version="2.0.1")
        queryset.distinct.assert_called_once()

    @patch("apps.hosting.views.ModuleAttachSerializer")
    def test_tool_attach_module_adds_module_and_returns_serialized_tool(
        self, serializer_class
    ):
        serializer_instance = Mock()
        serializer_instance.validated_data = {"module": "module-core"}
        serializer_class.return_value = serializer_instance
        tool = Mock()
        view = ToolViewSet()
        view.get_object = Mock(return_value=tool)
        view.get_serializer = Mock(return_value=SimpleNamespace(data={"slug": "tool"}))

        response = view.attach_module(SimpleNamespace(data={"module": 1}))

        serializer_class.assert_called_once_with(data={"module": 1})
        serializer_instance.is_valid.assert_called_once_with(raise_exception=True)
        tool.modules.add.assert_called_once_with("module-core")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"slug": "tool"})

    @patch("apps.hosting.views.ModuleSerializer")
    def test_tool_modules_returns_serialized_modules(self, module_serializer):
        tool = Mock()
        tool.modules.all.return_value = [SimpleNamespace(slug="module-core")]
        module_serializer.return_value = SimpleNamespace(data=[{"slug": "module-core"}])
        view = ToolViewSet()
        view.get_object = Mock(return_value=tool)

        response = view.modules(SimpleNamespace())

        module_serializer.assert_called_once_with(tool.modules.all(), many=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [{"slug": "module-core"}])

    @patch("apps.hosting.views.ModuleAttachSerializer")
    def test_tool_detach_module_removes_module(self, serializer_class):
        serializer_instance = Mock()
        serializer_instance.validated_data = {"module": "module-core"}
        serializer_class.return_value = serializer_instance
        tool = Mock()
        view = ToolViewSet()
        view.get_object = Mock(return_value=tool)
        view.get_serializer = Mock(return_value=SimpleNamespace(data={"slug": "tool"}))

        response = view.detach_module(SimpleNamespace(data={"module": 1}))

        serializer_class.assert_called_once_with(data={"module": 1})
        serializer_instance.is_valid.assert_called_once_with(raise_exception=True)
        tool.modules.remove.assert_called_once_with("module-core")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"slug": "tool"})

    @patch("apps.hosting.views.publish_event")
    @patch("apps.hosting.views.ToolVersionSerializer")
    @patch("apps.hosting.views.VersionCreateSerializer")
    @patch("apps.hosting.views.publish_immutable_version")
    def test_tool_versions_post_updates_current_version_and_publishes(
        self,
        publish_version_mock,
        version_create_serializer_cls,
        tool_version_serializer_cls,
        publish_mock,
    ):
        tool = Mock(id=7, slug="tool-slug")
        version_obj = SimpleNamespace(version="1.1.0")
        publish_version_mock.return_value = SimpleNamespace(
            resource=tool,
            version=version_obj,
            created=True,
        )
        serializer = Mock()
        serializer.validated_data = {
            "version": "1.1.0",
            "notes": "release notes",
            "source": "ci",
        }
        version_create_serializer_cls.return_value = serializer
        tool_version_serializer_cls.return_value = SimpleNamespace(
            data={"version": "1.1.0"}
        )
        view = ToolViewSet()
        view.get_object = Mock(return_value=tool)

        response = view.versions(
            SimpleNamespace(method="POST", data={"version": "1.1.0"})
        )

        serializer.is_valid.assert_called_once_with(raise_exception=True)
        publish_version_mock.assert_called_once_with(
            tool,
            serializer.validated_data,
        )
        publish_mock.assert_called_once()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, {"version": "1.1.0"})

    @patch("apps.hosting.views.ToolVersionSerializer")
    def test_tool_versions_get_returns_versions(self, serializer_cls):
        tool = Mock()
        tool.versions.all.return_value = ["v1"]
        serializer_cls.return_value = SimpleNamespace(data=[{"version": "1.0.0"}])
        view = ToolViewSet()
        view.get_object = Mock(return_value=tool)

        response = view.versions(SimpleNamespace(method="GET"))

        serializer_cls.assert_called_once_with(tool.versions.all(), many=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [{"version": "1.0.0"}])

    def test_application_detach_module_delegates_to_conditional_mutation(self):
        view = HostedApplicationViewSet()
        delegated_response = Mock()
        view._update_module_membership = Mock(return_value=delegated_response)
        request = SimpleNamespace(data={"module": 1})

        response = view.detach_module(request, pk="9")

        view._update_module_membership.assert_called_once_with(
            request,
            pk="9",
            attach=False,
        )
        self.assertIs(response, delegated_response)

    def test_application_attach_module_delegates_to_conditional_mutation(self):
        view = HostedApplicationViewSet()
        delegated_response = Mock()
        view._update_module_membership = Mock(return_value=delegated_response)
        request = SimpleNamespace(data={"module": 1})

        response = view.attach_module(request, pk="9")

        view._update_module_membership.assert_called_once_with(
            request,
            pk="9",
            attach=True,
        )
        self.assertIs(response, delegated_response)

    @patch("apps.hosting.views.ApplicationVersionSerializer")
    def test_application_versions_get_returns_versions(self, serializer_cls):
        application = Mock()
        application.versions.all.return_value = ["v1"]
        serializer_cls.return_value = SimpleNamespace(data=[{"version": "2.0.0"}])
        view = HostedApplicationViewSet()
        view.get_object = Mock(return_value=application)

        response = view.versions(SimpleNamespace(method="GET"))

        serializer_cls.assert_called_once_with(application.versions.all(), many=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [{"version": "2.0.0"}])

    @patch("apps.hosting.views.ModuleSerializer")
    def test_application_modules_returns_serialized_modules(self, module_serializer):
        application = Mock()
        application.modules.all.return_value = [SimpleNamespace(slug="module-core")]
        module_serializer.return_value = SimpleNamespace(data=[{"slug": "module-core"}])
        view = HostedApplicationViewSet()
        view.get_object = Mock(return_value=application)

        response = view.modules(SimpleNamespace())

        module_serializer.assert_called_once_with(application.modules.all(), many=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [{"slug": "module-core"}])

    @patch("apps.hosting.views.publish_event")
    @patch("apps.hosting.views.ApplicationVersionSerializer")
    @patch("apps.hosting.views.VersionCreateSerializer")
    @patch("apps.hosting.views.publish_immutable_version")
    def test_application_versions_post_updates_current_version_and_publishes(
        self,
        publish_version_mock,
        version_create_serializer_cls,
        application_version_serializer_cls,
        publish_mock,
    ):
        application = Mock(id=11, slug="storefront", revision=4)
        version_obj = SimpleNamespace(version="3.0.0")
        publish_version_mock.return_value = SimpleNamespace(
            resource=application,
            version=version_obj,
            created=True,
        )
        serializer = Mock()
        serializer.validated_data = {
            "version": "3.0.0",
            "notes": "release notes",
            "source": "manual",
        }
        version_create_serializer_cls.return_value = serializer
        application_version_serializer_cls.return_value = SimpleNamespace(
            data={"version": "3.0.0"}
        )
        view = HostedApplicationViewSet()
        view.get_object = Mock(return_value=application)

        response = view.versions(
            SimpleNamespace(
                method="POST",
                data={"version": "3.0.0"},
                headers={"If-Match": '"4"'},
            )
        )

        serializer.is_valid.assert_called_once_with(raise_exception=True)
        publish_version_mock.assert_called_once_with(
            application,
            serializer.validated_data,
            expected_revision=4,
        )
        publish_mock.assert_called_once()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, {"version": "3.0.0"})
        self.assertEqual(response["ETag"], '"4"')

    @patch("apps.hosting.views.auto_discover_tools_and_applications")
    def test_api_autodiscover_view_returns_report_dict(self, autodiscover):
        autodiscover.return_value = SimpleNamespace(
            errors=[],
            to_dict=lambda **kwargs: {"ok": kwargs},
        )
        view = AutoDiscoverView()

        response = view.post(SimpleNamespace())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"ok": {"include_errors": False}})

    @patch("apps.hosting.views.redirect")
    @patch("apps.hosting.views.messages.error")
    @patch("apps.hosting.views.messages.success")
    @patch("apps.hosting.views.auto_discover_tools_and_applications")
    def test_management_autodiscover_view_posts_messages_and_redirects(
        self,
        autodiscover,
        success_message,
        error_message,
        redirect_mock,
    ):
        report = SimpleNamespace(
            modules_created=0,
            modules_updated=0,
            tools_created=1,
            tools_updated=2,
            applications_created=3,
            applications_updated=4,
            tool_versions_created=5,
            application_versions_created=6,
            errors=["manifest parse error"],
            error_count=1,
        )
        autodiscover.return_value = report
        redirect_mock.return_value = "redirected"
        request = RequestFactory().post("/hosting/manage/autodiscover/")

        response = ManagementAutoDiscoverView().post(request)

        self.assertEqual(response, "redirected")
        success_message.assert_not_called()
        self.assertEqual(error_message.call_count, 2)
        error_message.assert_any_call(
            request,
            "Autodiscovery failed; no changes were applied.",
        )
        error_message.assert_any_call(
            request,
            "Autodiscovery failed; details are available in server logs.",
        )
        redirect_mock.assert_called_once_with("hosting-management")

    @patch("apps.hosting.views.Dataset")
    @patch("apps.hosting.views.HostedApplication")
    @patch("apps.hosting.views.Tool")
    @patch("apps.hosting.views.Module")
    @patch("django.views.generic.base.TemplateView.get_context_data")
    def test_management_interface_context_for_superuser(
        self,
        super_context_data,
        module_model,
        tool_model,
        hosted_application_model,
        dataset_model,
    ):
        super_context_data.return_value = {"existing": True}
        modules = Mock(name="modules")
        tools = Mock(name="tools")
        applications = Mock(name="applications")
        datasets = Mock(name="datasets")
        datasets_ordered = Mock(name="datasets_ordered")

        module_model.objects.all.return_value.order_by.return_value = modules
        tool_model.objects.prefetch_related.return_value.all.return_value.order_by.return_value = tools
        hosted_application_model.objects.prefetch_related.return_value.all.return_value.order_by.return_value = applications
        dataset_model.objects.prefetch_related.return_value.filter.return_value = (
            datasets
        )
        datasets.order_by.return_value = datasets_ordered

        request = SimpleNamespace(user=SimpleNamespace(is_superuser=True))
        view = ManagementInterfaceView()
        view.request = request

        context = view.get_context_data()

        datasets.filter.assert_not_called()
        self.assertEqual(context["existing"], True)
        self.assertEqual(context["modules"], modules)
        self.assertEqual(context["tools"], tools)
        self.assertEqual(context["applications"], applications)
        self.assertEqual(context["datasets"], datasets_ordered)
