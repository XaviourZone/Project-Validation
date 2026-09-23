# Offline package bundle

Place the platform-specific Python wheels used by Validation in `wheels/`.

Prepare on an Internet-connected machine with:

```
python scripts/setup_dependencies.py --download
```

Then copy this `offline/` directory to the offline server.

Do not mix Windows/Linux or incompatible Python-version wheels in the bundle. Prepare the wheelhouse on the same target OS, CPU architecture and Python major/minor version.
