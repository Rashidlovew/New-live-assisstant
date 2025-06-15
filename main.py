from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
import openai
import os
import tempfile
import smtplib
from email.message import EmailMessage

openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__, static_url_path='/static', static_folder='static', template_folder='templates')
CORS(app)

user_states = {}
template_path = "police_report_template.docx"
final_email = "frnreports@gmail.com"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/transcribe", methods=["POST"])
def transcribe():
    file = request.files["audio"]
    user_id = request.form.get("user_id", "anonymous")

    transcript_response = openai.audio.transcriptions.create(
        model="whisper-1",
        file=(file.filename, file.stream, file.mimetype)
    )

    text = transcript_response.text

    conversation = user_states.get(user_id, [])
    conversation.append({"role": "user", "content": text})

    system_prompt = (
        "أنت مساعد صوتي ذكي متخصص في كتابة تقارير فنية لقسم الهندسة الجنائية. "
        "اجعل المحادثة طبيعية وودية تبدأ بالترحيب ثم الانتقال بسلاسة لجمع البيانات من المحقق. "
        "لا تكرر كلام المستخدم، بل انتقل للسؤال التالي بطريقة محادثة بشرية. "
        "احرص على فهم نية المستخدم بدون الاعتماد على كلمات محددة فقط. "
        "بعد جمع المعلومات، أخبره أنك سترسل التقرير."
    )

    conversation.insert(0, {"role": "system", "content": system_prompt})

    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=conversation
    )

    reply = response.choices[0].message.content
    conversation.append({"role": "assistant", "content": reply})
    user_states[user_id] = conversation

    if any("سأقوم الآن بإعداد التقرير" in m["content"] for m in conversation):
        save_report_and_email(user_id)

    return jsonify({"reply": reply})

@app.route("/speak")
def speak():
    text = request.args.get("text", "")
    speech = openai.audio.speech.create(
        model="tts-1",
        voice="onyx",
        response_format="mp3",
        input=text
    )
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    temp.write(speech.read())
    temp.close()
    return send_file(temp.name, mimetype="audio/mpeg")

def save_report_and_email(user_id):
    doc = Document(template_path)
    conversation = user_states.get(user_id, [])
    user_texts = [msg["content"] for msg in conversation if msg["role"] == "user"]
    full_text = "\n".join(user_texts)

    for p in doc.paragraphs:
        if "{{content}}" in p.text:
            p.text = full_text
            p.runs[0].font.name = 'Dubai'
            p.runs[0]._element.rPr.rFonts.set(qn('w:eastAsia'), 'Dubai')
            p.runs[0].font.size = Pt(13)
            p.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT

    report_path = f"/tmp/report_{user_id}.docx"
    doc.save(report_path)
    send_email(report_path, final_email)

def send_email(filepath, to_email):
    msg = EmailMessage()
    msg["Subject"] = "تقرير هندسي جاهز"
    msg["From"] = os.getenv("EMAIL_USER")
    msg["To"] = to_email
    msg.set_content("تم إعداد التقرير الفني المرفق من خلال المساعد الذكي.")

    with open(filepath, "rb") as f:
        file_data = f.read()
        file_name = os.path.basename(filepath)
        msg.add_attachment(file_data, maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename=file_name)

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.starttls()
        smtp.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
        smtp.send_message(msg)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
