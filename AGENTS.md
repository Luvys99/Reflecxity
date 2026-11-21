# 작업 원칙

이 저장소의 코드는 다음 작업의 본보기가 됩니다. 기존 코드의 패턴을 따르되,
따르려는 패턴이 우회 코드나 중복으로 보이면 복제하지 말고 먼저 알려 주세요.

## 문제를 고칠 때
- 증상을 덮지 말고 근본 원인을 고칩니다. sleep, 재시도, 예외 무시, 경고 억제로
  넘어가고 싶어질 때는 멈추고 원인을 설명해 주세요.
- 린트, 타입, 테스트가 실패하면 규칙을 끄거나 테스트를 약하게 만들지 않습니다.
  규칙이 틀렸다고 판단되면 고치기 전에 이유를 말해 주세요.
- 옳은 일을 하지 않은 이유를 주석이나 문서에 적어 두지 않습니다.
  주석은 코드만으로 알 수 없는 사실에만 씁니다.

## 작업을 끝냈다고 말하기 전에
- 빌드와 전체 테스트를 실행하고 결과를 보여 주세요.
- 동작이 바뀌었다면 실제로 실행해 확인한 증거(요청과 응답, 로그, 스크린샷)를 남겨 주세요.
- 확인하지 못한 부분이 있으면 그대로 밝혀 주세요.

## 같은 지적을 다시 받았을 때
- 이 문서에 문장을 추가하기보다, 린트 규칙이나 아키텍처 테스트나 타입으로
  자동 차단할 방법을 먼저 제안해 주세요.

