import jwt
import datetime

SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 6000


def create_server_token(server_id: str) -> str:
    """
    Generates a signed JWT for the server to authenticate with MCP tools.
    """
    expire = datetime.datetime.utcnow() + datetime.timedelta(
        minutes=TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": server_id,
        "exp": expire,
        "iat": datetime.datetime.utcnow(),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def verify_server_token(token: str):
    """
    Verifies a JWT token issued by this server.
    Returns decoded payload if valid, raises Exception if not.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.PyJWTError:
        raise Exception("Invalid token")
