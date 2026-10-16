# Help us check usability

Real engineer feedback has not yet been collected. Automated tests cannot establish that a new user understands the workflow.

Try these tasks using synthetic examples in a disposable local directory:

1. Follow the README source installation and run `doctor`.
2. Generate an offline `example`, then open its HTML `report`.
3. Use `guide` to plan a diagnosis without executing it.
4. Use `suggest` and explain which statements are evidence and which are possible causes.
5. Export a `handover` and identify the fields an engineer must complete.

Record the toolkit commit, OS/Python, task, approximate time, point of confusion, expected behavior and improvement. Success means completing the task and explaining its limits without undocumented help; do not grade only whether a command exits zero.

Use [the usability issue template](https://github.com/Vishnu063/devops_platform/issues/new?template=usability.yml). Keep feedback free of credentials, internal names, kubeconfigs and live report attachments. Maintainers can turn verified problems into small reproducible issues and document the fix.

No survey responses, satisfaction scores or external endorsements are claimed. This guide does not contact anyone or submit an issue automatically.
