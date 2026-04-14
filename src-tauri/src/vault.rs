use qdrant_client::qdrant::{
    CreateCollectionBuilder, Distance, PointStruct, SearchPointsBuilder,
    VectorParamsBuilder, UpsertPointsBuilder, DeleteCollectionBuilder,
    vectors_config::Config, VectorsConfig,
};
use qdrant_client::Qdrant;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use uuid::Uuid;
use walkdir::WalkDir;

use crate::embeddings::EmbeddingClient;
use crate::markdown::parse_markdown_file;

fn payload_str<'a>(payload: &'a HashMap<String, qdrant_client::qdrant::Value>, key: &str, default: &'a str) -> &'a str {
    payload.get(key).and_then(|v| v.as_str()).map(|s| s.as_str()).unwrap_or(default)
}

const EMBEDDING_DIM: u64 = 768; // nomic-embed-text dimension
const SEMANTIC_THRESHOLD: f32 = 0.75; // cosine similarity threshold for semantic edges

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VaultInfo {
    pub name: String,
    pub source_path: String,
    pub note_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SearchResult {
    pub title: String,
    pub path: String,
    pub chunk: String,
    pub score: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphNode {
    pub id: String,
    pub title: String,
    pub path: String,
    pub tags: Vec<String>,
    pub link_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphEdge {
    pub source: String,
    pub target: String,
    pub edge_type: String, // "link" or "semantic"
    pub weight: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GraphData {
    pub nodes: Vec<GraphNode>,
    pub edges: Vec<GraphEdge>,
}

// File tree types
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileTreeNode {
    pub name: String,
    pub path: String,
    pub is_dir: bool,
    pub children: Vec<FileTreeNode>,
}

// Note detail with chunks and similar notes
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChunkDetail {
    pub index: usize,
    pub text: String,
    pub similar_notes: Vec<SimilarNote>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SimilarNote {
    pub title: String,
    pub chunk: String,
    pub score: f32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NoteDetail {
    pub title: String,
    pub path: String,
    pub raw_content: String,
    pub tags: Vec<String>,
    pub links: Vec<String>,
    pub chunks: Vec<ChunkDetail>,
}

pub struct VaultManager {
    qdrant: Qdrant,
    embedder: EmbeddingClient,
    config_path: PathBuf,
    vaults: HashMap<String, VaultInfo>,
}

#[derive(Serialize, Deserialize, Default)]
struct VaultConfig {
    vaults: HashMap<String, VaultInfo>,
}

impl VaultManager {
    pub async fn new() -> Result<Self, String> {
        let qdrant = Qdrant::from_url("http://localhost:6334")
            .build()
            .map_err(|e| format!("Failed to connect to Qdrant: {}", e))?;

        let config_dir = dirs_config_path();
        std::fs::create_dir_all(&config_dir).ok();
        let config_path = config_dir.join("vaults.json");

        let vaults = if config_path.exists() {
            let data = std::fs::read_to_string(&config_path).unwrap_or_default();
            serde_json::from_str::<VaultConfig>(&data)
                .unwrap_or_default()
                .vaults
        } else {
            HashMap::new()
        };

        Ok(Self {
            qdrant,
            embedder: EmbeddingClient::default(),
            config_path,
            vaults,
        })
    }

    fn save_config(&self) -> Result<(), String> {
        let config = VaultConfig {
            vaults: self.vaults.clone(),
        };
        let json = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
        std::fs::write(&self.config_path, json).map_err(|e| e.to_string())
    }

    pub fn list_vaults(&self) -> Vec<VaultInfo> {
        self.vaults.values().cloned().collect()
    }

    pub async fn create_vault(&mut self, name: &str, source_path: &str) -> Result<VaultInfo, String> {
        let collection_name = format!("vault_{}", name);

        // Create Qdrant collection
        self.qdrant
            .create_collection(
                CreateCollectionBuilder::new(&collection_name)
                    .vectors_config(VectorsConfig {
                        config: Some(Config::Params(
                            VectorParamsBuilder::new(EMBEDDING_DIM, Distance::Cosine).build(),
                        )),
                    }),
            )
            .await
            .map_err(|e| format!("Failed to create collection: {}", e))?;

        // Ingest markdown files
        let notes = self.ingest_directory(Path::new(source_path), &collection_name).await?;

        let info = VaultInfo {
            name: name.to_string(),
            source_path: source_path.to_string(),
            note_count: notes,
        };

        self.vaults.insert(name.to_string(), info.clone());
        self.save_config()?;

        Ok(info)
    }

    pub async fn delete_vault(&mut self, name: &str) -> Result<(), String> {
        let collection_name = format!("vault_{}", name);
        self.qdrant
            .delete_collection(DeleteCollectionBuilder::new(&collection_name))
            .await
            .map_err(|e| format!("Failed to delete collection: {}", e))?;

        self.vaults.remove(name);
        self.save_config()?;
        Ok(())
    }

    async fn ingest_directory(&self, dir: &Path, collection: &str) -> Result<usize, String> {
        let mut count = 0;
        let mut all_points = Vec::new();

        let md_files: Vec<_> = WalkDir::new(dir)
            .into_iter()
            .filter_map(|e| e.ok())
            .filter(|e| {
                e.path().extension().map(|ext| ext == "md").unwrap_or(false)
                    && !e.path().to_string_lossy().contains(".trash")
            })
            .collect();

        for entry in &md_files {
            let note = match parse_markdown_file(entry.path()) {
                Ok(n) => n,
                Err(_) => continue,
            };

            if note.chunks.is_empty() {
                continue;
            }

            // Embed all chunks for this note
            let embeddings = match self.embedder.embed(note.chunks.clone()).await {
                Ok(e) => e,
                Err(_) => continue,
            };

            let links_json = serde_json::to_string(&note.links).unwrap_or_default();
            let tags_json = serde_json::to_string(&note.tags).unwrap_or_default();

            for (i, (chunk, embedding)) in note.chunks.iter().zip(embeddings.iter()).enumerate() {
                let point_id = Uuid::new_v4().to_string();
                let payload: HashMap<String, qdrant_client::qdrant::Value> = HashMap::from([
                    ("title".to_string(), note.title.clone().into()),
                    ("path".to_string(), note.path.clone().into()),
                    ("chunk".to_string(), chunk.clone().into()),
                    ("chunk_index".to_string(), (i as i64).into()),
                    ("links".to_string(), links_json.clone().into()),
                    ("tags".to_string(), tags_json.clone().into()),
                ]);

                all_points.push(PointStruct::new(point_id, embedding.clone(), payload));
            }

            count += 1;
        }

        // Batch upsert
        if !all_points.is_empty() {
            // Upsert in batches of 100
            for batch in all_points.chunks(100) {
                self.qdrant
                    .upsert_points(UpsertPointsBuilder::new(collection, batch.to_vec()))
                    .await
                    .map_err(|e| format!("Upsert failed: {}", e))?;
            }
        }

        Ok(count)
    }

    pub async fn search(&self, vault_name: &str, query: &str, limit: u64) -> Result<Vec<SearchResult>, String> {
        let collection = format!("vault_{}", vault_name);
        let query_vec = self.embedder.embed_one(query).await?;

        let results = self
            .qdrant
            .search_points(
                SearchPointsBuilder::new(&collection, query_vec, limit).with_payload(true),
            )
            .await
            .map_err(|e| format!("Search failed: {}", e))?;

        let search_results = results
            .result
            .into_iter()
            .map(|point| {
                let payload = point.payload;
                SearchResult {
                    title: payload_str(&payload, "title", "").to_string(),
                    path: payload_str(&payload, "path", "").to_string(),
                    chunk: payload_str(&payload, "chunk", "").to_string(),
                    score: point.score,
                }
            })
            .collect();

        Ok(search_results)
    }

    pub async fn build_graph(&self, vault_name: &str) -> Result<GraphData, String> {
        let collection = format!("vault_{}", vault_name);

        // Scroll all points with vectors for semantic similarity
        let scroll_result = self
            .qdrant
            .scroll(
                qdrant_client::qdrant::ScrollPointsBuilder::new(&collection)
                    .with_payload(true)
                    .with_vectors(true)
                    .limit(10000),
            )
            .await
            .map_err(|e| format!("Scroll failed: {}", e))?;

        let mut nodes_map: HashMap<String, GraphNode> = HashMap::new();
        let mut edges: Vec<GraphEdge> = Vec::new();

        // Collect per-note average vectors for semantic edges
        let mut note_vectors: HashMap<String, Vec<Vec<f32>>> = HashMap::new();

        // Build nodes from unique titles
        for point in &scroll_result.result {
            let payload = &point.payload;
            let title = payload_str(payload, "title", "").to_string();
            let path = payload_str(payload, "path", "").to_string();
            let tags_str = payload_str(payload, "tags", "[]");
            let tags: Vec<String> = serde_json::from_str(tags_str).unwrap_or_default();
            let links_str = payload_str(payload, "links", "[]");
            let links: Vec<String> = serde_json::from_str(links_str).unwrap_or_default();

            // Extract vector for semantic edges
            if let Some(vectors) = &point.vectors {
                if let Some(qdrant_client::qdrant::vectors_output::VectorsOptions::Vector(v)) = &vectors.vectors_options {
                    note_vectors.entry(title.clone()).or_default().push(v.data.clone());
                }
            }

            let node = nodes_map.entry(title.clone()).or_insert_with(|| GraphNode {
                id: title.clone(),
                title: title.clone(),
                path,
                tags,
                link_count: 0,
            });
            node.link_count = links.len();

            // Create link edges
            for link in &links {
                if nodes_map.contains_key(link) || true {
                    edges.push(GraphEdge {
                        source: title.clone(),
                        target: link.clone(),
                        edge_type: "link".to_string(),
                        weight: 1.0,
                    });
                }
            }
        }

        // Compute average vectors per note, then add semantic edges
        let mut avg_vectors: HashMap<String, Vec<f32>> = HashMap::new();
        for (title, vecs) in &note_vectors {
            if vecs.is_empty() { continue; }
            let dim = vecs[0].len();
            let mut avg = vec![0.0f32; dim];
            for v in vecs {
                for (i, val) in v.iter().enumerate() {
                    avg[i] += val;
                }
            }
            let n = vecs.len() as f32;
            for val in avg.iter_mut() {
                *val /= n;
            }
            avg_vectors.insert(title.clone(), avg);
        }

        // Compare all note pairs for semantic similarity
        let titles: Vec<&String> = avg_vectors.keys().collect();
        for i in 0..titles.len() {
            for j in (i + 1)..titles.len() {
                let sim = cosine_similarity(
                    &avg_vectors[titles[i]],
                    &avg_vectors[titles[j]],
                );
                if sim > SEMANTIC_THRESHOLD {
                    edges.push(GraphEdge {
                        source: titles[i].clone(),
                        target: titles[j].clone(),
                        edge_type: "semantic".to_string(),
                        weight: sim,
                    });
                }
            }
        }

        let nodes: Vec<GraphNode> = nodes_map.into_values().collect();

        Ok(GraphData { nodes, edges })
    }

    pub fn get_file_tree(&self, vault_name: &str) -> Result<FileTreeNode, String> {
        let vault = self.vaults.get(vault_name)
            .ok_or_else(|| format!("Vault '{}' not found", vault_name))?;
        let root_path = Path::new(&vault.source_path);
        build_file_tree(root_path, root_path)
    }

    pub async fn get_note_detail(&self, vault_name: &str, note_path: &str) -> Result<NoteDetail, String> {
        let collection = format!("vault_{}", vault_name);

        // Read the raw file
        let raw_content = std::fs::read_to_string(note_path)
            .map_err(|e| format!("Failed to read file: {}", e))?;

        let note = parse_markdown_file(Path::new(note_path))
            .map_err(|e| format!("Failed to parse: {}", e))?;

        // Get this note's chunks from Qdrant with vectors
        let scroll_result = self
            .qdrant
            .scroll(
                qdrant_client::qdrant::ScrollPointsBuilder::new(&collection)
                    .with_payload(true)
                    .with_vectors(true)
                    .limit(10000),
            )
            .await
            .map_err(|e| format!("Scroll failed: {}", e))?;

        // Find chunks belonging to this note and search for similar ones
        let mut chunks = Vec::new();
        for point in &scroll_result.result {
            let payload = &point.payload;
            let p = payload_str(payload, "path", "");
            if p != note_path { continue; }

            let chunk_text = payload_str(payload, "chunk", "").to_string();
            let chunk_idx_val = payload.get("chunk_index")
                .and_then(|v| v.as_integer())
                .unwrap_or(0) as usize;

            // Get the vector for this chunk to search for similar
            let mut similar_notes = Vec::new();
            if let Some(vectors) = &point.vectors {
                if let Some(qdrant_client::qdrant::vectors_output::VectorsOptions::Vector(v)) = &vectors.vectors_options {
                    // Search for similar chunks (excluding same note)
                    if let Ok(results) = self.qdrant.search_points(
                        SearchPointsBuilder::new(&collection, v.data.clone(), 6)
                            .with_payload(true),
                    ).await {
                        for r in results.result {
                            let r_title = payload_str(&r.payload, "title", "").to_string();
                            if r_title == note.title { continue; }
                            similar_notes.push(SimilarNote {
                                title: r_title,
                                chunk: payload_str(&r.payload, "chunk", "").to_string(),
                                score: r.score,
                            });
                        }
                    }
                }
            }

            chunks.push(ChunkDetail {
                index: chunk_idx_val,
                text: chunk_text,
                similar_notes,
            });
        }

        chunks.sort_by_key(|c| c.index);

        Ok(NoteDetail {
            title: note.title,
            path: note_path.to_string(),
            raw_content,
            tags: note.tags,
            links: note.links,
            chunks,
        })
    }
}

fn build_file_tree(path: &Path, root: &Path) -> Result<FileTreeNode, String> {
    let name = path.file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("root")
        .to_string();

    if path.is_dir() {
        let mut children: Vec<FileTreeNode> = Vec::new();
        let entries = std::fs::read_dir(path).map_err(|e| e.to_string())?;

        for entry in entries {
            let entry = entry.map_err(|e| e.to_string())?;
            let entry_path = entry.path();
            let entry_name = entry_path.file_name()
                .and_then(|n| n.to_str())
                .unwrap_or("");

            // Skip hidden dirs and .trash
            if entry_name.starts_with('.') { continue; }

            if entry_path.is_dir() {
                if let Ok(child) = build_file_tree(&entry_path, root) {
                    children.push(child);
                }
            } else if entry_path.extension().map(|e| e == "md").unwrap_or(false) {
                children.push(FileTreeNode {
                    name: entry_name.to_string(),
                    path: entry_path.to_string_lossy().to_string(),
                    is_dir: false,
                    children: vec![],
                });
            }
        }

        // Sort: dirs first, then files, alphabetically
        children.sort_by(|a, b| {
            match (a.is_dir, b.is_dir) {
                (true, false) => std::cmp::Ordering::Less,
                (false, true) => std::cmp::Ordering::Greater,
                _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
            }
        });

        Ok(FileTreeNode { name, path: path.to_string_lossy().to_string(), is_dir: true, children })
    } else {
        Ok(FileTreeNode { name, path: path.to_string_lossy().to_string(), is_dir: false, children: vec![] })
    }
}

fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    let mut dot = 0.0f32;
    let mut norm_a = 0.0f32;
    let mut norm_b = 0.0f32;
    for i in 0..a.len().min(b.len()) {
        dot += a[i] * b[i];
        norm_a += a[i] * a[i];
        norm_b += b[i] * b[i];
    }
    let denom = norm_a.sqrt() * norm_b.sqrt();
    if denom == 0.0 { 0.0 } else { dot / denom }
}

fn dirs_config_path() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("vaultdb")
}
