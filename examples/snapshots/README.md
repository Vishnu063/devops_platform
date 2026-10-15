# Sample incident snapshots

These files contain invented, illustrative data and image digests. They are not actual deployment results or usable images.

Run from the repository root:

```bash
python -m devops_toolkit compare examples/snapshots/before.json examples/snapshots/after.json
```

No cluster, kubectl, Docker or credentials are needed for comparison. The examples show a changed deployment image, fewer ready replicas, increased restarts and a warning. They do not establish what caused the failure.
