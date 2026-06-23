# Red Hat OpenShift AI - Known Issues on OSD

This document tracks known issues and workarounds for deploying RHOAI on OpenShift Dedicated clusters.

---

## Issue 1: Gateway NetworkPolicy Blocked on OSD (RHOAI 3.4.1)

**Affected Versions:** RHOAI 3.4.0+, OpenShift Dedicated 4.x

**Symptom:**
```
DataScienceCluster status: Error
Reason: "gateway domain is missing for Dashboard; the Data Science Gateway may not be ready yet—check that GatewayConfig exists and its status reports a domain: GatewayConfig.Status.Domain is empty"

GatewayConfig error:
"admission webhook 'networkpolicies-validation.managed.openshift.io' denied the request: 
User 'system:serviceaccount:redhat-ods-operator:redhat-ods-operator-controller-manager' 
prevented from creating network policy that may impact default ingress, which is managed by Red Hat."
```

**Root Cause:**
RHOAI 3.4.x attempts to create a NetworkPolicy in the `openshift-ingress` namespace to secure the gateway auth proxy. OpenShift Dedicated's admission webhook blocks this for security reasons because OSD's ingress is SRE-managed.

**Impact:**
- DataScienceCluster fails to reconcile
- Dashboard and ModelRegistry components cannot deploy
- No console link created for OpenShift AI
- All components remain in "NotReady" state

---

## Solution: Disable NetworkPolicy in GatewayConfig (Recommended)

### Prerequisites
- RHOAI operator installed (any 3.4.x version)
- `cluster-admin` or equivalent permissions on OSD
- Service Mesh operator installed (should be present on OSD)

### Step 1: Verify the Issue

```bash
# Check DataScienceCluster status
oc get datasciencecluster default-dsc -n redhat-ods-applications

# Expected output:
# NAME          READY   REASON
# default-dsc   False   Error

# Check GatewayConfig status
oc get gatewayconfig default-gateway -o jsonpath='{.status.conditions[?(@.type=="Ready")]}'

# Expected: status: "False", message contains NetworkPolicy error
```

### Step 2: Apply the Proper Fix

Configure the GatewayConfig to **disable NetworkPolicy creation**. This is the **official/supported approach** for OSD deployments:

```bash
cat <<EOF | oc apply -f -
apiVersion: services.platform.opendatahub.io/v1alpha1
kind: GatewayConfig
metadata:
  name: default-gateway
spec:
  authProxyTimeout: 5s
  cookie:
    expire: 24h
    refresh: 1h
  certificate:
    type: OpenshiftDefaultIngress
  enableK8sTokenValidation: true
  ingressMode: OcpRoute
  verifyProviderCertificate: true
  networkPolicy:
    ingress:
      enabled: false
EOF
```

**The key setting:** `networkPolicy.ingress.enabled: false` tells RHOAI to skip creating the NetworkPolicy that OSD blocks.

**Output:**
```
gatewayconfig.services.platform.opendatahub.io/default-gateway configured
```

### Step 3: Verify the Fix

```bash
# Wait 30-60 seconds for reconciliation
sleep 30

# Check GatewayConfig status
oc get gatewayconfig default-gateway

# Expected output:
# NAME              READY   REASON
# default-gateway   True

# Check DataScienceCluster status
oc get datasciencecluster default-dsc

# Expected: READY should progress to True (may take 2-5 minutes)

# Check if pods are starting
oc get pods -n redhat-ods-applications

# Expected: Dashboard, ModelRegistry, and other component pods should be Running
```

### Step 4: Verify Console Link

```bash
# Check for the OpenShift AI application link
oc get consolelink rhodslink

# Expected output:
# NAME        TEXT                   URL
# rhodslink   Red Hat OpenShift AI   https://rh-ai.apps.<cluster-id>.openshiftapps.com/
```

### Step 5: Access OpenShift AI

1. Open your OpenShift Console
2. Click the **Application menu** (9-dot icon) in the top navigation bar
3. Click **"Red Hat OpenShift AI"**
4. You should be redirected to the RHOAI dashboard

---

## Alternative: Manual Workaround (Not Recommended)

