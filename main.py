# sangdambot FastAPI 서버: 라우팅 자동화 + 상담 요약 이메일 전송 포함

from fastapi import FastAPI, Request
from pydantic import BaseModel
from datetime import datetime
import requests
import json
import smtplib
from email.mime.text import MIMEText
import os

app = FastAPI()

# 텔레그램 정보 (직접 입력된 값)
TELEGRAM_BOT_TOKEN = "7954320343:AAGGW8K8N3SDfaTeG7VIVhBUcut-T9v1aDY"
TEACHER_CHAT_ID = "5560273829"

# 인증 DB 로드
with open("student_code_db.json", "r", encoding="utf-8") as f:
    STUDENT_CODE_DB = json.load(f)

# 상담 요청 형식
class ConsultRequest(BaseModel):
    student_code: str
    parent_message: str
    preferred_time: str = "미지정"
    timestamp: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# 상담 요약 및 이메일 요청 형식
class EmailSummaryRequest(BaseModel):
    student_code: str
    category: str
    content: str
    summary: str
    preferred_time: str

# 텔레그램 메시지 전송 함수
def send_to_telegram(chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    response = requests.post(url, json=payload)
    return response.json()

# 상담 신청 전송 API
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

# 상담 주제별 분류 라우팅 API
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

# 상담 요약 이메일 전송 API
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
        return {"status": "sent", "email": "hyesulee14@gmail.com"}
    except Exception as e:
        return {"status": "error", "details": str(e)}
