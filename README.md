# Kong vLLM demo

## Installing Kong ingress controller

Following: https://developer.konghq.com/kubernetes-ingress-controller/install/#

Enable Gateway API:
```
kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.1/standard-install.yaml
kubectl apply -f gateway.yaml
```

Add the kong helm repo:
```
helm repo add kong https://charts.konghq.com
helm repo update
```

The kong ingress chart with default settings:
```
$ helm install kong kong/ingress -n kong
NAME: kong
LAST DEPLOYED: Tue Feb 24 08:39:54 2026
NAMESPACE: kong
STATUS: deployed
REVISION: 1
DESCRIPTION: Install complete
TEST SUITE: None
```

Check connectivity:
```
$ export PROXY_IP=$(kubectl get svc --namespace kong kong-gateway-proxy -o jsonpath='{range .status.loadBalancer.ingress[0]}{@.ip}{@.hostname}{end}')
curl -i $PROXY_IP
HTTP/1.1 404 Not Found
Date: Mon, 23 Feb 2026 19:40:30 GMT
Content-Type: application/json; charset=utf-8
Connection: keep-alive
Content-Length: 103
X-Kong-Response-Latency: 0
Server: kong/3.9.1
X-Kong-Request-Id: 7d10507e46077d600b9db12d993f8c0f

{
  "message":"no Route matched with those values",
  "request_id":"7d10507e46077d600b9db12d993f8c0f"
```

Deploy test service and verify:
```
kubectl apply -f echo/echo-service.yaml
kubectl apply -f echo/echo-ingress.yaml
curl "$PROXY_IP/echo" --no-progress-meter --fail-with-body
```

Output should look something like:
```
Welcome, you are connected to node uoa-drai-gpu-test-md-0-8xmh7-klhgr.
Running on Pod echo-bcf7f965b-tbrw4.
In namespace kong.
With IP address 192.168.161.105.
```

Note: echo service and ingress could be deleted now.

Add cluster issuer for kong (not shown here).

## Run vLLM service

Launch the vLLM service:
```
kubectl apply -f vllm-gptoss-service.yaml
```

## Setup access to vLLM via Kong

Add the key-auth plugin, which will enforce API key authentication:
```
kubectl apply -f kong-key-auth.yaml
```

Add the ai-proxy plugin:
```
kubectl apply -f kong-ai-proxy-vllm-gptoss-chat-completions.yaml
```

Add the ingress for the chat completions route (using key-auth and ai-proxy plugins):
```
kubectl apply -f kong-ingress-vllm-gptoss-chat-completions.yaml
```

Add the ingress for the models endpoint (just using key-auth plugin):
```
kubectl apply -f kong-ingress-vllm-gptoss-models.yaml
```

## Deploy the demo portal for creating API keys

Configure the portal secret and apply it:
```
kubectl apply -f portal-secrets.yaml
```

Deploy the portal:
```
kubectl apply -f portal.yaml
```

## Testing

- Get an API key from: https://portal.test.drai.auckland.ac.nz
- The chat completions endpoint is: https://llm.test.drai.auckland.ac.nz/v1/chat/completions
- The OpenAI compatible base url is: https://llm.test.drai.auckland.ac.nz/v1

Run the test (requires `uv`):

```
cd test
uv sync
export OPENAI_API_KEY=my-api-key
uv run python main.py
```
