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
import pandas as pd
import re

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

    current_student_name = student.get("name", "")
    registered_names = {info["name"] for info in STUDENT_CODE_DB.values()}

    # 🔑 키워드 → 필드 경로 매핑
    keyword_map = {
        "주소": "address",
        "생일": "birth",
        "반": "class",
        "진로": "dream_job",
        "감정 상태": "emotional_state",
        "학년": "grade",
        "상담 일자": "last_counseling.date",
        "상담 내용": "last_counseling.summary",
        "상담 유형": "last_counseling.type",
        "이름": "name",
        "번호": "number",
        "종합 성적": "overall_grade",
        "친한 친구": "relationship.close_with",
        "관계 설명": "relationship.description",
        "적대적 관계": "relationship.hostile_with",
        "국어 지필": "scores.국어.written_exam",
        "국어 수행": "scores.국어.performance_exam",
        "국어 총점": "scores.국어.total_score",
        "국어 등급": "scores.국어.grade",
        "영어 지필": "scores.영어.written_exam",
        "영어 수행": "scores.영어.performance_exam",
        "영어 총점": "scores.영어.total_score",
        "영어 등급": "scores.영어.grade",
        "수학 지필": "scores.수학.written_exam",
        "수학 수행": "scores.수학.performance_exam",
        "수학 총점": "scores.수학.total_score",
        "수학 등급": "scores.수학.grade",
        "사회 지필": "scores.사회.written_exam",
        "사회 수행": "scores.사회.performance_exam",
        "사회 총점": "scores.사회.total_score",
        "사회 등급": "scores.사회.grade",
        "과학 지필": "scores.과학.written_exam",
        "과학 수행": "scores.과학.performance_exam",
        "과학 총점": "scores.과학.total_score",
        "과학 등급": "scores.과학.grade",
        "학생코드": "student_id",
        "추이": "성적 추이",
        "점심": "점심을 함께 먹는 친구",
        "조별": "조별활동 참여 패턴"
    }

    # 🔍 키워드 매칭
    matched_key = next((k for k in keyword_map if k in question), None)
    if not matched_key:
        return {"result": "해당 질문에 대한 정보가 없습니다."}

    # 🧠 안전한 필드 경로 탐색
    field_path = keyword_map[matched_key].split(".")
    value = student
    for key in field_path:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            value = None
            break

    if value is None:
        return {"result": "해당 정보가 등록되어 있지 않습니다."}

    # ✔ 이름 마스킹 처리
    def mask_names(value, allowed_names, current_name):
        if isinstance(value, list):
            return [mask_names(v, allowed_names, current_name) for v in value]
        elif not isinstance(value, str):
            return str(value)
        for name in allowed_names:
            if name != current_name:
                value = value.replace(name, name[0] + "○" * 2)
        return value

    return {"result": mask_names(value, registered_names, current_student_name)}

# --- 학사일정 CSV 로드 ---
SCHEDULE_CSV_PATH = "/mnt/data/정리된_학사일정.csv"
try:
    schedule_df = pd.read_csv(SCHEDULE_CSV_PATH)
except Exception as e:
    print(f"CSV 파일을 불러오는 중 오류 발생: {e}")
    schedule_df = pd.DataFrame(columns=["날짜", "일정"])  # 비어 있는 경우 대비

@app.post("/search_schedule")
async def search_schedule(request: Request):
    data = await request.json()
    month = data.get("month")
    day = data.get("day")  # day는 선택적

    if not month:
        return {"result": "요청에 월(month) 정보가 필요합니다."}

    year = 2025  # 기본은 2025년으로 고정

    if month < 1 or month > 12:
        return {"result": "올바른 월(month)을 입력해 주세요."}

    if day:
        if day < 1 or day > 31:
            return {"result": "올바른 일(day)을 입력해 주세요."}
        target_date = f"{year}-{month:02d}-{day:02d}"
        filtered = schedule_df[schedule_df["날짜"] == target_date]

        if not filtered.empty:
            result_text = " / ".join(f"{row['날짜']} 일정: {row['일정']}" for _, row in filtered.iterrows())
            return {"result": result_text}
        else:
            return {"result": "등록된 일정이 없습니다."}

    else:
        filtered = schedule_df[schedule_df["날짜"].str.startswith(f"{year}-{month:02d}")]

        if not filtered.empty:
            result_text = " / ".join(f"{row['날짜']} 일정: {row['일정']}" for _, row in filtered.iterrows())
            return {"result": result_text}
        else:
            return {"result": "등록된 일정이 없습니다."}
