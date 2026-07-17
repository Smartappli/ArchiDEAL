# Kafka production contract

`topics.yaml` is the provider-neutral source for topic capacity, retention, compaction, and
principal intent. A site-specific Terraform, managed-provider, or Strimzi module must translate
this contract without weakening replication, ISR, retention, or ACL settings.

Production reconciliation must run before application rollout and fail when an existing topic has
fewer partitions, a weaker durability setting, or an incompatible cleanup policy. ACL wildcard
syntax is intent only; map it to the provider's supported prefix resource pattern.
