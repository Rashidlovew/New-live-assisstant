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

// --- VAD Parameters and State Variables ---
const SILENCE_THRESHOLD = 5; // Max average deviation from 128 for silence (adjust as needed)
const SILENCE_DURATION_MS = 1500; // 1.5 seconds of silence to stop
const VAD_CHECK_INTERVAL_MS = 200; // Check for silence every 200ms
const MAX_RECORDING_DURATION_MS = 30000; // Fallback: 30 seconds max

let vadContext = null;
let vadAnalyserNode = null;
let vadSourceNode = null;
let vadDataArray = null;
let vadSilenceStartTimestamp = null;
let vadInterval = null;
let maxRecordingTimer = null;
// --- End VAD Variables ---

function logTIMESTAMP(message, ...args) {
    const now = new Date();
    const timestamp = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}.${String(now.getMilliseconds()).padStart(3, '0')}`;
    if (args.length > 0) {
        console.log(`[${timestamp}] ${message}`, ...args);
    } else {
        console.log(`[${timestamp}] ${message}`);
    }
}

function cleanupVAD() {
    logTIMESTAMP("VAD: Cleaning up VAD resources.");
    if (vadInterval) {
        clearInterval(vadInterval);
        vadInterval = null;
    }
    if (maxRecordingTimer) {
        clearTimeout(maxRecordingTimer);
        maxRecordingTimer = null;
    }
    if (vadSourceNode) {
         vadSourceNode.disconnect();
         vadSourceNode = null;
    }
    if (vadAnalyserNode) {
         vadAnalyserNode.disconnect(); // Analyser is connected from source, so disconnect it too.
         vadAnalyserNode = null;
    }
    if (vadContext && vadContext.state !== 'closed') {
        vadContext.close().catch(e => logTIMESTAMP("VAD: Error closing AudioContext:", e));
    }
    vadContext = null;
    vadDataArray = null; // Clear the data array
    vadSilenceStartTimestamp = null; // Reset silence timestamp
}

async function startRecording() {
  logTIMESTAMP("startRecording() called. Current isRecording:", isRecording);

  if (isRecording) {
    logTIMESTAMP("🎤 startRecording: Recording already in progress, returning.");
    return;
  }

  // Reset audio playback state from previous turn
  logTIMESTAMP("startRecording: Before audioPlayback reset. onended is:", audioPlayback.onended ? "set" : "null");
  try {
    audioPlayback.pause();
    audioPlayback.src = "";
    audioPlayback.onended = null;
  } catch (e) {
    console.warn("Audio playback reset warning:", e); // Non-critical
  }
  logTIMESTAMP("startRecording: After audioPlayback reset. onended is:", audioPlayback.onended ? "set" : "null");

  cleanupVAD(); // Clean up any previous VAD instances before starting new recording

  isRecording = true;
  mediaRecorder = null;
  audioChunks = [];

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
    cleanupVAD(); // Ensure VAD cleanup on error
    return;
  }

  try {
    mediaRecorder = new MediaRecorder(stream);
    logTIMESTAMP("🎤 startRecording: MediaRecorder instantiated successfully.");

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      logTIMESTAMP("🎤 mediaRecorder.onstop called.");
      cleanupVAD(); // Crucial: clean up VAD resources when recording stops for any reason

      // Stop stream tracks AFTER VAD is cleaned up, as VAD uses the stream.
      // Also, onstop might be called before VAD cleanup if max duration is hit.
      // So, ensure tracks are stopped here.
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

    // --- VAD Setup ---
    vadContext = new AudioContext();
    logTIMESTAMP("VAD: AudioContext created.");
    vadSourceNode = vadContext.createMediaStreamSource(stream);
    logTIMESTAMP("VAD: MediaStreamAudioSourceNode created.");
    vadAnalyserNode = vadContext.createAnalyser();
    vadAnalyserNode.fftSize = 2048; // Standard size for detailed analysis
    logTIMESTAMP("VAD: AnalyserNode created, fftSize:", vadAnalyserNode.fftSize);
    vadDataArray = new Uint8Array(vadAnalyserNode.frequencyBinCount);
    vadSourceNode.connect(vadAnalyserNode);
    // Not connecting vadAnalyserNode to vadContext.destination as we don't need to hear the mic input through VAD
    logTIMESTAMP("VAD: Audio graph connected (source -> analyser).");

    mediaRecorder.start();
    logTIMESTAMP("🎤 startRecording: mediaRecorder.start() called.");

    // Start VAD checks
    vadSilenceStartTimestamp = null; // Reset silence timer
    vadInterval = setInterval(runVADCheck, VAD_CHECK_INTERVAL_MS);
    logTIMESTAMP("VAD: VAD check interval started. Interval ID:", vadInterval);

    // Fallback max recording timer
    maxRecordingTimer = setTimeout(() => {
        logTIMESTAMP("VAD: Max recording duration reached (" + MAX_RECORDING_DURATION_MS + "ms). Stopping recording.");
        if (mediaRecorder && mediaRecorder.state === "recording") {
            mediaRecorder.stop(); // This will trigger onstop, which calls cleanupVAD
        } else {
            cleanupVAD(); // If mediaRecorder somehow already stopped, ensure cleanup
        }
    }, MAX_RECORDING_DURATION_MS);
    logTIMESTAMP("VAD: Max recording timer set for " + MAX_RECORDING_DURATION_MS + "ms. Timer ID:", maxRecordingTimer);
    // --- End VAD Setup ---

  } catch (err) {
    logTIMESTAMP("🎤 startRecording: MediaRecorder setup or VAD setup FAILED.", err);
    statusDiv.innerText = "⚠️ خطأ في إعداد مسجل الصوت أو كشف الصوت. حاول تحديث الصفحة.";
    isRecording = false;
    cleanupVAD(); // Clean up VAD resources on error
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
    }
    return;
  }
}

function runVADCheck() {
    if (!vadAnalyserNode || !mediaRecorder || mediaRecorder.state !== "recording") {
        // logTIMESTAMP("VAD: runVADCheck - conditions not met or recording stopped. Analyser:", vadAnalyserNode, "MediaRecorder state:", mediaRecorder ? mediaRecorder.state : 'N/A');
        // No cleanup here, this might be called when mediaRecorder.stop() has already been called by VAD itself or max timer.
        // cleanupVAD is called by onstop or by the max timer handler.
        return;
    }

    vadAnalyserNode.getByteTimeDomainData(vadDataArray);
    let sumSquares = 0.0;
    for (const amplitude of vadDataArray) {
        sumSquares += (amplitude - 128) * (amplitude - 128); // 128 is the zero point for Uint8Array PCM data
    }
    const rms = Math.sqrt(sumSquares / vadDataArray.length);

    // Optional: Detailed RMS logging for VAD sensitivity debugging
    // logTIMESTAMP("VAD Check: RMS=" + rms.toFixed(2));

    if (rms < SILENCE_THRESHOLD) {
        if (vadSilenceStartTimestamp === null) {
            vadSilenceStartTimestamp = Date.now();
            // logTIMESTAMP("VAD: Silence potentially started at " + vadSilenceStartTimestamp + ", RMS: " + rms.toFixed(2));
        } else {
            const silentDuration = Date.now() - vadSilenceStartTimestamp;
            // logTIMESTAMP("VAD: Continuing silence for " + silentDuration + "ms, RMS: " + rms.toFixed(2));
            if (silentDuration >= SILENCE_DURATION_MS) {
                logTIMESTAMP("VAD: Silence detected for " + SILENCE_DURATION_MS + "ms. Stopping recording. RMS: " + rms.toFixed(2));
                if (mediaRecorder && mediaRecorder.state === "recording") {
                    mediaRecorder.stop(); // This will trigger mediaRecorder.onstop, which now calls cleanupVAD.
                } else {
                    // If mediaRecorder is already stopped but VAD interval is still running somehow.
                    cleanupVAD();
                }
            }
        }
    } else { // Sound detected
        if (vadSilenceStartTimestamp !== null) {
            // logTIMESTAMP("VAD: Sound detected, resetting silence timer. RMS: " + rms.toFixed(2));
        }
        vadSilenceStartTimestamp = null;
    }
}


async function generateReport() {
  logTIMESTAMP("generateReport() called.");
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
      logTIMESTAMP("startListener: Conditions NOT met. isRecording:", isRecording, "mediaRecorder:", mediaRecorder ? mediaRecorder.state : 'N/A');
    }
  };
  document.body.addEventListener('click', startListener);
  document.body.addEventListener('keydown', startListener);

  setTimeout(() => {
    logTIMESTAMP("window.onload: setTimeout for initial startRecording triggered.");
    document.body.removeEventListener('click', startListener);
    document.body.removeEventListener('keydown', startListener);
    if (!isRecording && !mediaRecorder) {
       logTIMESTAMP("⏰ Automatic conversation start initiated via setTimeout.");
       startRecording();
    } else {
      logTIMESTAMP("⏰ Automatic conversation start: Conditions NOT met. isRecording:", isRecording, "mediaRecorder:", mediaRecorder ? mediaRecorder.state : 'N/A');
    }
  }, 2500);
};
