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
    "أنتِ مساعد ذكي من قسم الهندسة الجنائية، تتحدثين بصوت بشري طبيعي وبأسلوب مهني ودود ومتعاطف."
    " وظيفتك هي إجراء محادثة طبيعية لجمع معلومات لتقرير فني. لا تجعلي المستخدم يشعر كأنه يملأ استمارة."
    " لكل معلومة يقدمها المستخدم (مثلاً عن 'التاريخ')، ابدئي ردك بتأكيد موجز وطبيعي لهذه المعلومة (مثلاً: 'حسنًا، تاريخ الواقعة هو [التاريخ الذي ذكره المستخدم].')."
    " بعد ذلك، إذا كانت إجابة المستخدم عن الحقل الحالي مختصرة جدًا أو غير واضحة، اطرحي سؤال متابعة مفتوح لتستوضحي أكثر عن نفس الحقل قبل الانتقال لطلب معلومات عن الحقل التالي."
    " إذا كانت المعلومة واضحة، انتقلي بسلاسة لطلب المعلومة التالية حسب الترتيب المحدد."
    " استخدمي انتقالات عبورية لطيفة بين المواضيع المختلفة للتقرير."
    " هدفك هو جمع المعلومات للحقول التالية بالترتيب: Date, Briefing, LocationObservations, Examination, Outcomes, TechincalOpinion."
    " عندما يتم جمع كل الحقول بنجاح، قومي بتأكيد استلام المعلومة الأخيرة ثم أعلني بشكل واضح عن اكتمال جمع البيانات وأن التقرير سيتم إعداده (مثلاً: 'شكرًا لك، هذه هي كل المعلومات المطلوبة. ✅ تم استلام جميع البيانات. يتم الآن إعداد التقرير...')."
    " تذكري أن تستخدمي هذه التعليمات في كل رد."
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

    if session["current"] < len(field_order):
        current_field_key = field_order[session["current"]]
        session["fields"][current_field_key] = user_message

    reply_content = generate_response(messages)

    # Advance session["current"] if the LLM is expected to have moved on.
    # The system_prompt guides the LLM to ask for follow-ups on the *same* field if unclear.
    # If the LLM is satisfied, it moves to the next field or concludes.
    # We increment `session["current"]` to reflect the next field the user should be providing,
    # or to mark completion.
    # This happens *after* the user provides data for the current `session["current"]` index,
    # and *after* the LLM generates a response based on that.
    # The new `session["current"]` is what the *next* user message will be for.

    # Heuristic: if the LLM's reply does not seem to be a clarifying question about the field
    # we just collected data for, then we can assume it's time to move to the next field index.
    # For now, we will increment if the current field (before increment) is not the last one.
    # This relies heavily on the LLM following the prompt to ask for the next field in sequence.
    if session["current"] < len(field_order) - 1:
        # We've processed data for field `session["current"]`. If it's not the last field,
        # the LLM *should* be asking for `session["current"] + 1`. So, update `session["current"]`
        # to reflect that the *next* user input is for this new index.
        session["current"] += 1
    elif session["current"] == len(field_order) - 1:
        # We've processed data for the *last* field.
        # The LLM *should* be generating a concluding message.
        # Increment `session["current"]` to mark that all fields are done.
        session["current"] += 1 # Now session["current"] == len(field_order)

    messages.append({"role": "assistant", "content": reply_content})
    return jsonify({"reply": reply_content})

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
