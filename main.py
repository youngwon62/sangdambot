# sangdambot FastAPI 서버: 상담 자동화 + 시간표 기능 포함

from fastapi import FastAPI, Request, UploadFile, File, Form
from pydantic import BaseModel
from datetime import datetime
import requests
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
import os

app = FastAPI()

# --- 텔레그램 정보 ---
TELEGRAM_BOT_TOKEN = "7954320343:AAGGW8K8N3SDfaTeG7VIVhBUcut-T9v1aDY"
TEACHER_CHAT_ID = "5560273829"

# --- 인증 DB 로드 ---
with open("student_profile_enriched_final_v3.json", "r", encoding="utf-8") as f:
    STUDENT_CODE_DB = json.load(f)

# --- 고정 시간표 ---
TEACHER_TIMETABLE = {
    "월": [1, 2, 3, 4, 6],
    "화": [1, 2, 3, 5, 6],
    "수": [1, 2, 4],
    "목": [1, 2, 3, 6],
    "금": [1, 2, 4, 5]
}
ALL_PERIODS = [1, 2, 3, 4, 5, 6, 7]
WEEKDAYS = ["월", "화", "수", "목", "금"]

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
    return {"valid": False}

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
    result = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TEACHER_CHAT_ID, "text": msg})
    return {"status": "sent", "telegram_response": result.json()}

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

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TEACHER_CHAT_ID, "text": body})

        return {"status": "sent", "email": msg["To"]}

    except Exception as e:
        return {"status": "error", "details": str(e)}

@app.get("/available_slots")
async def available_slots():
    empty_slots = {}
    for day in WEEKDAYS:
        empty = [p for p in ALL_PERIODS if p not in TEACHER_TIMETABLE.get(day, [])]
        empty_slots[day] = empty
    return {"available_slots": empty_slots}

@app.post("/upload_attendance_file")
async def upload_attendance_file(student_code: str = Form(...), file: UploadFile = File(...)):
    student_info = STUDENT_CODE_DB.get(student_code)
    if not student_info:
        return {"status": "error", "message": "학생 코드 오류"}

    contents = await file.read()

    msg = MIMEMultipart()
    msg["Subject"] = f"[출석 서류 제출] {student_info['name']} ({student_code})"
    msg["From"] = os.environ.get("EMAIL_USER")
    msg["To"] = ", ".join(["hyesulee14@gmail.com", "youngwon62@snu.ac.kr"])
    msg.attach(MIMEText("첨부된 출석 서류를 확인해 주세요."))

    part = MIMEApplication(contents, Name=file.filename)
    part["Content-Disposition"] = f'attachment; filename="{file.filename}"'
    msg.attach(part)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
            smtp.starttls()
            smtp.login(os.environ.get("EMAIL_USER"), os.environ.get("EMAIL_PASSWORD"))
            smtp.send_message(msg)

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument",
            data={"chat_id": TEACHER_CHAT_ID},
            files={"document": (file.filename, contents)})

        return {"status": "ok"}

    except Exception as e:
        return {"status": "error", "details": str(e)}

@app.post("/student_info_query")
async def student_info_query(data: dict):
    code = data.get("student_code")
    question = data.get("question", "")
    student = STUDENT_CODE_DB.get(code)

    if not student:
        return {"error": "유효하지 않은 학생 코드입니다."}

    keyword_map = {
        "지필": student.get("지필평가"),
        "수행": student.get("수행평가"),
        "종합": student.get("학기 종합 성적"),
        "추이": student.get("성적 추이"),
        "친구": student.get("가까운 친구"),
        "점심": student.get("점심을 함께 먹는 친구"),
        "조별": student.get("조별활동 참여 패턴")
    }

# 등록된 이름 목록 생성
registered_names = {info["name"] for info in STUDENT_CODE_DB.values()}

def mask_names(text, allowed_names):
    if not text:
        return text
    for word in text.split():
        if any(name in word for name in allowed_names):
            continue
        # 이름 길이에 따라 마스킹 적용
        if len(word) >= 2:
            text = text.replace(word, word[0] + "○" * (len(word) - 1))
        else:
            text = text.replace(word, "비공개")
    return text

matched = [v for k, v in keyword_map.items() if k in question]

if matched:
    masked = mask_names(matched[0], registered_names)
    return {"result": masked}
else:
    return {"result": "해당 질문에 대한 정보가 없습니다."}

