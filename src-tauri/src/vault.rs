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

        // Scroll all points to build the graph
        let scroll_result = self
            .qdrant
            .scroll(
                qdrant_client::qdrant::ScrollPointsBuilder::new(&collection)
                    .with_payload(true)
                    .limit(10000),
            )
            .await
            .map_err(|e| format!("Scroll failed: {}", e))?;

        let mut nodes_map: HashMap<String, GraphNode> = HashMap::new();
        let mut edges: Vec<GraphEdge> = Vec::new();

        // Build nodes from unique titles
        for point in &scroll_result.result {
            let payload = &point.payload;
            let title = payload_str(payload, "title", "").to_string();
            let path = payload_str(payload, "path", "").to_string();
            let tags_str = payload_str(payload, "tags", "[]");
            let tags: Vec<String> = serde_json::from_str(tags_str).unwrap_or_default();
            let links_str = payload_str(payload, "links", "[]");
            let links: Vec<String> = serde_json::from_str(links_str).unwrap_or_default();

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
                edges.push(GraphEdge {
                    source: title.clone(),
                    target: link.clone(),
                    edge_type: "link".to_string(),
                    weight: 1.0,
                });
            }
        }

        let nodes: Vec<GraphNode> = nodes_map.into_values().collect();

        Ok(GraphData { nodes, edges })
    }
}

fn dirs_config_path() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("vaultdb")
}
