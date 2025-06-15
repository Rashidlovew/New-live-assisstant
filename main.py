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
    "Date": "🎙️ لنبدأ بالتاريخ، متى وقع الحادث تقريبًا؟",
    "Briefing": "🎙️ شكرًا لك. والآن، هل يمكنك أن تعطيني موجزًا لما حدث؟",
    "LocationObservations": "🎙️ أرسل معاينة الموقع حيث بمعاينة موقع الحادث تبين ما يلي .....",
    "Examination": "🎙️ أرسل نتيجة الفحص الفني ... حيث بفحص موضوع الحادث تبين ما يلي .....",
    "Outcomes": "🎙️ أرسل النتيجة حيث أنه بعد المعاينة و أجراء الفحوص الفنية اللازمة تبين ما يلي:.",
    "TechincalOpinion": "🎙️ أرسل الرأي الفني."
}

sessions = {}

system_prompt = (
    "أنتِ مساعد AI متخصص في قسم الهندسة الجنائية، صوتك طبيعي ودافئ، وأسلوبك يجمع بين المهنية والتعاطف العميق."
    " مهمتك الأساسية هي مساعدة المستخدم في تقديم معلومات لتقرير فني، ولكن الأهم من ذلك هو أن يشعر المستخدم بالدعم والراحة خلال هذه العملية."

    "**بدء المحادثة:**"
    "ابدئي المحادثة بتحية ودية ومبادرة إنسانية بسيطة. على سبيل المثال: 'مرحباً بك، أنا هنا لمساعدتك في إعداد تقريرك. قبل أن نبدأ في التفاصيل، كيف حالك اليوم؟' أو 'أهلاً بك، أفهم أنك بحاجة لتقديم معلومات لتقرير. أود أن أطمئن عليك أولاً، أتمنى أن تكون بخير.' انتظري رد المستخدم على هذا المدخل الأولي، وتفاعلي معه بشكل مناسب ومختصر."
    "بعد هذا التفاعل الأولي، انتقلي لطلب أول معلومة بشكل سلس, وهي تاريخ الحادث, مستخدمة كنقطة انطلاق \"لنبدأ بالتاريخ، متى وقع الحادث تقريبًا؟\" ولكن بصياغتك الطبيعية. يجب أن تذكري كلمة 'التاريخ' أو 'تاريخ الحادث' عند طلب هذه المعلومة لأول مرة."

    "**جمع المعلومات:**"
    "عندما يحين وقت جمع المعلومات، تجنبي تمامًا أسلوب طرح الأسئلة المباشرة والمتتالية كأنكِ تملئين قائمة. هدفك هو أن تدمجي طلب المعلومات ضمن حوار طبيعي ومتدفق."
    "لكل معلومة يقدمها المستخدم (مثلاً عن 'التاريخ'):"
    "1. قدمي إقرارًا واضحًا وموجزًا بما قاله المستخدم (مثلاً: 'حسنًا، تاريخ الواقعة هو [التاريخ الذي ذكره المستخدم].')."
    "2. إذا كانت إجابته مختصرة جدًا أو غير واضحة، اطرحي سؤال متابعة مفتوح لتستوضحي أكثر عن *نفس النقطة* قبل الانتقال (مثلاً: 'هل يمكنك توضيح هذه النقطة أكثر قليلاً؟')."
    "3. إذا كانت المعلومة واضحة، أو بعد الاستيضاح، قدمي تعليقًا قصيرًا يُظهر التعاطف أو الاهتمام (مثلاً: 'شكرًا لك على توضيح ذلك.' أو 'أتفهم أن تذكر هذه التفاصيل قد يكون صعبًا.') ثم انتقلي بلطف لطلب المعلومة التالية."
    "مثال للانتقال: 'شكرًا لمشاركتنا هذه المعلومة. عندما تكون مستعدًا، هل يمكننا التحدث قليلاً عن [اسم الحقل التالي بصيغة طبيعية، مثلاً \"ملخص الحادث\" بدلاً من Briefing]؟' أو 'أتفهم. الآن، إذا سمحت، ننتقل إلى [اسم الحقل التالي بصيغة طبيعية].'"
    "عند طلب معلومة جديدة، استخدمي نص السؤال من `field_prompts` كدليل للمعنى المطلوب ولكن أعيدي صياغته بأسلوبك الحواري الطبيعي بدلاً من ترديده حرفياً."

    "**الأسلوب العام:**"
    "حافظي على هدوئك وصبرك طوال المحادثة. شجعي المستخدم على التحدث بحرية، وأكدي له أن بإمكانه أخذ وقته."
    "تذكري، أنتِ لستِ مجرد آلة لجمع البيانات، بل مساعد متعاطف. يجب أن يشعر المستخدم أنه يتحدث مع شخص يهتم به حقًا."
    "يجب جمع المعلومات للحقول التالية بالترتيب: Date, Briefing, LocationObservations, Examination, Outcomes, TechincalOpinion."
    "عندما يتم جمع كل الحقول بنجاح، قومي بتأكيد استلام المعلومة الأخيرة، ثم أعلني بشكل واضح وودي عن اكتمال جمع البيانات وأن التقرير سيتم إعداده (مثلاً: 'شكرًا جزيلاً لك على كل هذه المعلومات. ✅ لقد تم استلام جميع البيانات اللازمة. سأقوم الآن بإعداد التقرير لك...')."
    "استخدمي هذه التعليمات في كل رد من ردودك لضمان تجربة سلسة وداعمة للمستخدم."
)


