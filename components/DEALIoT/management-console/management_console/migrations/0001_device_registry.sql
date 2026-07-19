CREATE TABLE public.devices (
    device_id varchar(128) PRIMARY KEY,
    display_name varchar(160) NOT NULL,
    kind varchar(64) NOT NULL,
    status varchar(24) NOT NULL DEFAULT 'provisioning',
    mqtt_topic varchar(512),
    capabilities jsonb NOT NULL DEFAULT '[]'::jsonb,
    settings jsonb NOT NULL DEFAULT '{}'::jsonb,
    labels jsonb NOT NULL DEFAULT '{}'::jsonb,
    revision bigint NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    created_by varchar(255) NOT NULL,
    updated_by varchar(255) NOT NULL,
    CONSTRAINT devices_device_id_format CHECK (
        device_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
    ),
    CONSTRAINT devices_kind_format CHECK (kind ~ '^[a-z][a-z0-9_-]{0,63}$'),
    CONSTRAINT devices_status_valid CHECK (
        status IN ('provisioning', 'active', 'suspended', 'retired')
    ),
    CONSTRAINT devices_revision_positive CHECK (revision > 0),
    CONSTRAINT devices_retirement_consistent CHECK (
        (status = 'retired' AND retired_at IS NOT NULL)
        OR (status <> 'retired' AND retired_at IS NULL)
    )
);

CREATE INDEX devices_status_device_id_idx ON public.devices (status, device_id);
CREATE INDEX devices_kind_device_id_idx ON public.devices (kind, device_id);
CREATE INDEX devices_updated_at_idx ON public.devices (updated_at DESC);
