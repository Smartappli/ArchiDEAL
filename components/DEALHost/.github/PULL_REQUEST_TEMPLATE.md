# Pull Request

## Summary

Describe the change and the reason it is needed.

## Validation

- [ ] `python manage.py test tests --verbosity 2 --settings=dealhost.settings.test`
- [ ] `python -m compileall dealhost apps tests`
- [ ] `pre-commit run --all-files`
- [ ] Not run, reason:

## Deployment Impact

- [ ] No database migration required
- [ ] No APISIX route change required
- [ ] No environment variable or secret change required
- [ ] Documentation updated where behavior changed

## Notes for Reviewers

Call out risks, tradeoffs, or files that need special attention.
