# TTS 작업 큐 (Redis): TTS 요청을 stream:tts에 넣고, 워커의 끝 신호를 기다렸다가 결과 음성을 가져온다 (#38)
# 작업은 Windows의 TTS 워커(ModelServer/tts_worker.py)가 꺼내 처리한다
# 키 이름과 상태 값은 워커와의 약속이다 (AGENTS.md "Redis 키" 표). 한쪽만 바꾸면 깨진다
import time
import uuid

TTS_STREAM = "stream:tts"


async def enqueue_tts_job(redis_client, user_uuid, text, pitch, default_pitch):
    # 작업 정보(queued)를 만들고 목록에 작업 ID를 넣는다
    # pitch가 None이면 넣지 않는다: 워커가 자동 피치 → default_pitch 순서로 고른다 (#59)
    job_id = str(uuid.uuid4())
    job = {
        "type": "tts",
        "user": user_uuid,
        "text": text,
        "default_pitch": default_pitch,
        "status": "queued",
        "attempts": 0,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if pitch is not None:
        job["pitch"] = pitch
    await redis_client.hset(f"job:{job_id}", mapping=job)
    await redis_client.xadd(TTS_STREAM, {"job_id": job_id})
    return job_id


async def wait_for_tts_result(redis_binary_client, job_id, timeout_seconds):
    # 워커의 끝 신호(job:{id}:done)를 BLPOP으로 기다린다 (폴링 없음, 끝나는 순간 깨어남)
    # 돌려주는 값: ("success", 음성 bytes) / ("fail", None) / ("timeout", None)
    # 결과는 가져가면서 지운다(GETDEL): Redis에 머무는 시간을 줄이려고. 못 가져간 것은 워커가 건 10분 뒤 자동 삭제
    signal = await redis_binary_client.blpop(f"job:{job_id}:done", timeout=timeout_seconds)
    if signal is None:
        return "timeout", None
    status = signal[1].decode()
    if status != "success":
        return status, None
    return status, await redis_binary_client.getdel(f"job:{job_id}:result")
