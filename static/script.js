// === New script.js with automatic voice turn-taking and natural conversation ===
let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let userId = localStorage.getItem("user_id") || crypto.randomUUID();
localStorage.setItem("user_id", userId);

const statusDiv = document.getElementById("status");
const audioPlayback = document.getElementById("audioPlayback");
const generateBtn = document.getElementById("generateBtn");
generateBtn.disabled = true;

function logTIMESTAMP(message, ...args) {
    const now = new Date();
    // Simple ISO-like format: YYYY-MM-DD HH:MM:SS.mmm
    const timestamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}.${String(now.getMilliseconds()).padStart(3, '0')}`;
    if (args.length > 0) {
        console.log(`[${timestamp}] ${message}`, ...args);
    } else {
        console.log(`[${timestamp}] ${message}`);
    }
}

async function startRecording() {
  logTIMESTAMP("startRecording() called. Current isRecording:", isRecording);

  if (isRecording) {
    logTIMESTAMP("🎤 startRecording: Recording already in progress, returning.");
    return;
  }

  logTIMESTAMP("startRecording: Before audioPlayback reset. onended is:", audioPlayback.onended ? "set" : "null");
  try {
    audioPlayback.pause();
    audioPlayback.src = "";
    audioPlayback.onended = null;
  } catch (e) {
    console.warn("Audio playback reset warning:", e); // Non-critical
  }
  logTIMESTAMP("startRecording: After audioPlayback reset. onended is:", audioPlayback.onended ? "set" : "null");

  isRecording = true;
  mediaRecorder = null; // Explicitly nullify before trying to set up a new one
  audioChunks = [];     // Ensure audioChunks is also reset here

  statusDiv.innerText = "🔴 جاري التسجيل...";
  generateBtn.disabled = true;

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    logTIMESTAMP("🎤 startRecording: getUserMedia successful.");
  } catch (err) {
    logTIMESTAMP("🎤 startRecording: getUserMedia FAILED.", err);
    if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
      statusDiv.innerText = "⚠️ لم يتم العثور على ميكروفون. يرجى توصيل ميكروفون والمحاولة مرة أخرى.";
    } else if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
      statusDiv.innerText = "⚠️ تم رفض إذن الوصول إلى الميكروفون. يرجى تمكين الأذونات في إعدادات المتصفح.";
    } else {
      statusDiv.innerText = "⚠️ تعذر الوصول إلى الميكروفون. يرجى التحقق من الأذونات والمحاولة مرة أخرى.";
    }
    isRecording = false;
    return;
  }

  try {
    mediaRecorder = new MediaRecorder(stream); // This is where the new instance is created
    logTIMESTAMP("🎤 startRecording: MediaRecorder instantiated successfully.");
    // audioChunks = []; // Moved up to be with mediaRecorder = null for clarity

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      logTIMESTAMP("🎤 mediaRecorder.onstop called.");
      stream.getTracks().forEach(track => track.stop());
      logTIMESTAMP("🎤 mediaRecorder.onstop: Microphone stream tracks stopped.");

      statusDiv.innerText = "📤 جاري المعالجة...";
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      const formData = new FormData();
      formData.append('file', audioBlob, 'recording.webm');

      try {
        logTIMESTAMP("🎤 mediaRecorder.onstop: Before fetch /transcribe.");
        const transcribeRes = await fetch("/transcribe", { method: "POST", body: formData });
        if (!transcribeRes.ok) {
            logTIMESTAMP("🎤 mediaRecorder.onstop: fetch /transcribe FAILED.", transcribeRes.statusText);
            throw new Error(`Transcription error: ${transcribeRes.statusText}`);
        }
        const transcribeData = await transcribeRes.json();
        logTIMESTAMP("🎤 mediaRecorder.onstop: fetch /transcribe successful.", transcribeData);
        if (transcribeRes.status >= 400 || transcribeData.error) {
            logTIMESTAMP("🎤 mediaRecorder.onstop: Transcription API reported error.", transcribeData.error);
            throw new Error(`Transcription failed: ${transcribeData.error || 'Server error'}`);
        }

        logTIMESTAMP("🎤 mediaRecorder.onstop: Before fetch /chat.");
        const chatRes = await fetch("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, message: transcribeData.text })
        });
        if (!chatRes.ok) {
            logTIMESTAMP("🎤 mediaRecorder.onstop: fetch /chat FAILED.", chatRes.statusText);
            throw new Error(`Chat API error: ${chatRes.statusText}`);
        }
        const chatData = await chatRes.json();
        logTIMESTAMP("🎤 mediaRecorder.onstop: fetch /chat successful. chatData.reply:", chatData.reply);
        if (chatRes.status >= 400 || chatData.error) {
            logTIMESTAMP("🎤 mediaRecorder.onstop: Chat API reported error.", chatData.error);
            throw new Error(`Chat API failed: ${chatData.error || 'Server error'}`);
        }

        logTIMESTAMP("🎤 mediaRecorder.onstop: Before fetch /speak.");
        const speakRes = await fetch("/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: chatData.reply })
        });
        if (!speakRes.ok) {
            logTIMESTAMP("🎤 mediaRecorder.onstop: fetch /speak FAILED.", speakRes.statusText);
            throw new Error(`TTS error: ${speakRes.statusText}`);
        }
        logTIMESTAMP("🎤 mediaRecorder.onstop: fetch /speak successful.");

        const speakBlob = await speakRes.blob();
        const audioUrl = URL.createObjectURL(speakBlob);
        audioPlayback.src = audioUrl;

        logTIMESTAMP("🎤 mediaRecorder.onstop: Before audioPlayback.play().");
        try {
          await audioPlayback.play();
          logTIMESTAMP("⏯️ audioPlayback.play() successful. Setting onended handler. chatData.reply:", chatData.reply);
          statusDiv.innerText = chatData.reply;
        } catch (playErr) {
          logTIMESTAMP("⏯️ audioPlayback.play() FAILED. Error:", playErr, "Current isRecording:", isRecording);
          statusDiv.innerText = "⚠️ حدث خطأ أثناء تشغيل صوت الرد. حاول مرة أخرى.";
          isRecording = false;
          return;
        }

        audioPlayback.onended = () => {
          logTIMESTAMP("⏯️ audioPlayback.onended handler EXECUTED. Current isRecording (before reset):", isRecording);
          audioPlayback.onended = null;
          isRecording = false;
          logTIMESTAMP("⏯️ audioPlayback.onended: isRecording set to false.");
          if (!chatData.reply.includes("تم استلام جميع البيانات")) {
            logTIMESTAMP("⏯️ audioPlayback.onended: Condition to re-record is TRUE. Scheduling startRecording(). chatData.reply:", chatData.reply);
            setTimeout(() => {
                logTIMESTAMP("⏯️ audioPlayback.onended: setTimeout EXECUTED, now calling startRecording().");
                startRecording();
            }, 800);
          } else {
            logTIMESTAMP("⏯️ audioPlayback.onended: Condition to re-record is FALSE. Conversation ended. chatData.reply:", chatData.reply);
            statusDiv.innerText = chatData.reply + "\n✅ جاهز لإنشاء التقرير.";
            generateBtn.disabled = false;
            isRecording = false;
          }
        };

      } catch (err) {
        logTIMESTAMP("❌ Error in onstop processing:", err, "Current isRecording:", isRecording);
        statusDiv.innerText = `⚠️ حدث خطأ: ${err.message}. حاول مرة أخرى.`;
        isRecording = false;
      }
    }; // End of onstop

    mediaRecorder.start(); // This is where MediaRecorder is actually started.
    logTIMESTAMP("🎤 startRecording: mediaRecorder.start() called.");
    setTimeout(() => {
      if (mediaRecorder && mediaRecorder.state === "recording") {
        logTIMESTAMP("🎤 startRecording: setTimeout stopping mediaRecorder.");
        mediaRecorder.stop();
      }
    }, 10000);
    logTIMESTAMP("🎤 startRecording: setTimeout for mediaRecorder.stop() set for 10000ms.");

  } catch (err) {
    logTIMESTAMP("🎤 startRecording: MediaRecorder setup or start FAILED.", err);
    statusDiv.innerText = "⚠️ خطأ في إعداد مسجل الصوت. حاول تحديث الصفحة.";
    isRecording = false;
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
    }
    return;
  }
}

async function generateReport() {
  logTIMESTAMP("generateReport() called.");
  generateBtn.disabled = true;
  statusDiv.innerText = "⏳ جاري إنشاء التقرير...";
  try {
    // ... (generateReport logic remains, can add more logs if needed)
    const sessionRes = await fetch(`/get-session?user_id=${userId}`);
    if (!sessionRes.ok) throw new Error(`Session fetch error: ${sessionRes.statusText}`);
    const sessionData = await sessionRes.json();

    const generateRes = await fetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields: sessionData.fields })
    });
    if (!generateRes.ok) throw new Error(`Report generation error: ${generateRes.statusText}`);

    const blob = await generateRes.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "تقرير_هندسي.docx";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    statusDiv.innerText = "✅ تم إنشاء التقرير بنجاح وجاري تنزيله.";
    logTIMESTAMP("generateReport() successful.");
  } catch (err) {
    logTIMESTAMP("❌ generateReport() FAILED.", err);
    statusDiv.innerText = `⚠️ فشل إنشاء التقرير: ${err.message}.`;
  } finally {
     generateBtn.disabled = false;
  }
}

window.onload = () => {
  logTIMESTAMP("window.onload called.");
  statusDiv.innerText = "👋 أهلاً بك! اضغط على الشاشة أو انتظر لبدء المحادثة الصوتية.";
  const startListener = () => {
    logTIMESTAMP("startListener (click/keydown) triggered.");
    document.body.removeEventListener('click', startListener);
    document.body.removeEventListener('keydown', startListener);
    if (!isRecording && !mediaRecorder) {
      logTIMESTAMP("startListener: Conditions met, calling startRecording().");
      startRecording();
    } else {
      logTIMESTAMP("startListener: Conditions NOT met. isRecording:", isRecording, "mediaRecorder:", mediaRecorder);
    }
  };
  document.body.addEventListener('click', startListener);
  document.body.addEventListener('keydown', startListener);

  setTimeout(() => {
    logTIMESTAMP("window.onload: setTimeout for initial startRecording triggered.");
    document.body.removeEventListener('click', startListener); // Ensure listeners are removed even if timeout fires first
    document.body.removeEventListener('keydown', startListener);
    if (!isRecording && !mediaRecorder) {
       logTIMESTAMP("⏰ Automatic conversation start initiated via setTimeout.");
       startRecording();
    } else {
      logTIMESTAMP("⏰ Automatic conversation start: Conditions NOT met. isRecording:", isRecording, "mediaRecorder:", mediaRecorder);
    }
  }, 2500);
};