def generate_response(messages):
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.7
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
            "current": 0,
            "chat_state": "greeting"
        }
        if not user_message:
            user_message = "(بدأ المستخدم المحادثة)"

    session = sessions[user_id]
    messages = session["messages"]
    messages.append({"role": "user", "content": user_message})

    reply_content = ""

    if session.get("chat_state") == "greeting":
        print(f"DEBUG: UserID {user_id} in 'greeting' state. User message: '{user_message}'")
        reply_content = generate_response(messages)

        # Transition condition: AI's reply asks for the first field ("Date").
        # System prompt guides AI: "...انتقلي لطلب أول معلومة بشكل سلس, وهي تاريخ الحادث..."
        # Check if AI's reply contains keywords indicating it's asking for the date.
        # Keywords are based on field_prompts["Date"] and system_prompt guidance.
        first_field_keywords = ["التاريخ", "تاريخ الحادث", "متى وقع", field_prompts["Date"]]
        if any(keyword in reply_content for keyword in first_field_keywords) and session["current"] == 0:
            session["chat_state"] = "collecting_data"
            print(f"DEBUG: UserID {user_id} Transitioned to 'collecting_data'. AI reply: '{reply_content}'")
        else:
            print(f"DEBUG: UserID {user_id} Staying in 'greeting'. AI reply: '{reply_content}'")
        # No data storage or session["current"] increment in greeting state.

    elif session.get("chat_state") == "collecting_data":
        print(f"DEBUG: UserID {user_id} in 'collecting_data' state for field index {session['current']}. User message: '{user_message}'")
        if session["current"] < len(field_order):
            current_field_key = field_order[session["current"]]
            session["fields"][current_field_key] = user_message
            print(f"DEBUG: UserID {user_id} Stored user_message='{user_message}' for field='{current_field_key}' at index={session['current']}")
        else:
            # This case should ideally not be hit if logic is correct, means trying to store data when all fields are notionally done.
            print(f"DEBUG: UserID {user_id} Warning: In 'collecting_data' but session['current'] ({session['current']}) is out of bounds.")

        reply_content = generate_response(messages)

        # Increment current *after* data for current_field_key is stored and AI has replied.
        # This means the *next* user input will be for the *new* session["current"].
        if session["current"] < len(field_order): # Only advance if current index is valid
            # Check if data was actually stored for the field we were expecting.
            # This ensures we only advance if the user provided data for the *expected* field.
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
            else:
                print(f"DEBUG: UserID {user_id} Data for field {current_field_key_just_processed} not stored or mismatch; not advancing session['current'].")
        else:
             print(f"DEBUG: UserID {user_id} session['current'] ({session['current']}) already past end of field_order or invalid.")


    elif session.get("chat_state") == "completed":
        print(f"DEBUG: UserID {user_id} in 'completed' state. User message: '{user_message}'")
        # If the conversation is 'completed', the AI should ideally just give polite closing remarks.
        # Or, we could prevent further processing/LLM calls if strict completion is desired.
        # For now, let it respond. System prompt guides it to give a final message.
        reply_content = generate_response(messages)

    else: # Should not happen
        print(f"ERROR: UserID {user_id} Unknown chat_state: {session.get('chat_state')}")
        reply_content = "حدث خطأ غير متوقع في النظام."


    messages.append({"role": "assistant", "content": reply_content})
    return jsonify({"reply": reply_content})

# ... (rest of the file remains the same) ...

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
