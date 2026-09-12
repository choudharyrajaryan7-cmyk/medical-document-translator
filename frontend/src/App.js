import { useState } from "react";
import "./App.css";

function App() {
  const [file, setFile] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [status, setStatus] = useState("");
  const [result, setResult] = useState(null);
  const [question, setQuestion] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [asking, setAsking] = useState(false);

  const pollStatus = (id) => {
    const interval = setInterval(async () => {
      const res = await fetch(`http://localhost:8000/jobs/${id}`);
      const data = await res.json();

      setStatus(data.status);

      if (data.status === "completed") {
        setResult(data.result);
        clearInterval(interval);
      }
      if (data.status === "failed") {
        setStatus("failed: " + data.error);
        clearInterval(interval);
      }
    }, 2000);
  };

  const handleUpload = async () => {
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setStatus("Uploading...");
    setResult(null);
    setChatHistory([]);

    const res = await fetch("http://localhost:8000/upload", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();

    setJobId(data.job_id);
    setStatus(data.status);

    pollStatus(data.job_id);
  };

  const handleAsk = async () => {
    if (!question.trim()) return;
    const q = question;
    setChatHistory((h) => [...h, { role: "user", text: q }]);
    setQuestion("");
    setAsking(true);

    const res = await fetch(`http://localhost:8000/jobs/${jobId}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    const data = await res.json();

    setChatHistory((h) => [...h, { role: "ai", text: data.answer || data.error }]);
    setAsking(false);
  };

  return (
    <div className="app-shell">
      <h1 className="app-title">Medical Document Translator</h1>
      <p className="app-subtitle">
        Upload a hospital bill or doctor's report — get it explained in plain,
        everyday language, and ask follow-up questions if anything's unclear.
      </p>

      <div className="upload-card">
        <input
          className="file-input"
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          onChange={(e) => setFile(e.target.files[0])}
        />
        <button className="upload-btn" onClick={handleUpload}>
          Upload
        </button>
      </div>

      {jobId && (
        <div className="job-meta">
          <div><b>Job ID:</b> {jobId}</div>
          <div><b>Status:</b> {status}</div>
        </div>
      )}

      {result && (
        <div>
          {result.health_summary && result.health_summary.explanation && (
            <div className="health-card">
              <h3>What your doctor found</h3>
              {result.health_summary.diagnosis && (
                <p><b>Diagnosis:</b> {result.health_summary.diagnosis}</p>
              )}
              <p>{result.health_summary.explanation}</p>
              {result.health_summary.next_steps &&
                result.health_summary.next_steps.length > 0 && (
                  <>
                    <p style={{ marginBottom: "2px" }}><b>What to do next:</b></p>
                    <ul>
                      {result.health_summary.next_steps.map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ul>
                  </>
                )}
            </div>
          )}

          {result.flags && result.flags.length > 0 && (
            <div className="flags-block">
              <h4>Worth double-checking</h4>
              <ul>
                {result.flags.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          )}

          {result.line_items && result.line_items.length > 0 && (
            <>
              <div className="total-line">Total: {result.total || "N/A"}</div>
              <table className="bill-table">
                <thead>
                  <tr>
                    <th>Description</th>
                    <th>Code</th>
                    <th>Plain English</th>
                    <th>Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {result.line_items.map((item, i) => (
                    <tr key={i}>
                      <td>{item.description}</td>
                      <td>{item.code || "—"}</td>
                      <td>{item.plain_english}</td>
                      <td>{item.amount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          <div className="chat-section">
            <h4>Still confused? Ask a question</h4>

            <div className="chat-log">
              {chatHistory.map((msg, i) => (
                <p key={i} className={`chat-msg ${msg.role}`}>
                  {msg.role === "user" ? "You: " : "Assistant: "}
                  {msg.text}
                </p>
              ))}
              {asking && <p className="chat-thinking">Thinking...</p>}
            </div>

            <div className="chat-input-row">
              <input
                className="chat-input"
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleAsk()}
                placeholder="e.g. why is the lab cost so high?"
              />
              <button className="chat-ask-btn" onClick={handleAsk}>
                Ask
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;