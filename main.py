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

# Reverted field_prompts to be more direct
field_prompts = {
    "Date": "🎙️ أرسل تاريخ الواقعة.",
    "Briefing": "🎙️ أرسل موجز الواقعة.",
    "LocationObservations": "🎙️ أرسل معاينة الموقع حيث بمعاينة موقع الحادث تبين ما يلي .....",
    "Examination": "🎙️ أرسل نتيجة الفحص الفني ... حيث بفحص موضوع الحادث تبين ما يلي .....",
    "Outcomes": "🎙️ أرسل النتيجة حيث أنه بعد المعاينة و أجراء الفحوص الفنية اللازمة تبين ما يلي:.",
    "TechincalOpinion": "🎙️ أرسل الرأي الفني."
}

sessions = {}

# New direct system_prompt
system_prompt = (
    "أنت مساعد AI متخصص في قسم الهندسة الجنائية. مهمتك هي جمع المعلومات اللازمة لإعداد تقرير فني بكفاءة ومهنية."
    " ستطرح الأسئلة على المستخدم حقلًا تلو الآخر."
    " عند بدء المحادثة لأول مرة (عندما يكون تاريخ الرسائل فارغًا باستثناء رسالة النظام هذه ورسالة المستخدم الأولى), يجب أن يكون ردك الأول هو طلب المعلومة الأولى مباشرة وهي 'تاريخ الحادث'. استخدم صياغة مثل: 'أنا هنا لمساعدتك في إعداد تقرير الهندسة الجنائية. لنبدأ، يرجى تقديم تاريخ الحادث.'"
    " لكل معلومة يقدمها المستخدم بعد ذلك، قم بتأكيد مقتضب (مثال: 'تم تسجيل التاريخ.') ثم انتقل مباشرة لطلب المعلومة التالية بالترتيب المحدد."
    " إذا كانت إجابة المستخدم غير واضحة، اطلب منه التوضيح بلطف ثم كرر طلب نفس المعلومة قبل المتابعة."
    " يجب جمع المعلومات للحقول التالية بالترتيب: Date, Briefing, LocationObservations, Examination, Outcomes, TechincalOpinion."
    " عند استلام جميع الحقول، أعلن عن اكتمال جمع البيانات وأن التقرير سيتم إعداده، مثلاً: 'شكراً لك، تم استلام جميع البيانات. يتم الآن إعداد التقرير.'"
    " مثال لطلب معلومة تالية: 'الآن، يرجى تقديم موجز للحادث.'"
)


