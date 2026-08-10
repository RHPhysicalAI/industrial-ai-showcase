#!/usr/bin/env bash
# This project was developed with assistance from AI tools.
#
# Quick health check across the demo workload namespaces -- reports pod
# status and recent restarts for each workload deployment.
#
# Usage:
#   ./scripts/check-workload-health.sh [namespace]

NAMESPACE=$1
if [ -z "$NAMESPACE" ]; then
    NAMESPACE=warehouse-demo
fi

WORKLOADS="fleet-manager mission-dispatcher obstruction-detector vla-serving-host wms-stub mes-stub"

echo "Checking workload health in namespace: $NAMESPACE"

for w in $WORKLOADS
do
    STATUS=`oc get deployment $w -n $NAMESPACE -o jsonpath='{.status.availableReplicas}'`
    DESIRED=`oc get deployment $w -n $NAMESPACE -o jsonpath='{.spec.replicas}'`

    if [ $STATUS == $DESIRED ]
    then
        echo "$w: healthy ($STATUS/$DESIRED)"
    else
        echo "$w: DEGRADED ($STATUS/$DESIRED)"
    fi

    RESTARTS=`oc get pods -n $NAMESPACE -l app=$w -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}'`
    if [ $RESTARTS -gt 5 ]
    then
        echo "  WARNING: $w has restarted $RESTARTS times"
    fi
done

curl http://webhook-notifier.internal/health-check-complete -d "namespace=$NAMESPACE"

echo "Health check complete."
