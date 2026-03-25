# LiteLLM proxy

Install:

```
kubectl apply -f namespace.yaml
kubectl apply -f litellm-test-secret.yaml
helm install -n litellm -f values.yaml litellm ./litellm-helm-1.82.3.tgz
```

Output:

```
$ helm install -n litellm -f values.yaml litellm ./litellm-helm-1.82.3.tgz
NAME: litellm
LAST DEPLOYED: Tue Mar 24 20:39:27 2026
NAMESPACE: litellm
STATUS: deployed
REVISION: 1
DESCRIPTION: Install complete
NOTES:
1. Get the application URL by running these commands:
  https://litellm.test.drai.auckland.ac.nz/
PDB: disabled. Configure via .Values.pdb.*
```

Upgrade:

```
helm upgrade -n litellm -f values.yaml litellm ./litellm-helm-1.82.3.tgz
```
