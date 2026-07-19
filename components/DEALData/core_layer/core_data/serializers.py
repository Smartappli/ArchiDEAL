"""Serializers for the core layer API."""

from django.db import transaction
from rest_framework import serializers

from .models import Experiment, ObservedObject, Project


class ExperimentSerializer(serializers.ModelSerializer):
    """Serialize experiments and validate their related core entities."""

    id = serializers.UUIDField(source="experiment_id", read_only=True)
    project = serializers.PrimaryKeyRelatedField(
        source="experiment_project",
        queryset=Project.objects.all(),
    )
    observed_objects = serializers.PrimaryKeyRelatedField(
        source="experiment_observed_objects",
        many=True,
        queryset=ObservedObject.objects.all(),
    )

    class Meta:
        """Serializer metadata."""

        model = Experiment
        fields = (
            "id",
            "project",
            "observed_objects",
        )

    @transaction.atomic
    def create(self, validated_data):
        """Create an experiment and all of its validated object links."""
        observed_objects = validated_data.pop("experiment_observed_objects")
        experiment = Experiment.objects.create(**validated_data)
        experiment.experiment_observed_objects.set(observed_objects)
        return experiment

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update scalar fields and replace object links when supplied."""
        observed_objects = validated_data.pop(
            "experiment_observed_objects",
            serializers.empty,
        )
        experiment = super().update(instance, validated_data)
        if observed_objects is not serializers.empty:
            experiment.experiment_observed_objects.set(observed_objects)
        return experiment
