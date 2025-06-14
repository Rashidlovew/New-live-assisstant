from flask import Flask, request, jsonify, send_file, render_template
import openai
import tempfile
import os
from docx import Document
from datetime import datetime
import smtplib
from email.message import EmailMessage
from werkzeug.utils import secure_filename

app = Flask(__name__, static_url_path='/static', static_folder='static', template_folder='templates')

openai.api_key = os.getenv("OPENAI_API_KEY")

field_prompts = {
    "greeting": "مرحباً، أنا المساعد الذكي من قسم الهندسة الجنائية. هنا لمساعدتك في إعداد تقريرك الفني بكل سلاسة.",
    "ice_breaker": "بس قبل ما نبدأ، حاب أسألك كيف كان يومك؟ إن شاء الله كل شيء طيب؟",
    "name": "تشرفت فيك، ممكن أعرف اسمك الكريم عشان أسجله في التقرير؟",
    "Date": "خلينا نبدأ بالتاريخ... متى كانت الواقعة؟",
    "Briefing": "ممتاز، ممكن تعطيني موجز بسيط عن الحادث؟",
    "LocationObservations": "وبخصوص المعاينة الميدانية، إيش لاحظت في موقع الحادث؟",
    "Examination": "ومن خلال فحصك الفني، وش تبين لك؟",
    "Outcomes": "وبعد المعاينة والفحص، ما هي النتيجة اللي وصلت لها؟",
    "TechincalOpinion": "وأخيرًا، ما هو رأيك الفني في هذه الحالة؟",
    "closing": "شكرًا لك {Investigator}، تم تسجيل كل المعلومات وسأقوم الآن بإعداد التقرير وإرساله للقسم المختص."
}

fields = ["name", "Date", "Briefing", "LocationObservations", "Examination", "Outcomes", "TechincalOpinion"]
session_data = {}
current_field_index = {}

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/transcribe", methods=["POST"])
def transcribe():
    audio = request.files['audio']
    user_id = request.form.get("user_id", "default_user")
    filename = secure_filename(audio.filename)
    path = os.path.join(tempfile.gettempdir(), filename)
    audio.save(path)

    with open(path, "rb") as f:
        transcript = openai.Audio.transcribe("whisper-1", f)["text"]

    response = handle_user_input(user_id, transcript)
    return jsonify({"reply": response})

@app.route("/speak", methods=["POST"])
def speak():
    text = request.json.get("text")
    response = openai.Audio.speech.create(
        model="tts-1",
        voice="onyx",
        input=text
    )
    audio_path = os.path.join(tempfile.gettempdir(), "response.mp3")
    with open(audio_path, "wb") as f:
        f.write(response.content)
    return send_file(audio_path, mimetype="audio/mpeg")

def handle_user_input(user_id, user_input):
    if user_id not in session_data:
        session_data[user_id] = {}
        current_field_index[user_id] = 0
        return field_prompts["greeting"]

    if len(session_data[user_id]) == 0:
        session_data[user_id]["ice"] = user_input
        return field_prompts["name"]

    current_index = current_field_index[user_id]
    if current_index >= len(fields):
        return "جاري إعداد التقرير..."

    field = fields[current_index]
    session_data[user_id][field] = user_input
    current_field_index[user_id] += 1

    if current_field_index[user_id] < len(fields):
        next_field = fields[current_field_index[user_id]]
        return field_prompts[next_field]
    else:
        generate_report(user_id)
        name = session_data[user_id].get("name", "")
        reply = field_prompts["closing"].replace("{Investigator}", name)
        return reply

def generate_report(user_id):
    data = session_data[user_id]
    template = Document("police_report_template.docx")

    replacements = {
        "{{Date}}": data.get("Date", ""),
        "{{Briefing}}": data.get("Briefing", ""),
        "{{LocationObservations}}": data.get("LocationObservations", ""),
        "{{Examination}}": data.get("Examination", ""),
        "{{Outcomes}}": data.get("Outcomes", ""),
        "{{TechincalOpinion}}": data.get("TechincalOpinion", ""),
        "{{Investigator}}": data.get("name", "")
    }

    for para in template.paragraphs:
        for key, val in replacements.items():
            if key in para.text:
                para.text = para.text.replace(key, val)

    temp_path = tempfile.mktemp(suffix=".docx")
    template.save(temp_path)
    send_email(temp_path, data.get("name", ""))

def send_email(doc_path, investigator_name):
    email = "frnreports@gmail.com"
    msg = EmailMessage()
    msg["Subject"] = f"تقرير فحص هندسي من {investigator_name}"
    msg["From"] = os.getenv("EMAIL_USER")
    msg["To"] = email
    msg.set_content(f"تم إعداد التقرير بواسطة {investigator_name}. مرفق طياً.")

    with open(doc_path, "rb") as f:
        file_data = f.read()
        msg.add_attachment(file_data, maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename="report.docx")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
        smtp.send_message(msg)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
