# Runtime evidence

New host runs write to `data/runs` (ignored by Git). Kubernetes runs write to the
platform PVC at `/data`. Export selected evidence to `data/validation` for review;
never replace missing live results with historical fixtures.
