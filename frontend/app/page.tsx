"use client";

import { useState, useRef } from "react";

// ---------------------------------------------------------------------------
// Types matching the backend response models
// ---------------------------------------------------------------------------

interface TextBlock {
  block_id: number;
  page_number: number;
  bbox: number[];
  text: string;
}

interface UploadResponse {
  document_id: string;
  blocks: TextBlock[];
  page_count: number;
}

interface ClassifyResponse {
  shows: string[];
  assignments: Record<string, number[]>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export default function Home() {
  // Upload state
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);

  // Classification state
  const [classifying, setClassifying] = useState(false);
  const [classification, setClassification] = useState<ClassifyResponse | null>(
    null
  );

  // Redaction state
  const [selectedShow, setSelectedShow] = useState<string>("");
  const [redacting, setRedacting] = useState(false);

  // Error state
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // -------------------------------------------------------------------------
  // Handlers
  // -------------------------------------------------------------------------

  /** Reset everything for a new document */
  function resetAll() {
    setFile(null);
    setUploadResult(null);
    setClassification(null);
    setSelectedShow("");
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  /** Step 1: Upload PDF and extract text blocks */
  async function handleUpload() {
    if (!file) return;
    setError(null);
    setUploading(true);
    setClassification(null);
    setSelectedShow("");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch(`${API_URL}/api/upload`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Upload failed (${res.status})`);
      }

      const data: UploadResponse = await res.json();
      setUploadResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  /** Step 2: Classify blocks via AI */
  async function handleClassify() {
    if (!uploadResult) return;
    setError(null);
    setClassifying(true);

    try {
      // Classify can take 60–90+ seconds for large documents; use a long timeout
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000);
      const res = await fetch(`${API_URL}/api/classify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_id: uploadResult.document_id }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Classification failed (${res.status})`);
      }

      const data: ClassifyResponse = await res.json();
      setClassification(data);
      if (data.shows.length > 0) setSelectedShow(data.shows[0]);
    } catch (err: unknown) {
      if (err instanceof Error) {
        if (err.name === "AbortError") {
          setError("Classification timed out (took longer than 2 minutes). Try a smaller PDF.");
          return;
        }
        setError(err.message);
        return;
      }
      setError("Classification failed");
    } finally {
      setClassifying(false);
    }
  }

  /** Step 3: Generate redacted PDF and trigger download */
  async function handleRedact() {
    if (!uploadResult || !selectedShow) return;
    setError(null);
    setRedacting(true);

    try {
      const res = await fetch(`${API_URL}/api/redact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: uploadResult.document_id,
          selected_show: selectedShow,
        }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Redaction failed (${res.status})`);
      }

      // Download the PDF blob
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `redacted_${selectedShow.replace(/\s+/g, "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Redaction failed");
    } finally {
      setRedacting(false);
    }
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <main className="min-h-screen bg-background flex items-start justify-center p-8">
      <div className="w-full max-w-2xl space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold tracking-tight">PDF Redactor</h1>
          <p className="text-sm text-foreground/60 mt-1">
            Upload a multi-show sponsorship contract, classify blocks by show,
            and download a redacted version.
          </p>
        </div>

        {/* Error banner */}
        {error && (
          <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
            {error}
          </div>
        )}

        {/* ---- Step 1: Upload ---- */}
        <section className="rounded-lg border border-foreground/10 p-5 space-y-4">
          <h2 className="text-lg font-semibold">1. Upload PDF</h2>

          <div className="flex items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                // Reset downstream state when a new file is selected
                setUploadResult(null);
                setClassification(null);
                setSelectedShow("");
              }}
              className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-foreground/10 file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-foreground/15 cursor-pointer"
            />
            <button
              onClick={handleUpload}
              disabled={!file || uploading}
              className="rounded-md bg-foreground text-background px-4 py-1.5 text-sm font-medium disabled:opacity-40 hover:opacity-90 transition-opacity"
            >
              {uploading ? "Uploading..." : "Upload"}
            </button>
          </div>

          {uploadResult && (
            <div className="text-sm text-foreground/70 space-y-1">
              <p>
                Extracted <strong>{uploadResult.blocks.length}</strong> text
                blocks across <strong>{uploadResult.page_count}</strong> pages.
              </p>
              <button
                onClick={resetAll}
                className="text-xs underline underline-offset-2 opacity-60 hover:opacity-100"
              >
                Start over
              </button>
            </div>
          )}
        </section>

        {/* ---- Step 2: Classify ---- */}
        {uploadResult && (
          <section className="rounded-lg border border-foreground/10 p-5 space-y-4">
            <h2 className="text-lg font-semibold">2. Classify Blocks</h2>
            <p className="text-sm text-foreground/60">
              Send extracted blocks to AI for show-level classification.
            </p>

            <button
              onClick={handleClassify}
              disabled={classifying}
              className="rounded-md bg-foreground text-background px-4 py-1.5 text-sm font-medium disabled:opacity-40 hover:opacity-90 transition-opacity"
            >
              {classifying ? "Classifying..." : "Classify Document"}
            </button>

            {classification && (
              <div className="text-sm space-y-2">
                <p className="font-medium">
                  Detected {classification.shows.length} show
                  {classification.shows.length !== 1 ? "s" : ""}:
                </p>
                <ul className="list-disc list-inside text-foreground/70 space-y-1">
                  {classification.shows.map((show) => (
                    <li key={show}>
                      {show}{" "}
                      <span className="text-foreground/40">
                        ({classification.assignments[show]?.length ?? 0} blocks)
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="text-foreground/50 text-xs">
                  Global blocks:{" "}
                  {classification.assignments["GLOBAL"]?.length ?? 0} |
                  Unclassified:{" "}
                  {classification.assignments["UNCLASSIFIED"]?.length ?? 0}
                </p>
              </div>
            )}
          </section>
        )}

        {/* ---- Step 3: Redact & Download ---- */}
        {classification && classification.shows.length > 0 && (
          <section className="rounded-lg border border-foreground/10 p-5 space-y-4">
            <h2 className="text-lg font-semibold">3. Redact & Download</h2>
            <p className="text-sm text-foreground/60">
              Select a show to keep. All content unrelated to that show (and
              non-global content) will be permanently redacted.
            </p>

            <div className="flex items-center gap-3">
              <select
                value={selectedShow}
                onChange={(e) => setSelectedShow(e.target.value)}
                className="rounded-md border border-foreground/20 bg-background px-3 py-1.5 text-sm"
              >
                {classification.shows.map((show) => (
                  <option key={show} value={show}>
                    {show}
                  </option>
                ))}
              </select>

              <button
                onClick={handleRedact}
                disabled={!selectedShow || redacting}
                className="rounded-md bg-foreground text-background px-4 py-1.5 text-sm font-medium disabled:opacity-40 hover:opacity-90 transition-opacity"
              >
                {redacting ? "Generating..." : "Generate Redacted PDF"}
              </button>
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
