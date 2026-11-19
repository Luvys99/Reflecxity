# 학습·TTS 단계(rvc_cli.py, uvr_cli.py 등)를 새 프로세스로 실행하고 로그를 출력한다
import asyncio

# 모델 명령어 실행 함수 (비동기 처리)

async def run_command_async(command, model_id, step_name):
    process = None
    try:
        if step_name != "autopitch":
            print(f"[Model {model_id}] {step_name} 단계 시작...")

        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        async def print_stdout_logs():
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                print(f"[Model {model_id}] {line.decode('utf-8', errors='ignore').strip()}")

        async def print_stderr_logs():
            while True:
                err_line = await process.stderr.read(1024)
                if not err_line:
                    break
                print(f"[Model {model_id}] LOG: {err_line.decode('utf-8', errors='ignore').strip()}")

        stdout_task = asyncio.create_task(print_stdout_logs())
        stderr_task = asyncio.create_task(print_stderr_logs())

        await process.wait()

        await stdout_task
        await stderr_task

        if process.returncode != 0:
            raise RuntimeError(
                f"{step_name} 단계 실행 중 오류 발생: 프로세스 종료 코드 {process.returncode}"
            )

        if step_name != "autopitch":
            print(f"[Model {model_id}] {step_name} 단계 완료")

    except Exception as e:
        print(f"[Model {model_id}] {step_name} 단계 실행 중 오류 발생: {e}")
        if process and process.returncode is None:
            process.kill()  # 프로세스 강제 종료
            await process.wait()  # 프로세스가 완전히 종료될 때까지 대기
        raise e
