# 번역 하루 글자 수 상한 (Redis): Google 무료 체험판은 할당량을 낮출 수 없어서 Main이 직접 센다 (#105)
# 키: translate:chars:{YYYY-MM-DD} = 그날 번역한 글자 수. 이틀 뒤 저절로 지워진다
import time

KEY_TTL_SECONDS = 2 * 24 * 60 * 60


def daily_chars_key(day=None):
    return f"translate:chars:{day or time.strftime('%Y-%m-%d')}"


async def reserve_translation_chars(redis_client, chars, daily_limit):
    """오늘 쓴 글자 수에 chars를 더한다. 상한을 넘으면 되돌리고 False

    먼저 더하고(INCRBY) 결과를 보는 방식이라, 요청이 동시에 들어와도 상한을 넘겨 통과시키지 않는다
    """
    key = daily_chars_key()
    used = await redis_client.incrby(key, chars)
    if used == chars:
        await redis_client.expire(key, KEY_TTL_SECONDS)  # 오늘 첫 번역
    if used > daily_limit:
        await redis_client.decrby(key, chars)
        return False
    return True


async def release_translation_chars(redis_client, chars):
    """번역이 실패하면 미리 센 글자를 되돌린다"""
    await redis_client.decrby(daily_chars_key(), chars)
