from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import openai
import tempfile
import os
import requests
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.mime.text import MIMEText
import smtplib
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

openai.api_key = os.getenv("OPENAI_API_KEY")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")

field_order = [
    "Date", "Briefing", "LocationObservations",
    "Examination", "Outcomes", "TechincalOpinion"
]

field_prompts = {
    "Date": "🎙️ أرسل تاريخ الواقعة.",
    "Briefing": "🎙️ أرسل موجز الواقعة.",
    "LocationObservations": "🎙️ أرسل معاينة الموقع حيث بمعاينة موقع الحادث تبين ما يلي .....",
    "Examination": "🎙️ أرسل نتيجة الفحص الفني ... حيث بفحص موضوع الحادث تبين ما يلي .....",
    "Outcomes": "🎙️ أرسل النتيجة حيث أنه بعد المعاينة و أجراء الفحوص الفنية اللازمة تبين ما يلي:.",
    "TechincalOpinion": "🎙️ أرسل الرأي الفني."
}

sessions = {}

system_prompt = (
    "أنتِ مساعد ذكي من قسم الهندسة الجنائية، تتحدثين بصوت بشري طبيعي وبأسلوب مهني ودود."
    " وظيفتك التحدث مع المستخدم بشكل محاورة عامة وعفوية لجمع معلومات التقرير،"
    " حقلًا تلو الآخر دون أن يشعر المستخدم أن هناك نموذج يتم تعبئته."
    " شجعيه على الحديث بحرية، واطرحي أسئلة ذكية داخل السياق دون إزعاج."
    " لا تكرري نفس السؤال إذا أجاب، بل تابعي إلى الخطوة التالية بسلاسة."
    " تأكدي من جمع كل الحقول التالية: التاريخ، موجز الواقعة، معاينة الموقع، نتيجة الفحص، النتيجة، والرأي الفني."
)

def generate_response(messages):
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.6
    )
    return response.choices[0].message.content

@app.route("/transcribe", methods=["POST"])
def transcribe():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.mp3', '.mp4', '.mpeg', '.mpga', '.m4a', '.wav', '.webm', '.ogg']:
        return jsonify({'error': 'Unsupported file type'}), 400

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        file.save(tmp.name)
        audio_path = tmp.name

    with open(audio_path, "rb") as f:
        transcript_response = openai.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )

    os.remove(audio_path)
    return jsonify({"text": transcript_response.text})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_id = data.get("user_id")
    user_message = data.get("message")

    if user_id not in sessions:
        sessions[user_id] = {
            "messages": [{"role": "system", "content": system_prompt}],
            "fields": {},
            "current": 0
        }

    session = sessions[user_id]
    messages = session["messages"]
    messages.append({"role": "user", "content": user_message})

    current_field = field_order[session["current"]]
    session["fields"][current_field] = user_message

    session["current"] += 1
    if session["current"] < len(field_order):
        next_field = field_order[session["current"]]
        next_prompt = field_prompts[next_field]
        messages.append({"role": "assistant", "content": next_prompt})
        reply = next_prompt
    else:
        reply = "✅ تم استلام جميع البيانات. يتم الآن إعداد التقرير..."

    messages.append({"role": "assistant", "content": reply})
    return jsonify({"reply": reply})

@app.route("/speak", methods=["POST"])
def speak():
    data = request.get_json()
    text = data.get("text")

    if not text:
        return jsonify({"error": "No text provided"}), 400

    url = "https://api.elevenlabs.io/v1/text-to-speech/EXAVITQu4vr4xnSDxMaL"
    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.4,
            "similarity_boost": 0.85
        }
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code != 200:
        return jsonify({"error": "TTS failed", "details": response.text}), 500

    audio_path = os.path.join(tempfile.gettempdir(), "speech.mp3")
    with open(audio_path, "wb") as f:
        f.write(response.content)

    return send_file(audio_path, mimetype="audio/mpeg")

@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    fields = data.get("fields")

    doc = Document("police_report_template.docx")
    for paragraph in doc.paragraphs:
        for key, val in fields.items():
            if f"{{{{{key}}}}}" in paragraph.text:
                for run in paragraph.runs:
                    if f"{{{{{key}}}}}" in run.text:
                        run.text = run.text.replace(f"{{{{{key}}}}}", val)
                        paragraph.paragraph_format.right_to_left = True
                        paragraph.alignment = 2
                        run.font.name = 'Dubai'
                        run._element.rPr.rFonts.set(qn('w:eastAsia'), 'Dubai')
                        run.font.size = Pt(13)

    output_path = os.path.join(tempfile.gettempdir(), "final_report.docx")
    doc.save(output_path)
    send_email_with_attachment(output_path)
    return send_file(output_path, as_attachment=True)

def send_email_with_attachment(file_path):
    sender_email = os.getenv("SENDER_EMAIL")
    receiver_email = os.getenv("RECEIVER_EMAIL")
    password = os.getenv("EMAIL_PASSWORD")

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = "📄 تقرير جديد من المساعد الذكي"
    msg.attach(MIMEText("تم إرفاق التقرير الفني الذي تم إنشاؤه تلقائيًا.", 'plain'))

    with open(file_path, "rb") as attachment:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(file_path)}')
        msg.attach(part)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(sender_email, password)
        server.send_message(msg)

@app.route("/get-session", methods=["GET"])
def get_session():
    user_id = request.args.get("user_id")
    session = sessions.get(user_id)
    if session:
        return jsonify(session)
    return jsonify({"error": "Session not found"}), 404

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
