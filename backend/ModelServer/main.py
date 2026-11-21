import os
import shutil

from fastapi import FastAPI, HTTPException, File, UploadFile

app = FastAPI()

@app.get(
    "/online",
    tags=["상태"],
    summary="서버 상태 확인",
    description="서버가 떠 있으면 `{\"status\": \"online\"}`.",
)
async def check_online():
    return {"status": "online"}

# 파일 저장 기능 추가
@app.post(
    "/user/{user_uuid}/upload",
    tags=["녹음 파일"],
    summary="녹음 업로드",
    description="`user/{user_uuid}/raw/`에 그대로 저장한다.",
)
async def upload_file(user_uuid: str, file: UploadFile = File(...)):
    try:
        # 파일 저장 (user_uuid 폴더에 저장)
        user_folder = os.path.join(".", "user", user_uuid, "raw")
        os.makedirs(user_folder, exist_ok=True)
        file_path = os.path.join(user_folder, file.filename)
        with open(file_path, "wb") as f:
            f.write(file.file.read())

        return {"message": "파일 업로드 성공", "file_path": file_path}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 저장 중 오류 발생: {e}")

# 파일 검색 기능 추가
@app.get(
    "/user/{user_uuid}/files",
    tags=["녹음 파일"],
    summary="업로드한 파일 목록",
    description="`user/{user_uuid}/raw/`의 파일 이름 목록.",
)
def get_user_files(user_uuid: str):
    try:
        user_folder = os.path.join(".", "user", user_uuid, "raw")
        files = [
            f for f in os.listdir(user_folder) if os.path.isfile(os.path.join(user_folder, f))
        ]
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 목록 조회 중 오류 발생: {e}")

# 파일 삭제 기능 추가
@app.delete(
    "/user/{user_uuid}/raw/{filename}",
    tags=["녹음 파일"],
    summary="업로드한 파일 삭제",
    description="`user/{user_uuid}/raw/{filename}`을 지운다.",
)
async def delete_file(user_uuid: str, filename: str):
    try:
        file_path = os.path.join(".", "user", user_uuid, "raw", filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return {"message": "파일 삭제 성공"}
        else:
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없음")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 삭제 중 오류 발생: {e}")

# 사용자 삭제 기능 추가 (폴더 존재 여부 판단 개선)
@app.delete(
    "/user/{user_uuid}",
    tags=["사용자"],
    summary="사용자 폴더 삭제",
    description="`user/{user_uuid}/`(녹음)와 `logs/{user_uuid}/`(학습 결과, 모델)를 지운다.",
)
def delete_user(user_uuid: str):
    try:
        # 사용자 폴더 경로
        user_path = os.path.join(".", "user", user_uuid)
        user_model_path = os.path.join(".", "logs", user_uuid)

        # 폴더 존재 여부를 확인하여 삭제
        if os.path.exists(user_path) or os.path.exists(user_model_path):
            if os.path.exists(user_path):
                print(f"폴더 {user_path} 존재. 삭제를 시도합니다.")
                # 폴더 삭제
                shutil.rmtree(user_path)
                print(f"폴더 {user_path} 삭제 성공.")

            if os.path.exists(user_model_path):
                print(f"폴더 {user_model_path} 존재. 삭제를 시도합니다.")
                # 폴더 삭제
                shutil.rmtree(user_model_path)
                print(f"폴더 {user_model_path} 삭제 성공.")

            return {"message": "사용자 및 파일 삭제 성공"}
        else:
            # 둘 다 없을 경우 에러 발생시키지 않고 메시지 반환
            print(f"폴더 {user_path}와 {user_model_path}가 존재하지 않음.")
            return {"message": "사용자를 찾을 수 없습니다."}

    except Exception as e:
        print(f"사용자 삭제 중 오류 발생: {e}")
        raise HTTPException(status_code=500, detail=f"사용자 삭제 중 오류 발생: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=48000)