def generate_response(messages):
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.5 # Adjusted temperature for more directness
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
        transcript_response = openai.audio.transcriptions.create(model="whisper-1", file=f)
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
            "current": 0, # Starts at 0, expecting "Date"
            "chat_state": "collecting_data" # Start directly in collecting_data state
        }
        if not user_message:
            user_message = "(بدأ المستخدم المحادثة)"
        print(f"DEBUG: UserID {user_id} New session. Initial user_message: '{user_message}'. State: {sessions[user_id]['chat_state']}")

    session = sessions[user_id]
    messages = session["messages"]

    should_store_data = True
    if len(messages) == 1:
        should_store_data = False
        print(f"DEBUG: UserID {user_id} First effective user interaction. Not storing this message as field data. User message: '{user_message}'")

    messages.append({"role": "user", "content": user_message})
    reply_content = ""

    if session.get("chat_state") == "collecting_data":
        print(f"DEBUG: UserID {user_id} In 'collecting_data' state for field index {session['current']}. User message: '{user_message}'")

        if should_store_data and session["current"] < len(field_order):
            current_field_key = field_order[session["current"]]
            session["fields"][current_field_key] = user_message
            print(f"DEBUG: UserID {user_id} Stored user_message='{user_message}' for field='{current_field_key}' at index={session['current']}")
        elif not should_store_data:
            print(f"DEBUG: UserID {user_id} In 'collecting_data' but should_store_data is false. Not storing. This is likely the initial user utterance before AI asks for first field.")
        else:
             print(f"DEBUG: UserID {user_id} Warning: In 'collecting_data' but session['current'] ({session['current']}) is out of bounds for storing.")

        reply_content = generate_response(messages)

        if should_store_data and session["current"] < len(field_order):
            current_field_key_just_processed = field_order[session["current"]]
            if current_field_key_just_processed in session["fields"] and \
               session["fields"].get(current_field_key_just_processed) == user_message:

                if session["current"] < len(field_order) - 1:
                    session["current"] += 1
                    print(f"DEBUG: UserID {user_id} Advanced session current to {session['current']} for field {field_order[session['current']]}")
                elif session["current"] == len(field_order) - 1:
                    session["current"] += 1
                    session["chat_state"] = "completed"
                    print(f"DEBUG: UserID {user_id} All fields processed. session current is now {session['current']}. State: {session['chat_state']}.")

    elif session.get("chat_state") == "completed":
        print(f"DEBUG: UserID {user_id} in 'completed' state. User message: '{user_message}'")
        reply_content = generate_response(messages)
    else:
        print(f"ERROR: UserID {user_id} Unknown chat_state: {session.get('chat_state')}")
        reply_content = "حدث خطأ غير متوقع في النظام."

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
            "similarity_boost": 0.85,
            "speed": 1.3
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
    print(f"DEBUG: /generate received fields: {fields}")

    if not fields:
        print("DEBUG: /generate called with no fields data.")
        # For robust handling, ensure fields is at least an empty dict if None
        fields = {}

    doc = Document("police_report_template.docx") # Load template

    keys_replaced_in_doc = set()

    for paragraph in doc.paragraphs:
        # It's important to handle potential splits of placeholders across multiple runs.
        # A simple way is to buffer paragraph text and replace, then clear and rewrite runs.
        # However, to stick to run-level iteration as in original code:
        for key, val in fields.items():
            placeholder = f"{{{{{key}}}}}"
            # Check and replace in the paragraph's full text first to handle placeholders potentially split across runs.
            # This is complex with python-docx as run text needs to be modified directly.
            # The current loop structure might miss placeholders split across runs or format them inconsistently.
            # For now, sticking to run-by-run replacement logic from original and adding logging.

            # Log presence of key in paragraph text before diving into runs
            if placeholder in paragraph.text:
                print(f"DEBUG: Placeholder '{placeholder}' found in paragraph: \"{paragraph.text[:100]}...\"")

            for run in paragraph.runs:
                if placeholder in run.text:
                    initial_run_text = run.text
                    # Ensure val is a string; if None, replace with empty string
                    replacement_value = str(val) if val is not None else ""
                    run.text = run.text.replace(placeholder, replacement_value)

                    print(f"DEBUG: Key '{key}': Replaced placeholder in run. Original: '{initial_run_text}', New: '{run.text}'")
                    keys_replaced_in_doc.add(key)

                    # Apply formatting to the run that contained the placeholder
                    # Note: If placeholder was split, formatting might only apply to the first part.
                    # The paragraph style is set once if any replacement happens in it.
                    paragraph.paragraph_format.right_to_left = True
                    paragraph.alignment = 2 # WD_ALIGN_PARAGRAPH.RIGHT in docx.enum.text

                    run.font.name = 'Dubai'
                    try:
                        # Ensure rFonts is correctly accessed and set
                        rpr = run._element.get_or_add_rPr()
                        rFonts = rpr.get_or_add_rFonts()
                        rFonts.set(qn('w:eastAsia'), 'Dubai')
                        rFonts.set(qn('w:cs'), 'Dubai') # Also for complex script
                        rFonts.set(qn('w:ascii'), 'Dubai') # Ensure for ascii as well
                        rFonts.set(qn('w:hAnsi'), 'Dubai') # And high-ansi
                    except Exception as e:
                        print(f"DEBUG: Error applying font to run for key '{key}': {e}")
                    run.font.size = Pt(13)

    # Log keys from input `fields` that were not found/replaced
    for key_in_fields in fields.keys():
        if key_in_fields not in keys_replaced_in_doc:
            print(f"DEBUG: Key '{key_in_fields}' (value: '{fields[key_in_fields]}') from input fields was NOT found/replaced in the document. Check template placeholder: {{{{{key_in_fields}}}}}")

    output_path = os.path.join(tempfile.gettempdir(), "final_report.docx")
    doc.save(output_path)
    print(f"DEBUG: Report saved to {output_path}")
    # send_email_with_attachment(output_path) # Temporarily commented out
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
