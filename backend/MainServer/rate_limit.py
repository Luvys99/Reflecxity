# 요청 수 제한 (Redis): 한 사람이 정해진 시간 구간에 같은 기능을 몇 번 썼는지 센다 (#103)
# 키: rate:{기능}:{누구}:{구간 번호}. 구간이 끝나면 저절로 지워진다
import time

LOOPBACK_HOSTS = ("127.0.0.1", "::1")


def client_ip(request):
    """요청한 기기의 IP

    Tailscale Funnel을 거친 요청은 이 Mac의 Tailscale이 대신 보내서 127.0.0.1로 보인다.
    Tailscale은 진짜 IP를 X-Forwarded-For에 담아 주므로, 127.0.0.1에서 온 요청일 때만 이 헤더를 믿는다.
    바깥에서 바로 들어온 요청이 헤더를 꾸며 넣어도 쓰지 않는다
    """
    host = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("x-forwarded-for")
    if host in LOOPBACK_HOSTS and forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return host


async def count_request(redis_client, name, who, limit, window_seconds):
    """이번 구간의 횟수를 하나 올린다. 넘으면 다음 구간까지 남은 초, 괜찮으면 None"""
    now = time.time()
    window = int(now // window_seconds)
    key = f"rate:{name}:{who}:{window}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_seconds)
    if count > limit:
        return max(1, int((window + 1) * window_seconds - now))
    return None
