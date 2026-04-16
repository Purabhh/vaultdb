import { useState, useEffect, useRef, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { NoteDetail } from "../types";

type NoteViewMode = "note" | "embeddings";

interface NoteViewerProps {
  note: NoteDetail;
  loading: boolean;
  vaultName: string;
  onNoteUpdated?: (note: NoteDetail) => void;
}

export function NoteViewer({ note, loading, vaultName, onNoteUpdated }: NoteViewerProps) {
  const [mode, setMode] = useState<NoteViewMode>("note");
  const [editContent, setEditContent] = useState(note.raw_content);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "reembedding" | "error">("idle");

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reembedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedRef = useRef(note.raw_content);

  // Sync content when a different note is selected
  useEffect(() => {
    setEditContent(note.raw_content);
    lastSavedRef.current = note.raw_content;
    setSaveStatus("idle");
  }, [note.path, note.raw_content]);

  const doSave = useCallback(async (content: string) => {
    if (content === lastSavedRef.current) return;
    setSaveStatus("saving");
    try {
      await invoke("save_note", { vaultName, notePath: note.path, content });
      lastSavedRef.current = content;
      setSaveStatus("saved");
    } catch (e) {
      console.error("Save failed:", e);
      setSaveStatus("error");
    }
  }, [vaultName, note.path]);

  const doReembed = useCallback(async () => {
    setSaveStatus("reembedding");
    try {
      const updated = await invoke<NoteDetail>("reembed_note", { vaultName, notePath: note.path });
      setSaveStatus("saved");
      onNoteUpdated?.(updated);
    } catch (e) {
      console.error("Re-embed failed:", e);
      setSaveStatus("saved");
    }
  }, [vaultName, note.path, onNoteUpdated]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setEditContent(value);

    // Debounced auto-save: 1.5s
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      doSave(value).then(() => {
        // Debounced re-embed: 5s after last save
        if (reembedTimerRef.current) clearTimeout(reembedTimerRef.current);
        reembedTimerRef.current = setTimeout(() => doReembed(), 5000);
      });
    }, 1500);
  }, [doSave, doReembed]);

  // Auto-resize textarea to fit content
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta && mode === "note") {
      ta.style.height = "auto";
      ta.style.height = ta.scrollHeight + "px";
    }
  }, [editContent, mode]);

  // Cleanup timers
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      if (reembedTimerRef.current) clearTimeout(reembedTimerRef.current);
    };
  }, []);

  if (loading) {
    return <div className="note-viewer"><div className="loading">Loading note...</div></div>;
  }

  const statusLabel: Record<typeof saveStatus, string> = {
    idle: "",
    saving: "Saving...",
    saved: "Saved",
    reembedding: "Updating embeddings...",
    error: "Save failed",
  };

  return (
    <div className="note-viewer">
      <div className="note-header">
        <div className="note-header-top">
          <h2 className="note-title">{note.title}</h2>
          {saveStatus !== "idle" && (
            <span className={`save-status save-status--${saveStatus}`}>
              {statusLabel[saveStatus]}
            </span>
          )}
        </div>
        <div className="note-meta">
          {note.tags.length > 0 && (
            <div className="note-tags">
              {note.tags.map((tag) => (
                <span key={tag} className="tag-badge">#{tag}</span>
              ))}
            </div>
          )}
          {note.links.length > 0 && (
            <div className="note-links-count">
              {note.links.length} link{note.links.length !== 1 ? "s" : ""}
            </div>
          )}
        </div>
        <div className="view-toggle note-view-toggle">
          <button className={mode === "note" ? "active" : ""} onClick={() => setMode("note")}>
            Note
          </button>
          <button
            className={mode === "embeddings" ? "active" : ""}
            onClick={() => setMode("embeddings")}
          >
            Embeddings
          </button>
        </div>
      </div>

      <div className="note-body">
        {mode === "note" && (
          <textarea
            ref={textareaRef}
            className="note-textarea"
            value={editContent}
            onChange={handleChange}
            spellCheck={false}
          />
        )}

        {mode === "embeddings" && (
          <div className="note-chunks">
            {note.chunks.map((chunk) => (
              <div key={chunk.index} className="chunk-card">
                <div className="chunk-header">
                  <span className="chunk-label">Chunk {chunk.index + 1}</span>
                </div>
                <p className="chunk-text">{chunk.text}</p>
                {chunk.similar_notes.length > 0 && (
                  <div className="chunk-similar">
                    <span className="similar-label">Similar notes:</span>
                    <ul className="similar-list">
                      {chunk.similar_notes.map((s, i) => (
                        <li key={i} className="similar-item">
                          <div className="similar-header">
                            <span className="similar-title">{s.title}</span>
                            <span className="similar-score">
                              {(s.score * 100).toFixed(0)}%
                            </span>
                          </div>
                          <p className="similar-chunk">{s.chunk}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
