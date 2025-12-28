from src.django.channels.auth.token import TokenMiddleware


class AuthTokenMiddleware(TokenMiddleware):
    """
    Middleware that authenticates the user based on the auth token

    Header should be in the format: "AuthToken <_token_>"
    """

    keyword = "AuthToken"
