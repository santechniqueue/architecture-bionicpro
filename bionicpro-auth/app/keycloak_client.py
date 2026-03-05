import base64
import hashlib
import json
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.models import TokenPayload, UserInfo


class KeycloakClient:
    def __init__(self, settings: Settings):
        self.settings = settings

        self.public_realm_base = (
            f"{self.settings.keycloak_public_base_url}/realms/{self.settings.keycloak_realm}"
        )
        self.internal_realm_base = (
            f"{self.settings.keycloak_internal_base_url}/realms/{self.settings.keycloak_realm}"
        )

        self.token_url = f"{self.internal_realm_base}/protocol/openid-connect/token"
        self.auth_url = f"{self.public_realm_base}/protocol/openid-connect/auth"
        self.logout_url = f"{self.internal_realm_base}/protocol/openid-connect/logout"
        self.userinfo_url = f"{self.internal_realm_base}/protocol/openid-connect/userinfo"

    @staticmethod
    def build_code_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("utf-8")

    @staticmethod
    def _decode_jwt_payload(token: str) -> dict:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")

        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        return json.loads(decoded.decode("utf-8"))

    def build_user_from_tokens(self, token_payload: TokenPayload) -> UserInfo:
        access_claims = self._decode_jwt_payload(token_payload.access_token)

        id_claims = {}
        if token_payload.id_token:
            try:
                id_claims = self._decode_jwt_payload(token_payload.id_token)
            except ValueError:
                id_claims = {}

        merged_claims = dict(access_claims)

        for key in (
            "sub",
            "preferred_username",
            "email",
            "given_name",
            "family_name",
            "realm_access",
        ):
            if id_claims.get(key) is not None:
                merged_claims[key] = id_claims[key]

        return UserInfo.model_validate(merged_claims)

    def build_authorization_url(
        self,
        redirect_uri: str,
        state: str,
        code_challenge: str,
    ) -> str:
        query = urlencode(
            {
                "client_id": self.settings.keycloak_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid profile email roles",
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{self.auth_url}?{query}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> TokenPayload:
        data = {
            "grant_type": "authorization_code",
            "client_id": self.settings.keycloak_client_id,
            "client_secret": self.settings.keycloak_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(self.token_url, data=data)
            response.raise_for_status()
            return TokenPayload.model_validate(response.json())

    async def refresh(self, refresh_token: str) -> TokenPayload:
        data = {
            "grant_type": "refresh_token",
            "client_id": self.settings.keycloak_client_id,
            "client_secret": self.settings.keycloak_client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(self.token_url, data=data)
            response.raise_for_status()
            return TokenPayload.model_validate(response.json())

    async def revoke(self, refresh_token: str) -> None:
        data = {
            "client_id": self.settings.keycloak_client_id,
            "client_secret": self.settings.keycloak_client_secret,
            "refresh_token": refresh_token,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(self.logout_url, data=data)

    async def userinfo(self, access_token: str) -> UserInfo:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(self.userinfo_url, headers=headers)
            response.raise_for_status()
            return UserInfo.model_validate(response.json())