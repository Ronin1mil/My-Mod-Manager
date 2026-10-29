#!/bin/sh
# Prints the release notes (or just the title) of one version from CHANGELOG.md.
#   release-notes.sh 0.5.1          the section: a short summary, then the details
#   release-notes.sh 0.5.1 title    the words after "## 0.5.1 - "
# Fails when the version has no section, so a release cannot go out without notes.
v="$1"
if [ "$2" = "title" ]; then
  t=$(grep -m1 "^## $v " CHANGELOG.md | sed 's/^## [^ ]* - //')
  [ -n "$t" ] || { echo "CHANGELOG.md has no section for $v" >&2; exit 1; }
  printf '%s\n' "$t"
  exit 0
fi
notes=$(awk -v h="## $v " 'index($0,h)==1{p=1;next} /^## /{p=0} p' CHANGELOG.md | sed -e '/./,$!d')
[ -n "$notes" ] || { echo "CHANGELOG.md has no section for $v" >&2; exit 1; }
printf '%s\n' "$notes"
