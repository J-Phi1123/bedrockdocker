#!/bin/sh

# Script to build, push, and commit image

docker build -t jackclark1123/bedrockserver .
docker push jackclark1123/bedrockserver
git add .
git commit -m "Auto-build-`date`"
git push
