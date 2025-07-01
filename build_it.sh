#!/bin/sh

# Script to build, push, and commit image
docker logout
docker login -u jackclark1123 -p `cat pass`
docker build -t jackclark1123/bedrockserver .
docker push jackclark1123/bedrockserver
docker logout
git add .
git commit -m "Auto-build-`date`"
git push
