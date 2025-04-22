# sangdambot FastAPI 서버: 상담 자동화 + 시간표 기능 포함

from fastapi import FastAPI, Request
from pydantic import BaseModel
from datetime import datetime
import requests
import json
import smtplib
from email.mime.text import MIMEText
import os

app = FastAPI()

# --- 텔레그램 정보 ---
TELEGRAM_BOT_TOKEN = "7954320343:AAGGW8K8N3SDfaTeG7VIVhBUcut-T9v1aDY"
TEACHER_CHAT_ID = "5560273829"

# --- 인증 DB 로드 ---
with open("student_profile_enriched_final.json", "r", encoding="utf-8") as f:
    STUDENT_CODE_DB = json.load(f)

# --- 고정 시간표 (월~금 각 1~7교시, 총 35차시 중 수업 있는 시간만 지정) ---
TEACHER_TIMETABLE = {
    "월": [1, 2, 3, 4, 6],
    "화": [1, 2, 3, 5, 6],
    "수": [1, 2, 4],
    "목": [1, 2, 3, 6],
    "금": [1, 2, 4, 5]
}

ALL_PERIODS = [1, 2, 3, 4, 5, 6, 7]
WEEKDAYS = ["월", "화", "수", "목", "금"]

# --- 모델 정의 ---
class ConsultRequest(BaseModel):
    student_code: str
    parent_message: str
    preferred_time: str = "미지정"
    timestamp: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class EmailSummaryRequest(BaseModel):
    student_code: str
    category: str
    content: str
    summary: str
    preferred_time: str

# --- 학생 코드 인증 ---
@app.post("/verify_code")
async def verify_code(request: Request):
    data = await request.json()
    code = data.get("student_code")
    student_info = STUDENT_CODE_DB.get(code)
    if student_info:
        return {
            "valid": True,
            "name": student_info["name"],
            "student_id": student_info["student_id"]
        }
    return { "valid": False }


# --- 텔레그램 메시지 전송 ---
def send_to_telegram(chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload)
    return response.json()

# --- 상담 전송 ---
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

# --- 상담 주제 라우팅 ---
@app.post("/route_topic")
async def route_topic(request: Request):
    data = await request.json()
    message = data.get("message", "")
    categories = {
        "성적": "성적/학업",
        "학업": "성적/학업",
        "교우": "교우관계/생활",
        "생활": "교우관계/생활",
        "진로": "진로/진학",
        "진학": "진로/진학",
        "폭력": "학교폭력",
        "학교폭력": "학교폭력",
    }
    for keyword, label in categories.items():
        if keyword in message:
            return {"category": label}
    return {"category": "기타 고민"}

# --- 상담 요약 확인 ---
@app.post("/confirm_summary")
async def confirm_summary(data: EmailSummaryRequest):
    student_info = STUDENT_CODE_DB.get(data.student_code)
    if not student_info:
        return {"status": "error", "message": "학생 코드 오류"}

    confirm_msg = f"""
📌 상담 요약 확인 요청
- 학생: {student_info['name']} ({data.student_code})
- 영역: {data.category}
- 상담 요청 내용: {data.content}
- 상담 희망 시간: {data.preferred_time}
- 요약 내용:
{data.summary}

이 내용이 맞다면 확인 후 메일과 텔레그램으로 발송됩니다.
"""
    return {"status": "pending", "confirm_message": confirm_msg}

# --- 상담 요약 메일 + 텔레그램 전송 ---
@app.post("/send_summary_email")
async def send_summary_email(data: EmailSummaryRequest):
    student_info = STUDENT_CODE_DB.get(data.student_code)
    if not student_info:
        return {"status": "error", "message": "학생 코드 오류"}

    body = f"""
📌 상담 요약
- 학생: {student_info['name']} ({data.student_code})
- 영역: {data.category}
- 상담 요청 내용: {data.content}
- 요약 내용: {data.summary}
- 상담 희망 시간: {data.preferred_time}
"""
    msg = MIMEText(body)
    msg["Subject"] = "[상담 요청 요약] 학부모 상담 내용"
    msg["From"] = os.environ.get("EMAIL_USER")
    msg["To"] = ", ".join(["hyesulee14@gmail.com", "youngwon62@snu.ac.kr"])

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_PASSWORD"))
            smtp.send_message(msg)

        result = send_to_telegram(TEACHER_CHAT_ID, body)

        return {
            "status": "sent",
            "email": "hyesulee14@gmail.com",
            "telegram_result": result
        }

    except Exception as e:
        return {
            "status": "error",
            "details": str(e)
        }

# --- 교사 빈 시간표 조회 ---
@app.get("/available_slots")
async def available_slots():
    empty_slots = {}
    for day in WEEKDAYS:
        empty = [p for p in ALL_PERIODS if p not in TEACHER_TIMETABLE.get(day, [])]
        empty_slots[day] = empty
    return {"available_slots": empty_slots}
