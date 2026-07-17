# Pull Request

## Summary

Describe the change and the problem it solves.

## Type Of Change

- Runtime behavior
- Data model, migration, or ingestion contract
- Deployment or operations
- Documentation
- Security or compliance
- Community or adoption
- Test-only change

## Validation

List commands run and important manual checks.

```powershell
# example
.\.venv\Scripts\python.exe -m compileall -q core_layer gps_layer sensor_layer
```

## Operational Impact

Explain any change to secrets, deployment targets, data contracts, migrations, rollback, or support expectations.

## Checklist

- Tests or documentation updated where needed
- No secrets, private endpoints, customer data, or raw personal data committed
- Production image tags remain immutable where applicable
- README, support, or contributor docs updated when user-facing behavior changed
