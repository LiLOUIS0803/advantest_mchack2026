#!/bin/bash
set -eu
cd "$(dirname "$0")"
registry="${REGISTRY:-unifiedserver.local/grp4}"
version="${VERSION:-tasks-v6}"
image="$registry/py-app:$version"
docker build -f py-app.dockerfile -t "$image" .
docker push "$image"
printf 'Published %s\nUpdate the HC app_descriptor.json to this exact version.\n' "$image"
