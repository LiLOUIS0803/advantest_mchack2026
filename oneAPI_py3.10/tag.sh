#!/bin/bash
#set -x
export DOCKER_BUILDKIT=0
orginame="py-app"
iname="py-app:latest"
registry="unifiedserver.local/grp4"
docker rmi $registry/$iname
docker build -f py-app.dockerfile . -t $registry/$iname
docker push $registry/$iname
docker rmi $registry/$iname
docker rmi unifiedserver.local/all/template-data-app:v22.04
