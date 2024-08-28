#!/bin/bash

./bin/kubectl run curl --image=curlimages/curl --rm=true --restart=Never -ti -- -X POST -v \
   -H "content-type: application/json"  \
   -H "ce-specversion: 1.0" \
   -H "ce-source: cli" \
   -H "ce-type: my.demo.event" \
   -H "ce-id: 1" \
   -d '{"details":"ChannelDemo"}' \
   http://ingress-to-one-kn-channel.chaining-test.svc.cluster.local
