import base64
import json
import logging
import os
import secrets
import urllib.parse
import hashlib
import re
import httpx
import jwt as pyjwt
from jwt import PyJWKClient
from cryptography.fernet import Fernet
from govbr_auth.core.config import GovBrConfig

__all__ = ["GovBrAuthorize", "GovBrIntegration",
           "GovBrException", "GovBrAuthenticationError"]

logger = logging.getLogger(__name__)


# exceptions
class GovBrException(Exception):
    """
    Custom exception for Gov.br related errors.
    """
    pass


class GovBrAuthenticationError(GovBrException):
    """
    Custom exception for Gov.br authentication errors.
    """
    pass


class GovBrAuthorize:
    def __init__(self,
                 config: GovBrConfig):
        self.config = config

    def __generate_codes(self):
        code_verifier = base64.urlsafe_b64encode(os.urandom(80)).decode('utf-8')
        code_verifier = re.sub('[^a-zA-Z0-9]+', '', code_verifier)
        code_challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge_bytes).decode('utf-8').replace('=', '')
        fernet = Fernet(self.config.cript_verifier_secret.encode('utf-8'))
        encrypted_verifier = fernet.encrypt(code_verifier.encode('utf-8')).decode('utf-8')
        return encrypted_verifier, code_challenge

    def build_authorize_url(self) -> dict:
        try:
            encrypted_verifier, code_challenge = self.__generate_codes()
            nonce = secrets.token_urlsafe(32)
            encoded_redirect_uri = urllib.parse.quote_plus(self.config.redirect_uri)
            url = (
                f"{self.config.govbr_auth_url}?response_type={self.config.response_type}"
                f"&client_id={self.config.client_id}"
                f"&scope={self.config.scope}"
                f"&redirect_uri={encoded_redirect_uri}"
                f"&nonce={nonce}"
                f"&state={encrypted_verifier}"
                f"&code_challenge={code_challenge}"
                f"&code_challenge_method={self.config.code_challenge_method}"
            )
            return {"url": url}
        except Exception as e:
            return {"error": f"Failed to build authorize URL: {str(e)}"}

    def build_authorize_url_sync(self) -> dict:
        return self.build_authorize_url()


