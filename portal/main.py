import os
import secrets

import httpx
from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from keycloak import KeycloakOpenID
import kubernetes


app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- CONFIGURATION (Load from Env Vars) ---
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "https://keycloak.example.com/auth/")
REALM = os.getenv("KEYCLOAK_REALM", "myrealm")
CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "portal-client")
CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "change-me")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")
NAMESPACE = "kai-test"
LITELLM_API_URL = os.getenv("LITELLM_API_URL", "http://litellm.localhost")
LITELLM_MASTER_KEY = os.getenv("LITELLM_MASTER_KEY", "dummy-master-key")

# Keycloak Setup
keycloak_openid = KeycloakOpenID(
    server_url=KEYCLOAK_URL,
    client_id=CLIENT_ID,
    realm_name=REALM,
    client_secret_key=CLIENT_SECRET
)

# kubernetes setup
# Load in-cluster config (works automatically inside the pod)
kubernetes.config.load_incluster_config()
k8s_custom_api = kubernetes.client.CustomObjectsApi()
k8s_core_api = kubernetes.client.CoreV1Api()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Show Login or Generate Key page based on session."""
    token = request.cookies.get("access_token")
    user_info = None
    existing_api_key = None

    if token:
        try:
            user_info = keycloak_openid.userinfo(token)
            user_id = user_info['sub']
            secret_name = f"apikey-{user_id}"

            # Check if user already has an API key
            try:
                existing_secret = k8s_core_api.read_namespaced_secret(secret_name, NAMESPACE)
                import base64
                existing_api_key = base64.b64decode(existing_secret.data['key']).decode('utf-8')
                # strip the leading "Bearer "
                existing_api_key = existing_api_key.removeprefix("Bearer ")
            except kubernetes.client.exceptions.ApiException as e:
                if e.status != 404:
                    raise
                # No existing key found

        except Exception:
            pass  # Token invalid/expired

    redirect_uri = f"{APP_URL}/callback"

    return templates.TemplateResponse("index.html", {
        "request": request, 
        "user": user_info,
        "existing_api_key": existing_api_key,
        "keycloak_login_url": keycloak_openid.auth_url(
            redirect_uri=redirect_uri,
            scope="email openid profile",
        ),
    })

@app.get("/callback")
async def callback(request: Request, code: str):
    """Handle Keycloak redirect, exchange code for token."""
    token = keycloak_openid.token(
        grant_type='authorization_code',
        code=code,
        redirect_uri=f"{APP_URL}/callback"
    )
    response = RedirectResponse(url="/")
    response.set_cookie(key="access_token", value=token['access_token'])
    return response

@app.post("/generate-key", response_class=HTMLResponse)
async def generate_key(request: Request):
    """Call Kong Admin API to create consumer and key."""
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse("/")

    try:
        user_info = keycloak_openid.userinfo(token)
        user_id = user_info['sub']  # Unique Keycloak ID
        username = user_info.get('preferred_username', user_id)
        email = user_info.get('email', '')
        print(f"generating key for user_id: {user_id}; username: {username}; email: {email}")

        # Check if user already has an API key
        secret_name = f"apikey-{user_id}"
        try:
            existing_secret = k8s_core_api.read_namespaced_secret(secret_name, NAMESPACE)
            import base64
            existing_api_key = base64.b64decode(existing_secret.data['key']).decode('utf-8')
            # Strip the leading "Bearer " to show just the key
            existing_api_key = existing_api_key.removeprefix("Bearer ")

            return templates.TemplateResponse("index.html", {
                "request": request, 
                "user": user_info, 
                "existing_api_key": existing_api_key,
                "message": "You already have an API key. Here it is:"
            })
        except kubernetes.client.exceptions.ApiException as e:
            if e.status != 404:
                raise
            # No existing key found, proceed to create one

        # TODO: what happens if the key and/or consumer already exist?
        # TODO: key name should have uuid and label should have name so can display in ui and delete, add multiple, etc

        # 1. Create the Secret for the API Key
        api_key_value = secrets.token_urlsafe(32)
        kong_username = f"user-{user_id}"

        secret_manifest = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": secret_name,
                "namespace": NAMESPACE,
                "labels": {
                    "konghq.com/credential": "key-auth",
                    "created-by": "api-portal",
                },
            },
            "stringData": {
                # openai apis expect a Bearer token in the Authorization header
                "key": f"Bearer {api_key_value}",
            },
        }
        k8s_core_api.create_namespaced_secret(NAMESPACE, secret_manifest)

        # 2. Create the KongConsumer CRD
        consumer_manifest = {
            "apiVersion": "configuration.konghq.com/v1",
            "kind": "KongConsumer",
            "metadata": {
                "name": kong_username,
                "namespace": NAMESPACE,
                "annotations": {
                    "kubernetes.io/ingress.class": "kong",
                    "keycloak/email": email,
                    "keycloak/username": username,
                    "keycloak/sub": user_id,
                }
            },
            "username": kong_username,
            "credentials": [secret_name],
        }
        try:
            k8s_custom_api.create_namespaced_custom_object(
                group="configuration.konghq.com",
                version="v1",
                namespace=NAMESPACE,
                plural="kongconsumers",
                body=consumer_manifest,
            )
        except kubernetes.client.exceptions.ApiException as e:
            if e.status == 400:  # Bad Request - consumer already exists
                # Update the existing consumer to reference the new secret
                try:
                    existing_consumer = k8s_custom_api.get_namespaced_custom_object(
                        group="configuration.konghq.com",
                        version="v1",
                        namespace=NAMESPACE,
                        plural="kongconsumers",
                        name=kong_username
                    )
                    
                    # Update the credentials list to include our new secret
                    if 'credentials' not in existing_consumer:
                        existing_consumer['credentials'] = []
                    
                    if secret_name not in existing_consumer['credentials']:
                        existing_consumer['credentials'].append(secret_name)
                    
                    # Update annotations with current user info
                    if 'metadata' not in existing_consumer:
                        existing_consumer['metadata'] = {}
                    if 'annotations' not in existing_consumer['metadata']:
                        existing_consumer['metadata']['annotations'] = {}
                    
                    existing_consumer['metadata']['annotations'].update({
                        "keycloak/email": email,
                        "keycloak/username": username,
                        "keycloak/sub": user_id,
                    })
                    
                    k8s_custom_api.patch_namespaced_custom_object(
                        group="configuration.konghq.com",
                        version="v1",
                        namespace=NAMESPACE,
                        plural="kongconsumers",
                        name=kong_username,
                        body=existing_consumer
                    )
                except Exception as update_error:
                    raise Exception(f"Failed to update existing consumer: {update_error}")
            else:
                raise  # Re-raise if it's not a 400 error
        
        # 3. Create LiteLLM User and Key
        try:
            with httpx.Client(base_url=LITELLM_API_URL) as client:
                headers = {"Authorization": f"Bearer {LITELLM_MASTER_KEY}"}

                # Check if user exists, create if not
                try:
                    client.get(f"/user/info?user_id={user_id}", headers=headers).raise_for_status()
                    print(f"LiteLLM user {user_id} already exists.")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        print(f"LiteLLM user {user_id} not found, creating...")
                        user_payload = {
                            "user_id": user_id,
                            "user_email": email,
                            "auto_create_key": False
                        }
                        response = client.post("/user/new", json=user_payload, headers=headers)
                        response.raise_for_status()
                    else:
                        raise

                # Check if key exists, create if not
                try:
                    client.get(f"/key/info?key={api_key_value}", headers=headers).raise_for_status()
                    print(f"LiteLLM key already exists for user {user_id}.")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        print(f"LiteLLM key for user {user_id} not found, creating...")
                        key_payload = {
                            "key": api_key_value,
                            "user_id": user_id
                        }
                        response = client.post("/key/generate", json=key_payload, headers=headers)
                        response.raise_for_status()
                        print(f"LiteLLM key created for user {user_id}.")
                    else:
                        raise

        except httpx.HTTPStatusError as e:
            # Clean up Kong resources if LiteLLM fails
            k8s_core_api.delete_namespaced_secret(secret_name, NAMESPACE)
            # k8s_custom_api.delete_namespaced_custom_object(...) # decide if we should delete the consumer
            raise Exception(f"Failed to create LiteLLM resources: {e.response.text}")
        except Exception as e:
            # Clean up Kong resources if LiteLLM fails
            k8s_core_api.delete_namespaced_secret(secret_name, NAMESPACE)
            raise Exception(f"An unexpected error occurred with LiteLLM: {e}")


        return templates.TemplateResponse("index.html", {
            "request": request, 
            "user": user_info, 
            "new_api_key": api_key_value,
        })

    except Exception as e:
        return templates.TemplateResponse("index.html", {
            "request": request, 
            "error": str(e)
        })

@app.get("/logout")
async def logout():
    response = RedirectResponse("/")
    response.delete_cookie("access_token")
    return response
