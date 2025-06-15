let mediaRecorder;
let audioChunks = [];
let isRecording = false;

const statusDiv = document.getElementById("status");
const audioPlayback = document.getElementById("audioPlayback");

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
      const transcribeRes = await fetch("/transcribe", {
        method: "POST",
        body: formData
      });

      const transcribeData = await transcribeRes.json();
      console.log("📝 النص:", transcribeData.text); // للتأكد

      // ✅ استخدم النص من transcribeData.text وليس reply
      const speakRes = await fetch("/speak", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: transcribeData.text })
      });

      const speakBlob = await speakRes.blob();
      const audioUrl = URL.createObjectURL(speakBlob);

      audioPlayback.src = audioUrl;
      audioPlayback.play();
      statusDiv.innerText = transcribeData.text;

    } catch (error) {
      console.error("❌ Error:", error);
      statusDiv.innerText = "حدث خطأ. حاول مجددًا.";
    } finally {
      isRecording = false;
    }
  };

  mediaRecorder.start();
  setTimeout(() => mediaRecorder.stop(), 5000);
}
