// Updated script.js for smart Arabic voice assistant

let mediaRecorder;
let audioChunks = [];
const statusDiv = document.getElementById("status");
const audioPlayback = document.getElementById("audioPlayback");

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);

    mediaRecorder.ondataavailable = (event) => {
      audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      audioChunks = [];
      audioPlayback.src = URL.createObjectURL(audioBlob);
      statusDiv.innerText = "🔁 جاري المعالجة...";

      const formData = new FormData();
      formData.append("file", audioBlob, "recording.webm");

      try {
        const transcription = await fetch("/transcribe", {
          method: "POST",
          body: formData,
        });

        const transcribed = await transcription.json();
        const userText = transcribed.text;

        statusDiv.innerText = `📨 تم التعرف: ${userText}`;

        const response = await fetch("/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: userText })
        });

        const audioBuffer = await response.arrayBuffer();
        const audioBlob = new Blob([audioBuffer], { type: 'audio/mpeg' });
        audioPlayback.src = URL.createObjectURL(audioBlob);
        audioPlayback.play();
      } catch (err) {
        statusDiv.innerText = "❌ حدث خطأ أثناء المعالجة.";
        console.error(err);
      }
    };

    mediaRecorder.start();
    statusDiv.innerText = "🎙️ جاري التسجيل... تكلم الآن";

    setTimeout(() => {
      mediaRecorder.stop();
      statusDiv.innerText = "⏹️ تم إنهاء التسجيل.";
    }, 5000); // تسجيل 5 ثواني
  } catch (error) {
    statusDiv.innerText = "⚠️ لم يتم الوصول إلى الميكروفون.";
    console.error(error);
  }
}
