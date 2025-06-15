let mediaRecorder;
let audioChunks = [];
const statusDiv = document.getElementById("status");
const audioPlayback = document.getElementById("audioPlayback");

async function startRecording() {
  statusDiv.innerText = "🔴 جاري التسجيل... تحدث الآن";

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream);
  audioChunks = [];

  mediaRecorder.ondataavailable = event => {
    audioChunks.push(event.data);
  };

  mediaRecorder.onstop = async () => {
    statusDiv.innerText = "⏳ جاري المعالجة...";
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append("audio", audioBlob, "recording.webm");
    formData.append("user_id", "test_user");

    const response = await fetch("/transcribe", {
      method: "POST",
      body: formData
    });

    const data = await response.json();
    statusDiv.innerText = data.reply;

    const tts = await fetch("/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: data.reply })
    });

    const audioBlobTTS = await tts.blob();
    audioPlayback.src = URL.createObjectURL(audioBlobTTS);
    audioPlayback.play();
  };

  mediaRecorder.start();
  setTimeout(() => {
    mediaRecorder.stop();
    stream.getTracks().forEach(track => track.stop());
  }, 5000);
}
