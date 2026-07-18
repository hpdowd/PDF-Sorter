# Versioning policy

OCR File Sorter uses **semantic versioning: `MAJOR.MINOR.PATCH`** (e.g. `1.2.0`).
Releases are tagged `vMAJOR.MINOR.PATCH` and cut by bumping `__version__` in
`src/__init__.py` and merging to `main` (the GitHub Actions build publishes the
release for a version that hasn't been released yet).

Decide the bump from the highest-impact change in the release.

## MAJOR (`X.0.0`) — breaking changes
Bump when users must change something to keep working:
- Mapping JSON format changes that are **not** auto-migrated.
- Removing or renaming a feature, option, or setting people rely on.
- Moving mappings / template folders / settings in an incompatible way, or
  otherwise requiring a reconfigure, reinstall, or re-map.

## MINOR (`x.Y.0`) — new, backward-compatible functionality
Bump when you add capability without breaking existing use:
- New user-facing features or options (e.g. Deep Audit recursive scan).
- New settings that default to the previous behavior.
- Backward-compatible mapping-format additions (auto-migrated on load).

## PATCH (`x.y.Z`) — backward-compatible fixes only ("tertiary")
Bump for fixes with no new features and no behavior users must adapt to:
- Bug/crash fixes (e.g. the sorting crash, missing dialogs, installer repo
  slug, settings location, collision-safe moves, OCR channel handling).
- Build/CI/internal changes; documentation and typo fixes.

## Rule of thumb
Bump the tier of the single most-significant change and reset the lower tiers to
`0`. Any new feature makes a release at least **MINOR**; any breaking change
makes it **MAJOR** regardless of what else it contains.
