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
  if (isRecording) return;
  isRecording = true;
  statusDiv.innerText = "🔴 جاري التسجيل...";

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream);
  audioChunks = [];

  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) audioChunks.push(e.data);
  };

  mediaRecorder.onstop = async () => {
    statusDiv.innerText = "📤 جاري المعالجة...";
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.webm');

    try {
      const transcribeRes = await fetch("/transcribe", { method: "POST", body: formData });
      const transcribeData = await transcribeRes.json();

      const chatRes = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, message: transcribeData.text })
      });

      const chatData = await chatRes.json();
      const speakRes = await fetch("/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: chatData.reply })
      });

      if (!speakRes.ok) throw new Error("TTS error");

      const speakBlob = await speakRes.blob();
      const audioUrl = URL.createObjectURL(speakBlob);
      audioPlayback.src = audioUrl;
      audioPlayback.play();
      statusDiv.innerText = chatData.reply;

      // Listen again after playback ends
      audioPlayback.onended = () => {
        if (!chatData.reply.includes("تم استلام جميع البيانات")) {
          setTimeout(() => startRecording(), 800); // continue the conversation
        } else {
          generateBtn.disabled = false;
        }
      };

    } catch (err) {
      console.error("❌ Error:", err);
      statusDiv.innerText = "حدث خطأ. حاول مرة أخرى.";
      isRecording = false;
    }
  };

  mediaRecorder.start();
  setTimeout(() => mediaRecorder.stop(), 5000);
}

async function generateReport() {
  try {
    const sessionRes = await fetch(`/get-session?user_id=${userId}`);
    const sessionData = await sessionRes.json();

    const generateRes = await fetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields: sessionData.fields })
    });

    const blob = await generateRes.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "تقرير_هندسي.docx";
    link.click();
  } catch (err) {
    console.error("❌ Generate error:", err);
    statusDiv.innerText = "فشل إنشاء التقرير.";
  }
}

// Start initial conversation automatically
window.onload = () => {
  setTimeout(() => startRecording(), 2000);
};
