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

# Modified field_prompts
field_prompts = {
    "Date": "🎙️ لنبدأ بالتاريخ، متى وقع الحادث تقريبًا؟",
    "Briefing": "🎙️ شكرًا لك. والآن، هل يمكنك أن تعطيني موجزًا لما حدث؟",
    "LocationObservations": "🎙️ أرسل معاينة الموقع حيث بمعاينة موقع الحادث تبين ما يلي .....",
    "Examination": "🎙️ أرسل نتيجة الفحص الفني ... حيث بفحص موضوع الحادث تبين ما يلي .....",
    "Outcomes": "🎙️ أرسل النتيجة حيث أنه بعد المعاينة و أجراء الفحوص الفنية اللازمة تبين ما يلي:.",
    "TechincalOpinion": "🎙️ أرسل الرأي الفني."
}

sessions = {}

# Heavily revised system_prompt
system_prompt = (
    "أنتِ مساعد AI متخصص في قسم الهندسة الجنائية، صوتك طبيعي ودافئ، وأسلوبك يجمع بين المهنية والتعاطف العميق."
    " مهمتك الأساسية هي مساعدة المستخدم في تقديم معلومات لتقرير فني، ولكن الأهم من ذلك هو أن يشعر المستخدم بالدعم والراحة خلال هذه العملية."

    "**بدء المحادثة:**"
    "ابدئي المحادثة بتحية ودية ومبادرة إنسانية بسيطة. على سبيل المثال: 'مرحباً بك، أنا هنا لمساعدتك في إعداد تقريرك. قبل أن نبدأ في التفاصيل، كيف حالك اليوم؟' أو 'أهلاً بك، أفهم أنك بحاجة لتقديم معلومات لتقرير. أود أن أطمئن عليك أولاً، أتمنى أن تكون بخير.' انتظري رد المستخدم على هذا المدخل الأولي، وتفاعلي معه بشكل مناسب ومختصر."
    "بعد هذا التفاعل الأولي، انتقلي لطلب أول معلومة بشكل سلس, وهي تاريخ الحادث, مستخدمة كنقطة انطلاق \"لنبدأ بالتاريخ، متى وقع الحادث تقريبًا؟\" ولكن بصياغتك الطبيعية."

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
        temperature=0.7 # Slightly increased temperature for more conversational variance
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
        # For the very first message from the user (which is likely just an initial sound or empty),
        # the AI should respond with its initial greeting as per system_prompt.
        # We'll add the user's first message, then let generate_response craft the initial greeting.
        if not user_message: # Handle case where first user message might be empty if recording starts immediately
            user_message = "(بدأ المستخدم المحادثة)"


    session = sessions[user_id]
    messages = session["messages"]

    messages.append({"role": "user", "content": user_message})

    # Only store data if it's not the initial greeting phase.
    # The system_prompt asks the AI to have an initial exchange BEFORE asking for the first field.
    # So, `session["current"]` will be 0 when the AI is supposed to ask for "Date".
    # User's response to "Date" will be when `session["current"]` is 0.
    # This logic for storing fields seems okay, assuming the AI handles the initial interaction
    # and then asks for "Date", and the user's response to that is what gets stored.
    if session["current"] < len(field_order):
        # If the AI's last message was asking for a field, then this user_message is the answer.
        # This assumes the AI will not ask for a field during its initial greeting phase.
        # The system_prompt guides the AI to ask for "Date" *after* the initial exchange.
        # We need to ensure we don't store the user's response to "how are you?" as the "Date".

        # Heuristic: Check if the conversation history suggests a field was just asked.
        # This is getting complex. A simpler way: the AI must be guided by system_prompt.
        # If session["messages"] has more than just system and first user message, it means a field might have been asked.

        # Let's rely on the AI. If it's not asking for a field, it shouldn't be stored.
        # The `session["current"]` update logic below is key.
        # The user's response to the initial "how are you" should not result in `session["current"]` incrementing.

        # The current logic for incrementing `session["current"]` is:
        # - if session["current"] < len(field_order) - 1: session["current"] += 1
        # - elif session["current"] == len(field_order) - 1: session["current"] += 1
        # This means `session["current"]` increments *after* the LLM reply is generated.
        # The LLM reply is generated *after* the user message is appended.

        # If it's the very first *actual* user message (e.g. "I'm fine, thanks"),
        # the LLM should respond, and `session["current"]` should remain 0.
        # Only when the user provides the "Date" should `session["current"]` effectively prepare to move to 1.

        # The current logic for storing `session["fields"][current_field_key] = user_message`
        # happens *before* `reply_content` is generated and *before* `session["current"]` is incremented.
        # This means the user's response to "How are you?" could be stored in `session["fields"]["Date"]`
        # if `session["current"]` is 0. This needs adjustment.

        # Solution: We only store if the AI's *previous* message likely prompted for the current field.
        # Or, more simply, we only store if `messages` is beyond the initial greeting phase.
        # The system_prompt now asks AI to engage first, then request "Date".
        # So, the first user message is a reply to greeting. Second user message is the Date.

        # Store if messages length > 3 (system, user_greeting_reply, assistant_asks_for_date)
        # This means current user_message is an answer to a field.
        is_initial_greeting_phase = True
        if len(messages) > 3: # System, User (empty/greeting), Assistant (greeting), User (reply to greeting) ... now assistant asks for Date
             is_initial_greeting_phase = False

        if not is_initial_greeting_phase:
            current_field_key = field_order[session["current"]]
            session["fields"][current_field_key] = user_message
            # Log what's being stored for debugging
            print(f"Storing user_message='{user_message}' for field='{current_field_key}' at index={session['current']}")


    reply_content = generate_response(messages)

    # Determine if the AI is likely asking for a new field or has finished.
    # This logic helps advance `session["current"]` so the *next* user message is associated with the correct field.
    # This happens *after* the AI has responded.

    # If the AI's last message was its initial greeting, `session["current"]` should not advance.
    # If the AI just asked for "Date", `session["current"]` should still be 0 (pointing to "Date").
    # After user provides "Date", and AI acknowledges and asks for "Briefing", then `session["current"]` should advance to 1.

    # The crucial part from system_prompt:
    # "After this TEPID_RESPONSE_PLACEHOLDER exchange, move to ask for the first piece of information, which is the date of the incident..."
    # "If the info is clear...gently guide the conversation towards the next piece of information."

    # If the AI's response `reply_content` is asking for the *next* field, or concluding,
    # then we should advance `session["current"]`.
    # This is hard to determine programmatically.
    # The current increment logic might be too aggressive for the new conversational intro.

    # Revised logic for incrementing session["current"]:
    # Only increment if a field was likely processed in this turn.
    # A field is processed if:
    # 1. We are past the initial greeting phase.
    # 2. The user provided some input for the current field.
    # 3. The AI's response (`reply_content`) is likely an acknowledgement + request for next, or conclusion.

    # Let's assume the AI follows the prompt: if it got info for field `X` and it's clear, it will ask for `X+1`.
    # So, if we were expecting field `X` (current `session["current"]`), and user provided it,
    # and we are not in greeting phase, then the *next* expectation is `X+1`.

    # Condition for advancing: not in initial greeting phase, and we haven't collected all fields yet.
    can_advance_field = False
    if len(messages) > 3 and session["current"] < len(field_order) : # system, user, assistant_greeting, user_reply_to_greeting -> at least 4 messages means greeting is over
        # If we are here, user has replied to assistant.
        # If assistant's last message (reply_content) is not a clarifying question for the current field,
        # it means this field is considered done by the AI.
        # This is still hard. The system_prompt tells AI to ask clarifying Q *before* moving on.
        # So if AI is *not* asking clarifying Q for current field, it *is* moving on.

        # The simplest robust way is to trust the AI to follow the field_order.
        # If the user just provided data for `field_order[session["current"]]`,
        # and the AI's `reply_content` acknowledges it and moves to the next or concludes,
        # then `session["current"]` should be incremented.
        # The `is_initial_greeting_phase` check before storing data helps.

        # If we stored data for `session["fields"][field_order[session["current"]]]` this turn,
        # it means `user_message` was the data for that field.
        # Then, the AI's `reply_content` will be ack + next prompt OR ack + conclusion.
        # So, we should advance `session["current"]`.

        current_field_key_just_processed = field_order[session["current"]]
        if current_field_key_just_processed in session["fields"] and session["fields"][current_field_key_just_processed] == user_message:
             # This means user_message was indeed stored as data for the current field index.
             # So, we can advance the index for the *next* turn.
            if session["current"] < len(field_order) - 1:
                session["current"] += 1
                print(f"Advanced session current to {session['current']} for field {field_order[session['current']]}")
            elif session["current"] == len(field_order) - 1: # Was the last field
                session["current"] += 1 # Mark as completed
                print(f"All fields processed. session current is now {session['current']}")

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
