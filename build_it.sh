#!/bin/sh

# Script to build, push, and commit image
docker logout
docker login -u jackclark1123 -p d9bfa568-8669-4481-be26-aaf90074760d
docker build -t jackclark1123/bedrockserver .
docker push jackclark1123/bedrockserver
git add .
git commit -m "Auto-build-`date`"
git push
