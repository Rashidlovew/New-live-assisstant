from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import openai
import tempfile
import os
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
CORS(app)

# Email config
EMAIL_SENDER = "noreply@example.com"
EMAIL_RECEIVER = "frnreports@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Set of fields to collect
fields_order = ["name", "Date", "Briefing", "LocationObservations", "Examination", "Outcomes", "TechincalOpinion"]
session_data = {}

@app.route("/transcribe", methods=["POST"])
def transcribe():
    file = request.files["file"]
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as temp_audio:
        file.save(temp_audio.name)
        temp_audio_path = temp_audio.name

    with open(temp_audio_path, "rb") as f:
        transcript_response = openai.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )
        transcript = transcript_response.text

    os.remove(temp_audio_path)
    return jsonify({"text": transcript})

@app.route("/speak", methods=["POST"])
def speak():
    data = request.json
    text = data.get("text")
    voice = "hala"  # Arabic female voice

    response = openai.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text,
        response_format="mp3"
    )

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    temp_file.write(response.read())
    temp_file.flush()
    return send_file(temp_file.name, mimetype="audio/mpeg")

def format_doc_arabic(paragraph):
    paragraph.paragraph_format.alignment = 2
    run = paragraph.runs[0]
    run.font.name = 'Dubai'
    run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Dubai')
    run.font.size = Pt(13)
    rtl = OxmlElement('w:rtl')
    rtl.set(qn('w:val'), '1')
    paragraph._element.get_or_add_pPr().append(rtl)

@app.route("/generate_report", methods=["POST"])
def generate_report():
    data = request.json
    name = data.get("name", "")

    doc = Document("police_report_template.docx")
    for field in fields_order:
        if field in data:
            value = data[field]
            doc.add_paragraph(f"{value}")
            format_doc_arabic(doc.paragraphs[-1])

    file_path = f"report_{name}.docx"
    doc.save(file_path)
    send_email_with_report(file_path, name)
    return jsonify({"message": "تم إعداد التقرير وإرساله بنجاح ✅"})

def send_email_with_report(filepath, name):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg["Subject"] = f"تقرير {name}"

    body = f"مرحباً،\n\nيرجى العثور على التقرير الفني الخاص بـ {name} مرفقاً.\n\nتحياتي."
    msg.attach(MIMEText(body, "plain"))

    with open(filepath, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(filepath)}")
        msg.attach(part)

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(SMTP_USERNAME, SMTP_PASSWORD)
    server.send_message(msg)
    server.quit()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
