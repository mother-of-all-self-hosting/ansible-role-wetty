#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Slavi Pantaleev
#
# SPDX-License-Identifier: AGPL-3.0-or-later

# Prints the tag that the currently checked out commit should be released as,
# or nothing at all if it does not warrant a release.
#
# Usage: bin/compute-next-tag.sh
#
# Tags look like `v<wetty version>-<release>`, which is what this repository
# has always published (v2.5-0, v2.5-1, v3.0.0-0, v3.0.0-1):
#
# - if defaults/main.yml points at a Wetty version that has never been
#   released, the release counter restarts at 0 (`v3.1.0-0`)
# - otherwise the counter is incremented (`v3.0.0-2`), but only if something
#   that actually affects the role has changed since the last release
#
# Determining the version from defaults/main.yml, rather than from the commit
# message of the pull request that got merged, makes the result independent of
# the order in which pull requests get merged, and lets any change to the role
# (bugfix, feature, dependency bump) release itself without a human tagging.
# The commit-message approach this replaced could only ever tag a commit
# authored by Renovate, so every hand-written change to the role sat
# unreleased until a dependency bump happened to come along and carry it.

set -euo pipefail

repository_path="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$repository_path"

defaults_path='defaults/main.yml'

# Paths that shape the behavior of the role for its consumers. A commit
# touching only other paths (a README fix, CI configuration, Molecule tests)
# does not change what a playbook run does, and releasing it would only create
# churn in the repositories that consume this role.
role_defining_paths=(
	'defaults'
	'meta'
	'tasks'
	'templates'
)

# Anchored on `wetty_version:` so that `wetty_container_image_tag`, which is
# `{{ wetty_version }}`, and `wetty_container_image`, which is built out of it,
# cannot be mistaken for it. This is the same literal that the `# renovate:`
# annotation above it points Renovate at, and it has to stay that way: a
# version moved into a Jinja expression would leave nothing here to read.
version="$(sed -nE 's|^wetty_version:[[:space:]]*(.+)$|\1|p' "$defaults_path" | head -n1)"

# Older revisions of this file quoted the version (`wetty_version: '2.5'`), so
# the quotes, an inline comment and any surrounding space all have to go.
version="${version%%#*}"
version="$(printf '%s' "$version" | tr -d "\"' 	")"

if [ -z "$version" ]; then
	echo >&2 "Could not determine the Wetty version from $defaults_path"
	exit 1
fi

# Wetty's own version is carried without a leading `v` (upstream's Git tags
# have one, its container image tags do not), but tolerate one so that a
# future change of convention does not produce a doubled prefix.
tag_prefix="v${version#v}-"

# Of all releases of this version, the highest release number. Sorted
# numerically, so that -10 is recognized as newer than -9.
last_release="$(git tag --list "${tag_prefix}*" | sed -e "s|^${tag_prefix}||" | grep -E '^[0-9]+$' | sort -n | tail -n1 || true)"

if [ -z "$last_release" ]; then
	echo >&2 "Version $version has never been released"
	echo "${tag_prefix}0"
	exit 0
fi

previous_tag="${tag_prefix}${last_release}"

if git diff --quiet "$previous_tag" HEAD -- "${role_defining_paths[@]}"; then
	echo >&2 "Nothing affecting the role has changed since $previous_tag"
	exit 0
fi

echo >&2 "The role has changed since $previous_tag"
echo "${tag_prefix}$((last_release + 1))"
