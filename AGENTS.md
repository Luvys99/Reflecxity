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
- 원래 팀 코드의 이름(`create_model_async`, `voice_file_name` 등)은 아직 그대로입니다. 새 코드에서 따라 하지 않습니다

## 명령어
- 빌드: 없음 (Python은 빌드 단계가 없고, Android 빌드는 이 저장소의 개선 범위 밖)
- 테스트: `cd backend/ModelServer && .venv/bin/python -m pytest tests` (학습·TTS 워커 규칙, Mac Redis가 켜져 있어야 함, 테스트용 DB 15번만 씀)
  `backend/*/test.py`는 실제 서버에 요청을 보내는 수동 스크립트라 테스트가 아닙니다 (Model 쪽은 학습까지 요청함)
- 로컬 실행 (Mac):
  - DB·Redis: `cd backend/MainServer && docker compose up -d` (Tailscale 먼저 켜기)
  - Main: `cd backend/MainServer && .venv/bin/python main.py` → http://localhost:28300/docs (`.env` 필요, README 참고)
  - Model: `cd backend/ModelServer && .venv/bin/python main.py` → http://localhost:48000/docs
  - 학습·TTS 요청은 GPU와 수 분의 시간을 씁니다. 실행 전에 물어봐 주세요.

## 구조
- `backend/MainServer`: 앱이 부르는 API(FastAPI, 28300)와 MariaDB. Model Server와는 HTTP로만 통신하고 그 코드를 import하지 않습니다.
- `backend/ModelServer`: 프로젝트 코드는 아래 파일뿐입니다.
  - `main.py`(FastAPI, 48000), `status.py`(사용자별 상태 파일)
  - `training.py`(학습 파이프라인), `tts.py`(모델 파일 찾기, TTS 실행), `command.py`(하위 프로세스 실행기, 학습·TTS 공용)
  - `job_worker.py`(워커 공통: Redis 스트림에서 꺼내기, `job:{id}` 기록, 재시도. 다시 해도 같은 실패는 `JobFailed`)
  - `train_worker.py`(학습 워커, 서버와 별개 프로세스. 학습 한 건만 하고 나머지는 `job_worker.py`, 학습 파이프라인은 `training.py`를 같이 씀)
  - `tts_worker.py`(TTS 워커, `stream:tts`. TTS 한 건만 하고 나머지는 `job_worker.py`, TTS는 `tts.py`를 같이 씀)
  - `tests/`(pytest. 실행 명령은 위 "명령어")
  `rvc_cli.py`, `uvr_cli.py`, `rvc/`, `uvr/`, `docs/`, `assets/`는 외부 rvc-cli 코드라 고치지 않습니다. 꼭 필요하면 먼저 물어봐 주세요.
- `rvc/configs/*.json`은 실행할 때마다 바뀝니다. 커밋하지 않습니다.
- `android/`: Java 앱. Main Server만 호출합니다.
