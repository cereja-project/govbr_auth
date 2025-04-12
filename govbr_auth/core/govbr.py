import base64
import json
import os
import secrets
import urllib.parse
import hashlib
import re
import httpx
from cryptography.fernet import Fernet
from govbr_auth.core.config import GovBrConfig

__all__ = ["GovBrAuthorize", "GovBrIntegration"]


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
                f"{self.config.auth_url}?response_type={self.config.response_type}"
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
    def __init__(self,
                 config: GovBrConfig):
        self.config = config

    def __decrypt_code_verifier(self,
                                encrypted_verifier: str) -> str:
        try:
            secret_key = self.config.cript_verifier_secret.encode('utf-8')
            fernet = Fernet(secret_key)
            decrypted_bytes = fernet.decrypt(encrypted_verifier.encode('utf-8'))
            return decrypted_bytes.decode("utf-8")
        except Exception:
            raise ValueError("Invalid or missing code_verifier")

    def __b64_decode(self,
                     b64_data: str) -> str:
        padding = 4 - len(b64_data) % 4
        if padding:
            b64_data += '=' * padding
        return base64.b64decode(b64_data).decode('utf-8')

    def jwt_payload_decode(self,
                           id_token: str) -> dict:
        header_b64, payload_b64, signature_b64 = id_token.split('.')
        payload_str = self.__b64_decode(payload_b64)
        return json.loads(payload_str)

    async def async_exchange_code_for_token(self,
                                            code: str,
                                            state: str) -> dict:
        return self.__exchange_code_for_token(code, state, async_mode=True)

    def exchange_code_for_token_sync(self,
                                     code: str,
                                     state: str) -> dict:
        return self.__exchange_code_for_token(code, state, async_mode=False)

    def __exchange_code_for_token(self,
                                  code: str,
                                  state: str,
                                  async_mode: bool) -> dict:
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

        if async_mode:
            return self.__exchange_async(data, headers)
        else:
            return self.__exchange_sync(data, headers)

    async def __exchange_async(self,
                               data: dict,
                               headers: dict) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.config.token_url, data=data, headers=headers, follow_redirects=False,
                                     timeout=10)
        return self.__parse_response(resp)

    def __exchange_sync(self,
                        data: dict,
                        headers: dict) -> dict:
        with httpx.Client() as client:
            resp = client.post(self.config.token_url, data=data, headers=headers, follow_redirects=False, timeout=10)
        return self.__parse_response(resp)

    def __parse_response(self,
                         resp: httpx.Response) -> dict:
        if not resp.is_success:
            return {"error": "Falha ao tentar autenticar no Govbr", "status_code": resp.status_code}

        token_json = resp.json()
        if "id_token" not in token_json:
            return {"error": "Falta 'id_token' na resposta do token"}

        id_token_decoded = self.jwt_payload_decode(token_json["id_token"])
        return {"token": token_json, "id_token_decoded": id_token_decoded}
