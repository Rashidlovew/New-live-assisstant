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

async function startRecording() {
  if (isRecording) {
    console.log("🎤 Recording already in progress, returning.");
    return;
  }

  // Reset audio playback state from previous turn
  try {
    audioPlayback.pause();
    audioPlayback.src = "";
    audioPlayback.onended = null;
  } catch (e) {
    console.warn("Audio playback reset warning:", e); // Non-critical, log and continue
  }

  isRecording = true;
  statusDiv.innerText = "🔴 جاري التسجيل...";
  generateBtn.disabled = true; // Disable during recording phase

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    console.error("🎤 getUserMedia error:", err);
    if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
      statusDiv.innerText = "⚠️ لم يتم العثور على ميكروفون. يرجى توصيل ميكروفون والمحاولة مرة أخرى.";
    } else if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
      statusDiv.innerText = "⚠️ تم رفض إذن الوصول إلى الميكروفون. يرجى تمكين الأذونات في إعدادات المتصفح.";
    } else {
      statusDiv.innerText = "⚠️ تعذر الوصول إلى الميكروفون. يرجى التحقق من الأذونات والمحاولة مرة أخرى.";
    }
    isRecording = false;
    return; // Stop execution if microphone access fails
  }

  try {
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      // When recording stops, release the stream tracks to turn off mic indicator
      stream.getTracks().forEach(track => track.stop());

      statusDiv.innerText = "📤 جاري المعالجة...";
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      const formData = new FormData();
      formData.append('file', audioBlob, 'recording.webm');

      try {
        const transcribeRes = await fetch("/transcribe", { method: "POST", body: formData });
        if (!transcribeRes.ok) throw new Error(`Transcription error: ${transcribeRes.statusText}`);
        const transcribeData = await transcribeRes.json();
        if (transcribeRes.status >= 400 || transcribeData.error) throw new Error(`Transcription failed: ${transcribeData.error || 'Server error'}`);


        const chatRes = await fetch("/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, message: transcribeData.text })
        });
        if (!chatRes.ok) throw new Error(`Chat API error: ${chatRes.statusText}`);
        const chatData = await chatRes.json();
        if (chatRes.status >= 400 || chatData.error) throw new Error(`Chat API failed: ${chatData.error || 'Server error'}`);


        const speakRes = await fetch("/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: chatData.reply })
        });
        if (!speakRes.ok) throw new Error(`TTS error: ${speakRes.statusText}`);

        const speakBlob = await speakRes.blob();
        const audioUrl = URL.createObjectURL(speakBlob);
        audioPlayback.src = audioUrl;

        try {
          await audioPlayback.play();
          statusDiv.innerText = chatData.reply;
        } catch (playErr) {
          console.error("⏯️ Audio playback error:", playErr);
          statusDiv.innerText = "⚠️ حدث خطأ أثناء تشغيل صوت الرد. حاول مرة أخرى.";
          isRecording = false;
          return;
        }

        audioPlayback.onended = () => {
          audioPlayback.onended = null; // Prevent multiple calls
          isRecording = false; // Reset recording state before deciding to re-record or stop
          if (!chatData.reply.includes("تم استلام جميع البيانات")) {
            setTimeout(() => startRecording(), 800);
          } else {
            statusDiv.innerText = chatData.reply + "\n✅ جاهز لإنشاء التقرير.";
            generateBtn.disabled = false;
            isRecording = false;
          }
        };

      } catch (err) {
        console.error("❌ Error in onstop processing:", err);
        statusDiv.innerText = `⚠️ حدث خطأ: ${err.message}. حاول مرة أخرى.`;
        isRecording = false;
      }
    }; // End of onstop

    mediaRecorder.start();
    setTimeout(() => {
      if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
      }
    }, 10000); // Stop recording after 10 seconds (changed from 5000)

  } catch (err) {
    console.error("🎤 MediaRecorder setup error:", err);
    statusDiv.innerText = "⚠️ خطأ في إعداد مسجل الصوت. حاول تحديث الصفحة.";
    isRecording = false;
    if (stream) { // Clean up stream if MediaRecorder setup failed
        stream.getTracks().forEach(track => track.stop());
    }
    return;
  }
}

async function generateReport() {
  generateBtn.disabled = true;
  statusDiv.innerText = "⏳ جاري إنشاء التقرير...";
  try {
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
    document.body.appendChild(link); // Required for Firefox
    link.click();
    document.body.removeChild(link); // Clean up
    statusDiv.innerText = "✅ تم إنشاء التقرير بنجاح وجاري تنزيله.";
  } catch (err) {
    console.error("❌ Generate error:", err);
    statusDiv.innerText = `⚠️ فشل إنشاء التقرير: ${err.message}.`;
  } finally {
     generateBtn.disabled = false;
  }
}

window.onload = () => {
  statusDiv.innerText = "👋 أهلاً بك! اضغط على الشاشة أو انتظر لبدء المحادثة الصوتية.";
  const startListener = () => {
    document.body.removeEventListener('click', startListener);
    document.body.removeEventListener('keydown', startListener);
    if (!isRecording && !mediaRecorder) {
      startRecording();
    }
  };
  document.body.addEventListener('click', startListener);
  document.body.addEventListener('keydown', startListener);

  setTimeout(() => {
    document.body.removeEventListener('click', startListener);
    document.body.removeEventListener('keydown', startListener);
    if (!isRecording && !mediaRecorder) {
       console.log("⏰ Automatic conversation start initiated.");
       startRecording();
    }
  }, 2500);
};
