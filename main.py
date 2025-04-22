# Render 배포용 FastAPI 서버 - main.py

from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
import requests
import json
import os

app = FastAPI()

# 텔레그램 정보 (환경변수로 설정)
TELEGRAM_BOT_TOKEN = "7954320343:AAGGW8K8N3SDfaTeG7VIVhBUcut-T9v1aDY"
TEACHER_CHAT_ID = "5560273829"

# 학생 코드 DB 로드
with open("student_code_db.json", "r", encoding="utf-8") as f:
    STUDENT_CODE_DB = json.load(f)

# 데이터 모델 정의
class ConsultRequest(BaseModel):
    student_code: str
    parent_message: str
    preferred_time: str = "미지정"
    timestamp: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 텔레그램 메시지 전송 함수
def send_to_telegram(chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    response = requests.post(url, json=payload)
    return response.json()

# 상담 신청 → 유효 코드 검사 → 텔레그램 전송
@app.post("/send_consult")
async def send_consult(data: ConsultRequest):
    student_info = STUDENT_CODE_DB.get(data.student_code)
    if not student_info:
        return {"status": "error", "message": "유효하지 않은 학생 코드입니다."}

    msg = f"""
📌 [상담 신청 도착]
🧑 학생 코드: {data.student_code} ({student_info['name']})
💬 상담 내용: {data.parent_message}
📅 희망 시간: {data.preferred_time}
⏰ 신청 시각: {data.timestamp}
"""
    result = send_to_telegram(TEACHER_CHAT_ID, msg)
    return {"status": "sent", "telegram_response": result}

# 코드 인증용 (GPTs 2차 인증)
class CodeOnly(BaseModel):
    student_code: str

@app.post("/verify_code")
async def verify_code(data: CodeOnly):
    student_info = STUDENT_CODE_DB.get(data.student_code)
    if not student_info:
        return {"valid": False}
    return {"valid": True, "student_id": student_info["student_id"], "name": student_info["name"]}
