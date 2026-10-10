import secrets

from mcp.server.auth.provider import AccessToken, TokenVerifier


class StaticTokenVerifier(TokenVerifier):
    def __init__(self, expected: str, resource: str, scope: str) -> None:
        self._expected = expected
        self._resource = resource
        self._scope = scope

    async def verify_token(self, token: str) -> AccessToken | None:
        if len(token) != len(self._expected) or not secrets.compare_digest(token, self._expected):
            return None
        return AccessToken(
            token=token,
            client_id="skillproof",
            scopes=[self._scope],
            resource=self._resource,
        )
