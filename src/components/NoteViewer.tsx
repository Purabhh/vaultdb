import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { NoteDetail } from "../types";

interface NoteViewerProps {
  note: NoteDetail;
  loading: boolean;
}

export function NoteViewer({ note, loading }: NoteViewerProps) {
  const [showEmbeddings, setShowEmbeddings] = useState(false);

  if (loading) {
    return <div className="note-viewer"><div className="loading">Loading note...</div></div>;
  }

  // Convert [[wikilinks]] to bold text so they stand out
  const renderedMarkdown = note.raw_content.replace(
    /\[\[([^\]]+)\]\]/g,
    "**[[$1]]**"
  );

  return (
    <div className="note-viewer">
      <div className="note-header">
        <h2 className="note-title">{note.title}</h2>
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
          <button
            className={!showEmbeddings ? "active" : ""}
            onClick={() => setShowEmbeddings(false)}
          >
            Note
          </button>
          <button
            className={showEmbeddings ? "active" : ""}
            onClick={() => setShowEmbeddings(true)}
          >
            Embeddings
          </button>
        </div>
      </div>

      <div className="note-body">
        {!showEmbeddings ? (
          <div className="note-rendered-content">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {renderedMarkdown}
            </ReactMarkdown>
          </div>
        ) : (
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