## 이름 짓기 (#25, 클린 코드 2·3장)
- 이름만 보고 무엇을 담는지·하는지 알 수 있게 짓습니다. 한 글자·축약 금지 (`r` → `redis_client`, `msg_id` → `message_id`). 짧은 반복문의 `i`만 예외
- 여러 개를 담으면 복수형 (`voice_file_names`)
- 함수는 동사로 시작 (`mark_job_failed`), 변수는 명사
- 한 개념에 한 단어: 작업 = `job`, 할 일 목록 = `stream`, 처리 = `process`
- 값은 이름 있는 상수로, 이름에 대상과 단위를 넣습니다 (`WAIT_FOR_JOB_MS`)
- 이름에 타입·방식 꼬리(`_async`, `_list`)를 붙이지 않습니다
- 단계마다 주석을 달아야 읽히는 함수는, 그 단계를 이름 있는 함수로 뺄 수 있는지 먼저 봅니다
- 서버 안의 이름은 원래 팀 코드까지 이 규칙대로 고쳤습니다(#58). 앱과 서버의 약속(URL·응답 키)도 고쳤습니다(#63): 주소는 명사 복수형(`/users/{uuid}/recordings`, `/users/{uuid}/training`), 앱은 한국어 문장이 아니라 `status` 같은 값으로 판단합니다. 약속을 바꿀 때는 서버만 바꾸지 말고 앱(`android/`)과 Main 테스트를 같은 PR에서 바꿉니다

## 명령어
- 빌드: 없음 (Python은 빌드 단계가 없고, Android 빌드는 이 저장소의 개선 범위 밖)
- 테스트 (Mac Redis가 켜져 있어야 함, 테스트용 DB 15번만 씀)
  - Main: `cd backend/MainServer && .venv/bin/python -m pytest tests` (앱이 받는 업로드·학습·TTS API 응답)
  - Model: `cd backend/ModelServer && .venv/bin/python -m pytest tests` (학습·TTS 워커 규칙, Mac Redis가 켜져 있어야 함, 테스트용 DB 15번만 씀)
- 로컬 실행 (Mac):
  - DB·Redis: `cd backend/MainServer && docker compose up -d` (Tailscale 먼저 켜기)
  - Main: `cd backend/MainServer && .venv/bin/python main.py` → http://localhost:28300/docs (`.env` 필요, README 참고)
  - Model: `cd backend/ModelServer && .venv/bin/python main.py` → http://localhost:48000/docs
  - 학습·TTS 요청은 GPU와 수 분의 시간을 씁니다. 실행 전에 물어봐 주세요.

## 구조
- `backend/MainServer`: 앱이 부르는 API(FastAPI, 28300)와 MariaDB. Model Server의 코드를 import하지 않습니다.
  - 학습은 `train_queue.py`, TTS는 `tts_queue.py`가 Redis에 작업을 넣고 결과를 읽습니다 (Windows 워커가 처리). 그 밖의 Model 호출(업로드, 파일, 사용자 삭제)은 HTTP
- `backend/ModelServer`: 프로젝트 코드는 아래 파일뿐입니다.
  - `main.py`(FastAPI, 48000. 녹음 파일 올리기·목록·삭제, 사용자 삭제만. 학습·TTS는 HTTP 주소 없이 워커가 Redis로 받는다, #47)
  - `training.py`(학습 파이프라인, 학습 횟수 `TRAIN_EPOCHS`), `tts.py`(모델 파일 찾기, TTS 실행), `command.py`(하위 프로세스 실행기, 학습·TTS 공용)
  - `auto_pitch.py`(자동 피치, #59): 학습 끝에 녹음 높이(F0)를 재서 `logs/{uuid}/auto_pitch.txt`에 저장, TTS 워커가 읽는다. 기준값은 `tts.TTS_VOICE_F0_HZ`(기계 음성을 바꾸면 실제 변환으로 다시 맞춘다)
  - `job_worker.py`(워커 공통: Redis 스트림에서 꺼내기, `job:{id}` 기록, 재시도. 다시 해도 같은 실패는 `JobFailed`). 워커 이름은 `컴퓨터이름-번호`(`--number`, 기본 1). 한 컴퓨터에 같은 종류의 워커를 여러 개 켤 때는 번호를 다르게, 다시 켤 때는 같은 번호로 (#51)
  - `train_worker.py`(학습 워커, 서버와 별개 프로세스. 학습 한 건만 하고 나머지는 `job_worker.py`, 학습 파이프라인은 `training.py`를 같이 씀)
  - `tts_worker.py`(TTS 워커, `stream:tts`. TTS 한 건만 하고 나머지는 `job_worker.py`, TTS는 `tts.py`를 같이 씀). 변환은 새 프로세스 없이 워커 안에서 `rvc_cli.run_tts_script`를 부른다(`tts.convert_text_to_voice`, #49). 워커는 켜질 때 작업을 받기 전에 `tts.prepare_voice_converter()`로 VoiceConverter·HuBERT를 미리 올린다(#54). 피치는 요청 값 → 자동 피치 → `default_pitch` 순서(`choose_pitch`, #59)
  - `tests/`(pytest. 실행 명령은 위 "명령어")
  `rvc_cli.py`, `uvr_cli.py`, `rvc/`, `uvr/`, `docs/`, `assets/`는 외부 rvc-cli 코드라 고치지 않습니다. 꼭 필요하면 먼저 물어봐 주세요.
- `rvc/configs/*.json`은 실행할 때마다 바뀝니다. 커밋하지 않습니다.

## Redis 키 (Main과 워커의 약속)
Main(`MainServer/train_queue.py`)과 워커(`ModelServer/job_worker.py`, `*_worker.py`)는 서로 import하지 않고 아래 이름으로만 만납니다. 한쪽을 바꾸면 다른 쪽과 양쪽 테스트도 같이 바꿉니다.

| 키 | 종류 | 쓰는 쪽 → 읽는 쪽 | 내용 |
| --- | --- | --- | --- |
| `stream:train` / 그룹 `train-workers` | Stream | Main(`XADD`) → 학습 워커 | 한 줄에 `job_id` |
| `stream:tts` / 그룹 `tts-workers` | Stream | Main(`XADD`) → TTS 워커 | 한 줄에 `job_id` |
| `job:{job_id}` | Hash | Main이 만들고 워커가 상태를 바꿈 | `type`, `user`, `status`, `attempts`, `error`, `message_id`, 시각들 (TTS는 `text`, `default_pitch`, `pitch`는 요청에 있을 때만) |
| `user:{uuid}:train` | String | Main | 그 사용자의 최근 학습 `job_id` |
| `job:{job_id}:result` | String (bytes) | 워커 → Main(`GETDEL`) | 작업 결과 (TTS는 wav). Main이 가져가면서 지움, 못 가져가면 10분 뒤 자동 삭제 |
| `job:{job_id}:done` | List | 워커 → Main(`BLPOP`) | 최종 `success` / `fail` 신호 (재시도 중에는 없음). 10분 뒤 자동 삭제 |
| `translate:chars:{YYYY-MM-DD}` | String (숫자) | Main만 (`translation_limit.py`) | 그날 번역한 글자 수. `TRANSLATE_DAILY_CHAR_LIMIT`을 넘으면 429 (#105). 이틀 뒤 자동 삭제 |

`status`: `queued`(Main) → `progress`(워커) → `success` / `fail`(워커)
- `android/`: Java 앱. Main Server만 호출합니다.
