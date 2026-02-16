"use client";

import { useState, useRef } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Alert from "@mui/material/Alert";
import FormControl from "@mui/material/FormControl";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Link from "@mui/material/Link";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import SearchIcon from "@mui/icons-material/Search";
import DownloadIcon from "@mui/icons-material/Download";
import DescriptionIcon from "@mui/icons-material/Description";
import TableChartIcon from "@mui/icons-material/TableChart";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";

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

interface ExtractResponse {
  rows_added: number;
  sheet_url: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null);
  const [classifying, setClassifying] = useState(false);
  const [classification, setClassification] = useState<ClassifyResponse | null>(
    null
  );
  const [selectedShow, setSelectedShow] = useState<string>("");
  const [redacting, setRedacting] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [extractResult, setExtractResult] = useState<ExtractResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [privacyModalOpen, setPrivacyModalOpen] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  function resetAll() {
    setFile(null);
    setUploadResult(null);
    setClassification(null);
    setSelectedShow("");
    setExtractResult(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

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

  async function handleClassify() {
    if (!uploadResult) return;
    setError(null);
    setClassifying(true);

    try {
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
          setError(
            "Classification timed out (took longer than 2 minutes). Try a smaller PDF."
          );
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

  async function handleExtract() {
    if (!uploadResult) return;
    setError(null);
    setExtracting(true);
    setExtractResult(null);

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 120000);
      const res = await fetch(`${API_URL}/api/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_id: uploadResult.document_id }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Export failed (${res.status})`);
      }
      const data: ExtractResponse = await res.json();
      setExtractResult(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        if (err.name === "AbortError") {
          setError("Export timed out. Try again.");
          return;
        }
        setError(err.message);
        return;
      }
      setError("Export to Google Sheets failed");
    } finally {
      setExtracting(false);
    }
  }

  return (
    <Box
      sx={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        bgcolor: "background.default",
      }}
    >
      <Box
        component="main"
        sx={{
          flex: 1,
          display: "flex",
          justifyContent: "center",
          px: 2,
          py: 6,
          pb: 8,
        }}
      >
        <Box sx={{ width: "100%", maxWidth: 560, display: "flex", flexDirection: "column", gap: 3 }}>
          {/* Logo + Header */}
          <Box sx={{ textAlign: "center" }}>
            <Box
              component="img"
              src="/redactExtract.png"
              alt="Redact & Extract"
              sx={{
                maxWidth: 320,
                width: "100%",
                height: "auto",
                mx: "auto",
                mb: 1.5,
              }}
            />
            <Typography variant="body1" color="text.secondary">
              Create a clean copy of your sponsorship contract for a single show.
              Upload your PDF, pick the show you need, and download.
            </Typography>
          </Box>

          {/* Error */}
          {error && (
            <Alert severity="error" onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          {/* Step 1: Upload */}
          <Paper elevation={0} sx={{ p: 3 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2 }}>
              <Box
                sx={{
                  width: 36,
                  height: 36,
                  borderRadius: "50%",
                  bgcolor: "primary.main",
                  color: "white",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  typography: "subtitle2",
                  fontWeight: 700,
                }}
              >
                1
              </Box>
              <Typography variant="h6">Upload your contract</Typography>
            </Box>

            <Box sx={{ display: "flex", flexDirection: { xs: "column", sm: "row" }, gap: 2 }}>
              <Button
                component="label"
                variant="outlined"
                startIcon={<DescriptionIcon />}
                sx={{
                  flex: 1,
                  py: 2,
                  borderStyle: "dashed",
                  borderWidth: 2,
                  "&:hover": {
                    borderWidth: 2,
                    borderStyle: "dashed",
                    bgcolor: "action.hover",
                  },
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  hidden
                  onChange={(e) => {
                    setFile(e.target.files?.[0] ?? null);
                    setUploadResult(null);
                    setClassification(null);
                    setSelectedShow("");
                  }}
                />
                {file ? file.name : "Choose a PDF file"}
              </Button>
              <Button
                variant="contained"
                startIcon={<UploadFileIcon />}
                onClick={handleUpload}
                disabled={!file || uploading}
                sx={{ alignSelf: { xs: "stretch", sm: "center" } }}
              >
                {uploading ? "Uploading…" : "Upload"}
              </Button>
            </Box>

            {uploadResult && (
              <Box
                sx={{
                  mt: 2,
                  pt: 2,
                  borderTop: 1,
                  borderColor: "divider",
                  display: "flex",
                  flexWrap: "wrap",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 1,
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  ✓ {uploadResult.blocks.length} sections found across{" "}
                  {uploadResult.page_count} pages
                </Typography>
                <Button size="small" color="primary" onClick={resetAll}>
                  Start over
                </Button>
              </Box>
            )}
          </Paper>

          {/* Step 2: Classify */}
          {uploadResult && (
            <Paper elevation={0} sx={{ p: 3 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 0.5 }}>
                <Box
                  sx={{
                    width: 36,
                    height: 36,
                    borderRadius: "50%",
                    bgcolor: "primary.main",
                    color: "white",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    typography: "subtitle2",
                    fontWeight: 700,
                  }}
                >
                  2
                </Box>
                <Typography variant="h6">Identify the shows</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ ml: 5, mb: 2 }}>
                We&apos;ll scan your document to find each show mentioned in the contract.
              </Typography>

              <Button
                variant="contained"
                color="secondary"
                startIcon={<SearchIcon />}
                onClick={handleClassify}
                disabled={classifying}
                sx={{ ml: 5 }}
              >
                {classifying ? "Scanning…" : "Scan document"}
              </Button>

              {classification && (
                <Box sx={{ ml: 5, mt: 2 }}>
                  <Typography variant="body2" fontWeight={600} sx={{ mb: 1 }}>
                    Found {classification.shows.length} show
                    {classification.shows.length !== 1 ? "s" : ""}:
                  </Typography>
                  <List dense disablePadding>
                    {classification.shows.map((show) => (
                      <ListItem
                        key={show}
                        sx={{
                          bgcolor: "action.hover",
                          borderRadius: 1,
                          mb: 0.5,
                          py: 1,
                        }}
                      >
                        <ListItemText
                          primary={show}
                          secondary={`${classification.assignments[show]?.length ?? 0} sections`}
                          secondaryTypographyProps={{ variant: "caption" }}
                        />
                      </ListItem>
                    ))}
                  </List>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
                    Also found {classification.assignments["GLOBAL"]?.length ?? 0}{" "}
                    shared sections (signatures, terms, etc.)
                  </Typography>
                </Box>
              )}
            </Paper>
          )}

          {/* Step 3: Redact & Download */}
          {classification && classification.shows.length > 0 && (
            <Paper elevation={0} sx={{ p: 3 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 0.5 }}>
                <Box
                  sx={{
                    width: 36,
                    height: 36,
                    borderRadius: "50%",
                    bgcolor: "secondary.main",
                    color: "white",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    typography: "subtitle2",
                    fontWeight: 700,
                  }}
                >
                  3
                </Box>
                <Typography variant="h6">Get your redacted copy</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ ml: 5, mb: 2 }}>
                Pick the show you need. We&apos;ll create a new PDF with only that
                show&apos;s content—everything else is removed for good.
              </Typography>

              <Box
                sx={{
                  ml: 5,
                  display: "flex",
                  flexDirection: { xs: "column", sm: "row" },
                  gap: 2,
                }}
              >
                <FormControl size="small" sx={{ minWidth: 200 }}>
                  <Select
                    value={selectedShow}
                    onChange={(e) => setSelectedShow(e.target.value)}
                    displayEmpty
                  >
                    {classification.shows.map((show) => (
                      <MenuItem key={show} value={show}>
                        {show}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <Button
                  variant="contained"
                  color="secondary"
                  startIcon={<DownloadIcon />}
                  onClick={handleRedact}
                  disabled={!selectedShow || redacting}
                  sx={{ alignSelf: { xs: "stretch", sm: "flex-start" } }}
                >
                  {redacting ? "Creating PDF…" : "Download PDF"}
                </Button>
              </Box>
            </Paper>
          )}

          {/* Step 4: Export to Google Sheets */}
          {classification && classification.shows.length > 0 && (
            <Paper elevation={0} sx={{ p: 3 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 0.5 }}>
                <Box
                  sx={{
                    width: 36,
                    height: 36,
                    borderRadius: "50%",
                    bgcolor: "success.main",
                    color: "white",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    typography: "subtitle2",
                    fontWeight: 700,
                  }}
                >
                  4
                </Box>
                <Typography variant="h6">Export to Google Sheets</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ ml: 5, mb: 2 }}>
                Extract sponsor details, costs, billing terms, and more for each
                show and add them to your Google Sheet.
              </Typography>

              <Box sx={{ ml: 5 }}>
                <Button
                  variant="contained"
                  color="success"
                  startIcon={<TableChartIcon />}
                  onClick={handleExtract}
                  disabled={extracting}
                >
                  {extracting ? "Exporting…" : "Export to Sheets"}
                </Button>

                {extractResult && (
                  <Box
                    sx={{
                      mt: 2,
                      p: 2,
                      bgcolor: "success.main",
                      color: "white",
                      borderRadius: 2,
                      display: "flex",
                      alignItems: "center",
                      gap: 1.5,
                    }}
                  >
                    <Typography variant="body2" sx={{ flex: 1 }}>
                      {extractResult.rows_added} row
                      {extractResult.rows_added !== 1 ? "s" : ""} added
                      successfully.
                    </Typography>
                    <Link
                      href={extractResult.sheet_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      sx={{
                        color: "white",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 0.5,
                        fontWeight: 600,
                        fontSize: "0.875rem",
                      }}
                    >
                      Open Sheet <OpenInNewIcon fontSize="small" />
                    </Link>
                  </Box>
                )}
              </Box>
            </Paper>
          )}
        </Box>
      </Box>

      {/* Footer */}
      <Box
        component="footer"
        sx={{
          position: "fixed",
          bottom: 0,
          right: 0,
          left: 0,
          p: 2,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 2,
        }}
      >
        <Typography
          component="button"
          variant="body2"
          color="text.secondary"
          onClick={() => setPrivacyModalOpen(true)}
          sx={{
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: 0,
            textDecoration: "underline",
            "&:hover": { color: "primary.main" },
          }}
        >
          Privacy Policy
        </Typography>
        <Typography
          component="a"
          href="https://lorienweb.com"
          target="_blank"
          rel="noopener noreferrer"
          variant="body2"
          color="text.secondary"
          sx={{
            textDecoration: "none",
            "&:hover": { color: "primary.main" },
          }}
        >
          Designed and built by Lorien Web
        </Typography>
      </Box>

      {/* Privacy Policy Modal */}
      <Dialog
        open={privacyModalOpen}
        onClose={() => setPrivacyModalOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Privacy Policy</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            This application uses Anthropic&apos;s Claude API to classify and extract
            information from your PDF contracts. When you use the &quot;Scan document&quot;
            or &quot;Export to Sheets&quot; features, the text content of your documents
            is sent to Anthropic&apos;s servers for processing.
          </Typography>
          <Typography variant="body2" sx={{ mb: 2 }}>
            According to Anthropic&apos;s policies, they do not use API customer data to
            train their models. Your data is processed only to fulfill your request
            and is not retained for model improvement purposes.
          </Typography>
          <Typography variant="body2">
            For full details on how Anthropic handles data, please review their
            privacy policy:
          </Typography>
          <Link
            href="https://www.anthropic.com/legal/privacy"
            target="_blank"
            rel="noopener noreferrer"
            sx={{ mt: 1, display: "inline-flex", alignItems: "center", gap: 0.5 }}
          >
            Anthropic Privacy Policy <OpenInNewIcon fontSize="small" />
          </Link>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPrivacyModalOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