<details>
<summary>Click to expand manual workaround (use only if the proper fix above doesn't work)</summary>

If the recommended fix above doesn't work for some reason, you can manually create the Route and patch the Gateway status:

```bash
# Create the missing Route
cat <<EOF | oc apply -f -
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: kube-auth-proxy
  namespace: openshift-ingress
spec:
  to:
    kind: Service
    name: kube-auth-proxy
  port:
    targetPort: 8443
  tls:
    termination: reencrypt
    insecureEdgeTerminationPolicy: Redirect
EOF

# Set the Gateway domain
ROUTE_HOST=$(oc get route kube-auth-proxy -n openshift-ingress -o jsonpath='{.spec.host}')
oc patch gatewayconfig default-gateway \
  --type=merge \
  --subresource=status \
  -p "{\"status\":{\"domain\":\"$ROUTE_HOST\"}}"
```

**Note:** This manual approach is a workaround and not officially supported. Use the recommended fix above instead.

</details>

---

## Verification Checklist

After applying the workaround:

- [ ] `oc get route kube-auth-proxy -n openshift-ingress` returns a valid route
- [ ] `oc get gatewayconfig default-gateway -o jsonpath='{.status.domain}'` returns a non-empty domain
- [ ] `oc get consolelink rhodslink` exists
- [ ] `oc get pods -n redhat-ods-applications` shows dashboard and other pods running
- [ ] OpenShift AI link appears in the Application menu
- [ ] Clicking the link opens the RHOAI dashboard (may take 5-10 minutes for all components to fully start)

---

## Post-Installation Notes

### Component Startup Time

After applying the fix, RHOAI components take **5-10 minutes** to fully start. Monitor progress:

```bash
# Watch DataScienceCluster status
watch oc get datasciencecluster default-dsc

# Watch component readiness
oc get dsc default-dsc -o jsonpath='{.status.conditions[?(@.type=="ComponentsReady")].message}'

# Watch pods
watch oc get pods -n redhat-ods-applications
```

### Expected Final State

When fully ready:
- `oc get dsc default-dsc` shows `READY: True`
- All component pods in `redhat-ods-applications` namespace are `Running`
- Dashboard is accessible via the console link

### Persistence

This workaround is **persistent** across operator restarts. The manually created Route will remain, and the GatewayConfig status will persist unless the GatewayConfig resource is deleted.

**If you delete the GatewayConfig:**
- It will be recreated automatically by DSCI
- You'll need to re-apply steps 3-4 (create Route + set domain)

**If you upgrade RHOAI:**
- Test the workaround on a non-production cluster first
- A future RHOAI version may resolve this OSD incompatibility

---

## Issue 2: Dashboard Replica Pending on Resource-Constrained Clusters

**Affected Versions:** RHOAI 3.4.x, OpenShift clusters with limited worker nodes

**Symptom:**
```
oc get pods -n redhat-ods-applications | grep dashboard
rhods-dashboard-xxxxx   9/9     Running   0          10m
rhods-dashboard-yyyyy   0/9     Pending   0          10m

Events: "0/11 nodes are available: Insufficient cpu, Insufficient memory"
```

**Root Cause:**
The `rhods-dashboard` Deployment requests 2 replicas for high availability, but small/demo clusters may only have resources for 1 replica.

**Impact:**
- **Minimal** - Dashboard works fine with 1 replica
- One pod remains Pending indefinitely
- DataScienceCluster may show `Ready: False` with reason "NotReady"
- All functionality is available despite the cosmetic error

**Solution:**

### Option 1: Accept the Pending Pod (Recommended for Dev/Demo)

The dashboard is **fully functional** with 1 replica. The pending pod is just the HA replica for production environments. For demo/development clusters, you can safely ignore it.

**Verify functionality:**
```bash
# Dashboard deployment is available
oc get deployment rhods-dashboard -n redhat-ods-applications

# Expected: READY 1/2, AVAILABLE 1

# Dashboard is accessible
oc get consolelink rhodslink -o jsonpath='{.spec.href}'
# Click the link - it should work
```

### Option 2: Scale Down to 1 Replica

Manually scale the dashboard to 1 replica to clear the pending pod warning:

```bash
oc scale deployment rhods-dashboard -n redhat-ods-applications --replicas=1
```

**Note:** The RHOAI operator may recreate the deployment with 2 replicas during reconciliation. If this happens, repeat the scale command or accept Option 1.

### Option 3: Add More Worker Nodes

If you need full HA for production:
- Request additional worker nodes for your OSD cluster
- Ensure nodes have sufficient CPU/memory for all RHOAI components

**Resource Requirements per Dashboard Pod:**
- CPU: ~200m-500m per container (9 containers)
- Memory: Varies by component

---

## Alternative: Disable Dashboard and ModelRegistry

If the workaround above doesn't work or you don't need the dashboard:

```bash
oc patch datasciencecluster default-dsc --type=merge -p '
spec:
  components:
    dashboard:
      managementState: Removed
    modelregistry:
      managementState: Removed
'
```

This allows other RHOAI components (Data Science Pipelines, KServe, Workbenches, etc.) to function without the Gateway dependency. You can access workbenches and notebooks directly via their Routes.

---

## Related Issues

- **Red Hat Internal:** This is a known incompatibility between RHOAI 3.4.x Gateway implementation and OSD's managed ingress restrictions
- **Upstream:** Similar issue reported in Open Data Hub when deployed on managed OpenShift environments

---

## References

- RHOAI Documentation: https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/3.4
- OpenShift Dedicated Restrictions: NetworkPolicy admission in `openshift-*` namespaces
- Related: `infrastructure/baseline/osd-hub-state.md` - OSD cluster baseline

---

**Last Updated:** 2026-06-22  
**Tested On:** OSD 4.21.5, RHOAI 3.4.1  
**Status:** Workaround verified working
