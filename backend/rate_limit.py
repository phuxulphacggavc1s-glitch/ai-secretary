from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_rate_limit_key(request: Request) -> str:
    user = request.scope.get("user")
    user_id = getattr(user, "id", None)
    if user_id:
        return str(user_id)
    return get_remote_address(request)


limiter = Limiter(key_func=get_rate_limit_key)
