# Pod in CrashLoopBackOff or OOMKilled

alerts: PodCrashLooping, ContainerOOMKilled, KubePodNotReady
owner: Platform-SRE

## Symptoms
Kubernetes restarts a container repeatedly. Restart count increases and the pod never becomes Ready.

## Likely causes
- Container exceeded its memory limit and was OOMKilled
- Bad configuration or missing secret after a deployment
- Failing liveness probe (probe too aggressive for slow start-up)
- Dependency unavailable at start-up and the app exits instead of retrying

## Diagnosis
- `kubectl describe pod <pod> -n <ns>` and look at Last State / Reason
- `kubectl logs <pod> -n <ns> --previous`
- `kubectl top pod -n <ns>` to compare memory usage with limits

## Remediation
1. Check the previous container logs with kubectl logs --previous to find the exit reason
2. If OOMKilled, raise the memory limit in the deployment by 25-50 percent and redeploy
3. If the crash started after a release, run kubectl rollout undo on the deployment
4. Relax the liveness probe initialDelaySeconds if the app is slow to start
5. kubectl delete namespace and recreate it from manifests if the namespace is corrupted
