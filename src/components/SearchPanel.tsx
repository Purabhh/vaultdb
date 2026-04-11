import { useState } from "react";
import { SearchResult } from "../types";

interface SearchPanelProps {
  results: SearchResult[];
  onSearch: (query: string) => void;
}

export function SearchPanel({ results, onSearch }: SearchPanelProps) {
  const [query, setQuery] = useState("");

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSearch(query);
  }

  return (
    <div className="search-panel">
      <form className="search-bar" onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Semantic search across your vault..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        <button type="submit">Search</button>
      </form>

      <div className="search-results">
        {results.length === 0 && (
          <p className="search-empty">
            Search your vault using natural language. Results are ranked by
            semantic similarity.
          </p>
        )}
        {results.map((r, i) => (
          <div key={i} className="result-card">
            <div className="result-header">
              <h3>{r.title}</h3>
              <span className="score">{(r.score * 100).toFixed(0)}%</span>
            </div>
            <p className="result-chunk">{r.chunk}</p>
            <span className="result-path">{r.path}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
