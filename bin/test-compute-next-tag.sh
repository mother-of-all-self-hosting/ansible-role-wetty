#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Slavi Pantaleev
#
# SPDX-License-Identifier: AGPL-3.0-or-later

# Exercises bin/compute-next-tag.sh against throwaway git repositories.
#
# Usage: bin/test-compute-next-tag.sh
#
# Every scenario creates a repository in a temporary directory, gives it role
# files and a release history, and then replays a series of merges through the
# real script, tagging as it goes just like the autotag workflow does. This
# repository is never touched and no network access is needed.

set -euo pipefail

script_under_test="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/compute-next-tag.sh"

failures=0
workdir=''

cleanup() {
	cd /
	if [ -n "$workdir" ]; then
		rm -rf "$workdir"
		workdir=''
	fi
}

trap cleanup EXIT

# Starts a scenario with a repository at Wetty 3.0.0 which has already seen two
# releases of it (v3.0.0-0 and v3.0.0-1), plus the `v2.5-0` and `v2.5-1` tags
# this repository really carries from when the role pinned the two-component
# container tag `2.5`. Those must not be counted as releases of 3.0.0.
#
# The defaults file deliberately carries the traps this role's real one has:
# the `# renovate:` annotation sitting directly above the version, an image tag
# that is nothing but `{{ wetty_version }}`, and a full image reference built
# out of that in turn. None of those may be picked up as the version, and the
# annotation being there means that moving it off the leaf literal - which
# would quietly stop Renovate from ever bumping this role - shows up here.
scenario() {
	echo "$1"

	cleanup
	workdir="$(mktemp -d)"

	mkdir -p "$workdir/bin" "$workdir/defaults" "$workdir/tasks" "$workdir/templates"
	cp "$script_under_test" "$workdir/bin/"
	cd "$workdir"

	git init -q -b main .
	git config user.email 'test@example.com'
	git config user.name 'Test'
	git config commit.gpgsign false

	cat > defaults/main.yml <<-'YAML'
		# renovate: datasource=docker depName=ghcr.io/butlerx/wetty versioning=semver
		wetty_version: 3.0.0

		wetty_container_image: "{{ wetty_container_image_registry_prefix }}butlerx/wetty:{{ wetty_container_image_tag }}"
		wetty_container_image_tag: "{{ wetty_version }}"
	YAML
	printf 'placeholder\n' > tasks/main.yml
	printf 'placeholder\n' > templates/env.j2
	printf 'placeholder\n' > README.md

	git add -A
	git commit -qm 'Initial commit'

	local tag
	for tag in v2.5-0 v2.5-1 v3.0.0-0 v3.0.0-1; do
		git tag "$tag"
	done
}

# Applies a change, commits it, and tags whatever the script says it should be.
# Prints the tag, or nothing when the script decided against a release.
merge() {
	local change="$1" tag

	eval "$change"
	git add -A
	git commit -qm 'Merge'

	tag="$(bin/compute-next-tag.sh 2>/dev/null)"

	if [ -n "$tag" ]; then
		git tag "$tag"
	fi

	printf '%s' "$tag"
}

expect() {
	local description="$1" expected="$2" actual="$3"

	if [ "$actual" = "$expected" ]; then
		printf '  ok   | %s -> %s\n' "$description" "${actual:-no release}"
	else
		printf '  FAIL | %s -> expected %s, got %s\n' "$description" "${expected:-no release}" "${actual:-no release}"
		failures=$((failures + 1))
	fi
}

bump_version="sed -i 's|^wetty_version: 3.0.0|wetty_version: 3.1.0|' defaults/main.yml"
revert_version="sed -i 's|^wetty_version: 3.1.0|wetty_version: 3.0.0|' defaults/main.yml"
quote_version="sed -i 's|^wetty_version: 3.0.0|wetty_version: \"3.0.0\"|' defaults/main.yml"
edit_task="printf 'a task\n' >> tasks/main.yml"
edit_template="printf 'a line\n' >> templates/env.j2"
edit_readme="printf 'documentation\n' >> README.md"
edit_script="printf '# a comment\n' >> bin/compute-next-tag.sh"

# The two merge orders below apply the same updates and must each end up with
# every update released exactly once, whichever order they arrive in.

scenario 'A version bump merged before other role changes'
expect 'version bump' v3.1.0-0 "$(merge "$bump_version")"
expect 'task edit'    v3.1.0-1 "$(merge "$edit_task")"
expect 'template'     v3.1.0-2 "$(merge "$edit_template")"

scenario 'A version bump merged after other role changes'
expect 'task edit'    v3.0.0-2 "$(merge "$edit_task")"
expect 'version bump' v3.1.0-0 "$(merge "$bump_version")"

# `v2.5-0` and `v2.5-1` exist in every scenario, and are the shape this
# repository's own history has. A version read loosely enough to match them
# would continue the counter from there instead of from 3.0.0's own releases.
scenario 'The two-component tags this repository carries from the 2.5 era'
expect 'a task' v3.0.0-2 "$(merge "$edit_task")"

# The version used to be written quoted (`wetty_version: '2.5'`), and a hand
# edit could reintroduce the quotes at any time. Adding them is a change to
# defaults/main.yml and so does warrant a release - but of `3.0.0`, not of
# `"3.0.0"`. A script that took the quotes for part of the version would see a
# version that had never been released and restart the counter at 0.
scenario 'A quoted version'
expect 'quoting the version' v3.0.0-2 "$(merge "$quote_version")"
expect 'a task'              v3.0.0-3 "$(merge "$edit_task")"

scenario 'Commits that do not affect the role'
expect 'README'   ''        "$(merge "$edit_readme")"
expect 'a script' ''        "$(merge "$edit_script")"
expect 'a task'   v3.0.0-2  "$(merge "$edit_task")"

scenario 'Release numbers past 9'
for release_number in 2 3 4 5 6 7 8 9 10; do
	git tag "v3.0.0-$release_number"
done
expect 'a task' v3.0.0-11 "$(merge "$edit_task")"

scenario 'Reverting to an already released version'
merge "$bump_version" > /dev/null
# The role is now identical to what v3.0.0-1 already published, so there is
# nothing new to release.
expect 'a revert' ''        "$(merge "$revert_version")"

scenario 'Reverting to an already released version, with a change'
merge "$bump_version" > /dev/null
expect 'a revert' v3.0.0-2 "$(merge "$revert_version && $edit_task")"

if [ "$failures" -gt 0 ]; then
	echo >&2 "$failures scenario(s) behaved unexpectedly"
	exit 1
fi

echo 'All scenarios behaved as expected'