class GovBrIntegration:
    # JWKS endpoint for Gov.br production and staging
    _GOVBR_JWKS_URLS = {
        "https://sso.acesso.gov.br": "https://sso.acesso.gov.br/jwk",
        "https://sso.staging.acesso.gov.br": "https://sso.staging.acesso.gov.br/jwk",
    }

    def __init__(self,
                 config: GovBrConfig):
        self.config = config
        self._jwks_client = None

    def _get_jwks_client(self) -> PyJWKClient:
        """Get or create a cached JWKS client for the configured Gov.br issuer."""
        if self._jwks_client is None:
            jwks_url = self._resolve_jwks_url()
            if jwks_url:
                self._jwks_client = PyJWKClient(jwks_url)
        return self._jwks_client

    def _resolve_jwks_url(self) -> str:
        """Resolve the JWKS URL from the configured token URL."""
        for issuer, jwks_url in self._GOVBR_JWKS_URLS.items():
            if self.config.govbr_token_url.startswith(issuer):
                return jwks_url
        return None

    def __decrypt_code_verifier(self,
                                encrypted_verifier: str) -> str:
        try:
            secret_key = self.config.cript_verifier_secret.encode('utf-8')
            fernet = Fernet(secret_key)
            decrypted_bytes = fernet.decrypt(encrypted_verifier.encode('utf-8'))
            return decrypted_bytes.decode("utf-8")
        except Exception:
            raise ValueError("Invalid or missing code_verifier")

    def jwt_payload_decode(self,
                           id_token: str,
                           verify: bool = True) -> dict:
        """
        Decode and verify the JWT id_token.

        For Gov.br production/staging, the token signature is verified using
        the JWKS endpoint (RSA public keys). For local/fake environments,
        verification uses the configured jwt_secret (HS256) or falls back
        to unverified decode.

        Args:
            id_token: The JWT id_token string.
            verify: Whether to verify the signature (default: True).

        Returns:
            Decoded token payload as dict.

        Raises:
            GovBrAuthenticationError: If verification fails.
        """
        if not verify:
            return pyjwt.decode(id_token, options={"verify_signature": False})

        # Try JWKS verification (Gov.br production/staging)
        jwks_client = self._get_jwks_client()
        if jwks_client:
            try:
                signing_key = jwks_client.get_signing_key_from_jwt(id_token)
                return pyjwt.decode(
                    id_token,
                    signing_key.key,
                    algorithms=["RS256", "RS384", "RS512"],
                    audience=self.config.client_id,
                    options={"verify_exp": True, "verify_aud": True},
                )
            except pyjwt.exceptions.PyJWTError as e:
                raise GovBrAuthenticationError(
                    f"JWT signature verification failed: {e}"
                )

        # Fallback for local/fake mode: use configured jwt_secret
        if self.config.jwt_secret:
            try:
                return pyjwt.decode(
                    id_token,
                    self.config.jwt_secret,
                    algorithms=[self.config.jwt_algorithm],
                    options={"verify_exp": True},
                )
            except pyjwt.exceptions.PyJWTError as e:
                raise GovBrAuthenticationError(
                    f"JWT verification failed with configured secret: {e}"
                )

        # Last resort: unverified decode (fake mode without jwt_secret)
        logger.warning(
            "JWT signature verification skipped: no JWKS endpoint or jwt_secret configured. "
            "This is only acceptable in local development."
        )
        return pyjwt.decode(id_token, options={"verify_signature": False})

    async def async_exchange_code_for_token(self,
                                            code: str,
                                            state: str) -> dict:

        data, headers = self.__make_request_for_token(code, state)
        return await self.__exchange_async(data, headers)

    def exchange_code_for_token_sync(self,
                                     code: str,
                                     state: str) -> dict:
        data, headers = self.__make_request_for_token(code, state)
        return self.__exchange_sync(data, headers)

    def __make_request_for_token(self,
                                 code: str,
                                 state: str):
        if not self.config.client_id or not self.config.client_secret:
            return {"error": "Necessário informar client_id e client_secret"}

        code_verifier = self.__decrypt_code_verifier(state)
        if code_verifier is None:
            return {"error": "Código de verificação inválido"}

        data = {
            "grant_type":    "authorization_code",
            "code":          code,
            "redirect_uri":  self.config.redirect_uri,
            "code_verifier": code_verifier,
        }

        client_credential = base64.b64encode(
                f"{self.config.client_id}:{self.config.client_secret}".encode('ascii')).decode('ascii')
        headers = {
            "Content-Type":  "application/x-www-form-urlencoded",
            "Authorization": f"Basic {client_credential}",
        }

        return data, headers

    async def __exchange_async(self,
                               data: dict,
                               headers: dict) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.config.govbr_token_url, data=data, headers=headers, follow_redirects=False,
                                     timeout=10)
        return self.__parse_response(resp)

    def __exchange_sync(self,
                        data: dict,
                        headers: dict) -> dict:
        with httpx.Client() as client:
            resp = client.post(self.config.govbr_token_url, data=data, headers=headers, follow_redirects=False, timeout=10)
        return self.__parse_response(resp)

    def __parse_response(self,
                         resp: httpx.Response) -> dict:
        if not resp.is_success:
            raise GovBrAuthenticationError(
                    f"Erro ao trocar o código pelo token: {resp.status_code} - {resp.text}")

        token_json = resp.json()
        if "id_token" not in token_json:
            raise GovBrAuthenticationError("Token de ID não encontrado na resposta")

        id_token_decoded = self.jwt_payload_decode(token_json["id_token"])
        return {"token": token_json, "id_token_decoded": id_token_decoded}
