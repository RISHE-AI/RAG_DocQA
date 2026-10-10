import os
import sys
import json
import time
import re
import pickle
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

# Ensure standard UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
import requests
import numpy as np
import faiss
from dotenv import load_dotenv

# Optional specialized parsers
try:
    import fitz  # PyMuPDF
    HAVE_PYMUPDF = True
except ImportError:
    HAVE_PYMUPDF = False

try:
    import PyPDF2
    HAVE_PYPDF2 = True
except ImportError:
    HAVE_PYPDF2 = False

try:
    from sentence_transformers import SentenceTransformer
    HAVE_ST = True
except ImportError:
    HAVE_ST = False

# ─── Environment & Paths ───
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')
load_dotenv(BASE_DIR / '.env.example')

UPLOAD_FOLDER = BASE_DIR / 'uploads'
UPLOAD_FOLDER.mkdir(exist_ok=True)

# ─── Flask App Configuration ───
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max file size
app.config['JSON_SORT_KEYS'] = False

# ─── RAG & Model Configuration ───
ALLOWED_EXTENSIONS = {'pdf', 'txt', 'md'}
EMBEDDING_MODEL_NAME = 'all-MiniLM-L6-v2'
EMBEDDING_DIM = 384
CHUNK_SIZE = 750       # Characters per chunk
CHUNK_OVERLAP = 150    # Characters overlap

GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
GROQ_MODELS_URL = 'https://api.groq.com/openai/v1/models'
GROQ_API_KEY = (os.getenv('GROQ_API_KEY') or '').strip()

# Recommended fallback model chain for Groq
CANDIDATE_MODELS = [
    os.getenv('GROQ_MODEL', '').strip(),
    'openai/gpt-oss-120b',
    'qwen/qwen3.8-27b',
    'openai/gpt-oss-20b',
    'llama-3.3-70b-versatile',
    'llama-3.1-8b-instant'
]
# Filter empty candidate model names
CANDIDATE_MODELS = [m for m in CANDIDATE_MODELS if m]

# ─── In-Memory Cache & State ───
_embedding_model = None
_cached_index = None
_cached_chunks_data = None
_cached_metadata = None
_discovered_groq_models = []

def get_embedding_model():
    """Lazily load the SentenceTransformer embedding model."""
    global _embedding_model
    if _embedding_model is None:
        if not HAVE_ST:
            raise RuntimeError("sentence-transformers package is not installed.")
        print(f"🧠 Loading embedding model: {EMBEDDING_MODEL_NAME}...")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print("✅ Embedding model ready.")
    return _embedding_model

def get_available_groq_models() -> List[str]:
    """Discover available chat models from the Groq API key."""
    global _discovered_groq_models
    if _discovered_groq_models:
        return _discovered_groq_models
    
    if not GROQ_API_KEY:
        return [m for m in CANDIDATE_MODELS if m]
        
    try:
        resp = requests.get(
            GROQ_MODELS_URL,
            headers={'Authorization': f'Bearer {GROQ_API_KEY}'},
            timeout=6
        )
        if resp.status_code == 200:
            data = resp.json().get('data', [])
            # Filter models to conversational chat models
            models = []
            for item in data:
                mid = item.get('id', '')
                if any(x in mid.lower() for x in ['whisper', 'guard', 'embedding', 'tts', 'stt']):
                    continue
                models.append(mid)
            if models:
                # Prioritize known high-quality models first
                priority = ['openai/gpt-oss-120b', 'qwen/qwen3.8-27b', 'openai/gpt-oss-20b']
                sorted_models = [m for m in priority if m in models] + [m for m in models if m not in priority]
                _discovered_groq_models = sorted_models
                return _discovered_groq_models
    except Exception as e:
        print(f"Notice: Failed to fetch Groq models dynamically: {e}")
        
    _discovered_groq_models = [m for m in CANDIDATE_MODELS if m]
    return _discovered_groq_models

def get_active_model(preferred_model: Optional[str] = None) -> str:
    """Resolve the best working model name."""
    available = get_available_groq_models()
    if preferred_model and preferred_model in available:
        return preferred_model
    if preferred_model and not available:
        return preferred_model
    if available:
        return available[0]
    return 'openai/gpt-oss-120b'

# ─── Document Parsing Utilities ───
def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def parse_pdf(filepath: Path) -> Tuple[List[Dict[str, Any]], int]:
    """
    Extract text per page from PDF using PyMuPDF (fast & accurate),
    falling back to PyPDF2 if needed.
    """
    pages_data = []
    
    # 1. Try PyMuPDF
    if HAVE_PYMUPDF:
        try:
            doc = fitz.open(str(filepath))
            total_pages = len(doc)
            for page_idx in range(total_pages):
                page = doc[page_idx]
                text = page.get_text() or ''
                pages_data.append({
                    'page_number': page_idx + 1,
                    'text': text.strip()
                })
            doc.close()
            if any(p['text'] for p in pages_data):
                return pages_data, total_pages
        except Exception as e:
            print(f"PyMuPDF warning: {e}. Falling back to PyPDF2...")

    # 2. Fallback to PyPDF2
    if HAVE_PYPDF2:
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            total_pages = len(reader.pages)
            for page_idx, page in enumerate(reader.pages):
                text = page.extract_text() or ''
                pages_data.append({
                    'page_number': page_idx + 1,
                    'text': text.strip()
                })
        return pages_data, total_pages

    raise RuntimeError("Neither PyMuPDF nor PyPDF2 is installed to parse PDF files.")

def parse_text_file(filepath: Path) -> Tuple[List[Dict[str, Any]], int]:
    """Parse plain text or markdown, chunking into logical pages of ~1500 chars."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        full_text = f.read()

    char_per_page = 1500
    pages_data = []
    total_len = len(full_text)
    
    if total_len == 0:
        return [{'page_number': 1, 'text': ''}], 1

    page_num = 1
    for start in range(0, total_len, char_per_page):
        chunk = full_text[start:start + char_per_page]
        pages_data.append({
            'page_number': page_num,
            'text': chunk.strip()
        })
        page_num += 1

    return pages_data, len(pages_data)

def split_into_sentences(text: str) -> List[str]:
    """Split text cleanly into sentences using regex boundary detection."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [s.strip() for s in sentences if s.strip()]

def create_semantic_chunks(pages_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Produce semantic chunks of ~CHUNK_SIZE with CHUNK_OVERLAP,
    maintaining strict page reference tracking.
    """
    chunks = []
    
    for page_info in pages_data:
        page_num = page_info['page_number']
        page_text = page_info['text']
        
        if not page_text:
            continue
            
        sentences = split_into_sentences(page_text)
        if not sentences:
            sentences = [page_text]
            
        current_chunk_sentences = []
        current_chunk_len = 0
        
        for sentence in sentences:
            sentence_len = len(sentence)
            
            if current_chunk_len + sentence_len > CHUNK_SIZE and current_chunk_sentences:
                chunk_text = ' '.join(current_chunk_sentences)
                chunks.append({
                    'id': len(chunks) + 1,
                    'text': chunk_text,
                    'pages': [page_num],
                    'preview': chunk_text[:120] + ('...' if len(chunk_text) > 120 else ''),
                    'char_count': len(chunk_text)
                })
                
                # Create overlap from end of current chunk
                overlap_sentences = []
                overlap_len = 0
                for s in reversed(current_chunk_sentences):
                    if overlap_len + len(s) > CHUNK_OVERLAP:
                        break
                    overlap_sentences.insert(0, s)
                    overlap_len += len(s) + 1
                    
                current_chunk_sentences = overlap_sentences
                current_chunk_len = overlap_len
                
            current_chunk_sentences.append(sentence)
            current_chunk_len += sentence_len + 1
            
        if current_chunk_sentences:
            chunk_text = ' '.join(current_chunk_sentences)
            chunks.append({
                'id': len(chunks) + 1,
                'text': chunk_text,
                'pages': [page_num],
                'preview': chunk_text[:120] + ('...' if len(chunk_text) > 120 else ''),
                'char_count': len(chunk_text)
            })

    return chunks

# ─── Vector Indexing & Storage ───
def build_and_save_index(chunks: List[Dict[str, Any]], filename: str, total_pages: int, file_size_bytes: int):
    """Generate normalized FAISS index and persist to disk and memory."""
    global _cached_index, _cached_chunks_data, _cached_metadata
    
    model = get_embedding_model()
    chunk_texts = [c['text'] for c in chunks]
    
    # Generate normalized embeddings for cosine similarity with Inner Product
    print(f"🔄 Encoding {len(chunk_texts)} chunks into vector embeddings...")
    embeddings = model.encode(chunk_texts, show_progress_bar=False, normalize_embeddings=True)
    embeddings = np.array(embeddings).astype('float32')
    
    # Initialize FAISS IndexFlatIP
    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    index.add(embeddings)
    
    # Metadata payload
    metadata = {
        'filename': filename,
        'uploaded_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_pages': total_pages,
        'total_chunks': len(chunks),
        'file_size': file_size_bytes,
        'embedding_dim': EMBEDDING_DIM,
        'embedding_model': EMBEDDING_MODEL_NAME
    }
    
    # Save paths
    vectors_path = UPLOAD_FOLDER / 'vectors.index'
    chunks_path = UPLOAD_FOLDER / 'chunks.pkl'
    meta_path = UPLOAD_FOLDER / 'metadata.json'
    
    faiss.write_index(index, str(vectors_path))
    with open(chunks_path, 'wb') as f:
        pickle.dump(chunks, f)
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
        
    # Update cache
    _cached_index = index
    _cached_chunks_data = chunks
    _cached_metadata = metadata
    
    print(f"✅ Indexed {len(chunks)} chunks across {total_pages} pages into FAISS vector space.")
    return metadata

def load_cached_index_data():
    """Load cached vector index and document metadata into memory."""
    global _cached_index, _cached_chunks_data, _cached_metadata
    
    if _cached_index is not None and _cached_chunks_data is not None and _cached_metadata is not None:
        return _cached_index, _cached_chunks_data, _cached_metadata
        
    vectors_path = UPLOAD_FOLDER / 'vectors.index'
    chunks_path = UPLOAD_FOLDER / 'chunks.pkl'
    meta_path = UPLOAD_FOLDER / 'metadata.json'
    
    if vectors_path.exists() and chunks_path.exists():
        try:
            index = faiss.read_index(str(vectors_path))
            with open(chunks_path, 'rb') as f:
                chunks = pickle.load(f)
            metadata = {}
            if meta_path.exists():
                with open(meta_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            else:
                metadata = {
                    'filename': 'Active Document',
                    'total_pages': max([max(c.get('pages', [1])) for c in chunks], default=1),
                    'total_chunks': len(chunks),
                    'embedding_model': EMBEDDING_MODEL_NAME
                }
            _cached_index = index
            _cached_chunks_data = chunks
            _cached_metadata = metadata
            return _cached_index, _cached_chunks_data, _cached_metadata
        except Exception as e:
            print(f"Error restoring cached index: {e}")
            
    return None, None, None

def clear_all_storage():
    """Clear the active vector database and stored documents."""
    global _cached_index, _cached_chunks_data, _cached_metadata
    
    _cached_index = None
    _cached_chunks_data = None
    _cached_metadata = None
    
    for f in UPLOAD_FOLDER.glob('*'):
        try:
            if f.is_file():
                f.unlink()
        except Exception as e:
            print(f"Error removing {f}: {e}")

# ─── Query Retrieval & LLM Generation ───
def retrieve_relevant_chunks(query: str, top_k: int = 5) -> Tuple[List[Dict[str, Any]], float]:
    """Retrieve top-K matching chunks using cosine similarity."""
    start_time = time.time()
    index, chunks, _ = load_cached_index_data()
    
    if index is None or not chunks:
        return [], 0.0
        
    model = get_embedding_model()
    query_vector = model.encode([query], normalize_embeddings=True).astype('float32')
    
    k = min(top_k, len(chunks))
    scores, indices = index.search(query_vector, k)
    
    retrieved = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(chunks):
            continue
        # Filter negative or irrelevantly low similarity
        if score < 0.12:
            continue
        chunk_item = chunks[idx].copy()
        chunk_item['similarity_score'] = round(float(score), 4)
        chunk_item['similarity_pct'] = round(float(score) * 100, 1)
        retrieved.append(chunk_item)
        
    retrieval_ms = (time.time() - start_time) * 1000
    return retrieved, round(retrieval_ms, 2)

def query_groq_llm(question: str, context: str, preferred_model: Optional[str] = None) -> Tuple[Optional[str], Optional[str], str]:
    """
    Call Groq API with automatic fallback across supported models.
    Returns (answer, error_msg, model_used).
    """
    if not GROQ_API_KEY:
        return None, "Groq API Key is not configured. Please add GROQ_API_KEY to your .env file.", ""

    system_prompt = (
        "You are an authoritative, highly professional AI Document Analyst & Intelligence Assistant. "
        "Your task is to provide comprehensive, clear, and rigorously grounded answers based SOLELY on the provided document excerpts.\n\n"
        "STRICT GROUNDING RULES:\n"
        "1. Base your answer ENTIRELY on the provided context excerpts. NEVER extrapolate, hallucinate, or bring in outside training data.\n"
        "2. If the excerpts do not contain sufficient evidence to answer the question, state: "
        "'Based on the uploaded document, there is insufficient information to answer this question accurately.' "
        "and concisely summarize what relevant details the document does mention.\n"
        "3. FORMATTING STANDARDS:\n"
        "   - Use clean, structured Markdown.\n"
        "   - Use bold (**term**) for key terminology, metrics, and definitions.\n"
        "   - Use bullet points or numbered lists for sequential steps, comparisons, or multi-item responses.\n"
        "   - If presenting comparisons, parameters, or specifications, render them in well-formatted Markdown tables.\n"
        "   - Use > blockquotes when quoting critical findings verbatim.\n"
        "4. CITATIONS:\n"
        "   - Whenever you state a key fact, definition, or metric, immediately cite the source page using the exact notation: **(Page X)** or **(Pages X, Y)**.\n"
        "5. Tone: Objective, polished, executive, and analytical."
    )

    user_message = f"DOCUMENT EXCERPTS:\n{context}\n\nUSER QUESTION: {question}\n\nProvide your comprehensive, well-structured answer with page citations:"

    # Candidate models to try in order
    selected_model = get_active_model(preferred_model)
    model_pool = [selected_model] + [m for m in get_available_groq_models() if m != selected_model]

    last_error = None
    for model_name in model_pool:
        try:
            payload = {
                'model': model_name,
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message}
                ],
                'temperature': 0.15,
                'max_tokens': 2500
            }

            resp = requests.post(
                GROQ_API_URL,
                headers={
                    'Authorization': f'Bearer {GROQ_API_KEY}',
                    'Content-Type': 'application/json'
                },
                json=payload,
                timeout=90
            )

            if resp.status_code == 200:
                data = resp.json()
                answer = data['choices'][0]['message']['content'].strip()
                return answer, None, model_name
            else:
                err_text = resp.text
                print(f"Model '{model_name}' failed with status {resp.status_code}: {err_text[:200]}")
                last_error = f"Groq error ({resp.status_code}): {err_text}"
                # If error is model not found or forbidden, continue to next candidate model
                if resp.status_code in [404, 400, 422]:
                    continue
                else:
                    # Break on unexpected server failure
                    break
        except requests.exceptions.Timeout:
            last_error = f"Request timed out while querying model '{model_name}'."
            continue
        except requests.exceptions.ConnectionError:
            last_error = "Connection error: Unable to reach Groq API servers."
            break
        except Exception as e:
            last_error = f"Unexpected error: {str(e)}"
            break

    return None, (last_error or "All Groq model requests failed."), ""

# ─── API Routes ───
@app.route('/')
def index():
    """Serve the modern web client."""
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    """Retrieve real-time application and vector store status."""
    _, chunks, metadata = load_cached_index_data()
    is_loaded = (chunks is not None and len(chunks) > 0)
    
    groq_ok = bool(GROQ_API_KEY)
    models = get_available_groq_models()
    active_model = get_active_model()
    
    return jsonify({
        'success': True,
        'loaded': is_loaded,
        'document': metadata or {},
        'groqConfigured': groq_ok,
        'activeModel': active_model,
        'availableModels': models,
        'embeddingModel': EMBEDDING_MODEL_NAME,
        'embeddingDim': EMBEDDING_DIM
    })

@app.route('/api/models', methods=['GET'])
def list_models():
    """List all available models on Groq."""
    models = get_available_groq_models()
    return jsonify({
        'success': True,
        'models': models,
        'activeModel': get_active_model()
    })

@app.route('/api/upload', methods=['POST'])
def handle_upload():
    """Handle document upload, text extraction, semantic chunking, and FAISS indexing."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file part in upload request.'}), 400
        
    file = request.files['file']
    if not file.filename or file.filename.strip() == '':
        return jsonify({'success': False, 'message': 'No file selected.'}), 400
        
    if not allowed_file(file.filename):
        allowed_str = ', '.join(f".{ext}" for ext in sorted(ALLOWED_EXTENSIONS))
        return jsonify({
            'success': False,
            'message': f'Unsupported file format. Please upload {allowed_str}.'
        }), 400

    filename = secure_filename(file.filename)
    filepath = UPLOAD_FOLDER / filename
    
    # Save uploaded file
    file.save(str(filepath))
    file_size = filepath.stat().st_size
    
    try:
        ext = filepath.suffix.lower()
        if ext == '.pdf':
            pages_data, total_pages = parse_pdf(filepath)
        elif ext in ['.txt', '.md']:
            pages_data, total_pages = parse_text_file(filepath)
        else:
            return jsonify({'success': False, 'message': f'Unsupported extension {ext}'}), 400

        if not pages_data or not any(p.get('text', '').strip() for p in pages_data):
            return jsonify({
                'success': False,
                'message': 'No readable text could be extracted. The document might be an image-only scan.'
            }), 400

        # Create semantic chunks
        chunks = create_semantic_chunks(pages_data)
        if not chunks:
            return jsonify({
                'success': False,
                'message': 'Semantic chunking produced 0 chunks.'
            }), 400

        # Vector Indexing
        metadata = build_and_save_index(chunks, filename, total_pages, file_size)

        return jsonify({
            'success': True,
            'message': f'Successfully parsed and indexed "{filename}" ({total_pages} pages, {len(chunks)} chunks).',
            'metadata': metadata
        })

    except Exception as e:
        print(f"Error during file processing: {str(e)}")
        return jsonify({'success': False, 'message': f'Processing error: {str(e)}'}), 500

@app.route('/api/ask', methods=['POST'])
def handle_ask():
    """Handle user query, retrieve relevant chunks, query Groq, and return citations."""
    data = request.get_json() or {}
    question = (data.get('question') or '').strip()
    preferred_model = data.get('model')

    if not question:
        return jsonify({'success': False, 'message': 'Please provide a question.'}), 400

    index, chunks, meta = load_cached_index_data()
    if index is None or not chunks:
        return jsonify({
            'success': False,
            'message': 'No document is currently indexed. Please upload a PDF, TXT, or MD document first.'
        }), 400

    start_total = time.time()

    # 1. Retrieve top matching chunks
    retrieved_chunks, retrieval_ms = retrieve_relevant_chunks(question, top_k=5)

    if not retrieved_chunks:
        return jsonify({
            'success': True,
            'answer': 'Based on the uploaded document, no relevant excerpts were found matching your query.',
            'sources': [],
            'chunks': [],
            'model': get_active_model(preferred_model),
            'metrics': {'retrieval_ms': retrieval_ms, 'generation_ms': 0, 'total_ms': round((time.time() - start_total) * 1000, 2)}
        })

    # 2. Build structured context
    context_parts = []
    source_pages = set()
    for item in retrieved_chunks:
        pg_str = ', '.join(str(p) for p in item.get('pages', [1]))
        source_pages.update(item.get('pages', [1]))
        context_parts.append(
            f"[Source: {meta.get('filename', 'Document')} | Page(s): {pg_str} | Similarity: {item.get('similarity_pct')}%]\n"
            f"{item.get('text')}"
        )
    context_str = '\n\n---\n\n'.join(context_parts)

    # 3. Query LLM
    gen_start = time.time()
    answer, error, model_used = query_groq_llm(question, context_str, preferred_model)
    generation_ms = round((time.time() - gen_start) * 1000, 2)
    total_ms = round((time.time() - start_total) * 1000, 2)

    if error:
        return jsonify({'success': False, 'message': error}), 500

    # Package inspected chunks for UI inspection drawer
    inspected_chunks = [{
        'id': c.get('id'),
        'pages': c.get('pages', [1]),
        'similarity_pct': c.get('similarity_pct'),
        'text': c.get('text'),
        'preview': c.get('preview')
    } for c in retrieved_chunks]

    return jsonify({
        'success': True,
        'answer': answer,
        'sources': sorted(list(source_pages)),
        'chunks': inspected_chunks,
        'model': model_used,
        'metrics': {
            'retrieval_ms': retrieval_ms,
            'generation_ms': generation_ms,
            'total_ms': total_ms
        }
    })

@app.route('/api/document/preview', methods=['GET'])
def get_document_preview():
    """Return an executive preview of the active document."""
    _, chunks, meta = load_cached_index_data()
    if not chunks or not meta:
        return jsonify({'success': False, 'message': 'No document loaded.'}), 404

    # Extract first 3 chunks as document intro
    intro_snippets = [c.get('text', '') for c in chunks[:3]]
    return jsonify({
        'success': True,
        'metadata': meta,
        'first_chunks': intro_snippets
    })

@app.route('/api/clear', methods=['POST'])
def handle_clear():
    """Clear the uploaded document and vector index."""
    try:
        clear_all_storage()
        return jsonify({'success': True, 'message': 'Database and document cache cleared successfully.'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Clear error: {str(e)}'}), 500

# ─── Entry Point ───
if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ['true', '1', 'yes']
    
    print("\n" + "=" * 60)
    print("🚀  RAG DocQA Studio — Enterprise Document Intelligence")
    print(f"📡  Server URL: http://localhost:{port}")
    print(f"⚙️   Debug Mode: {debug_mode}")
    print(f"🤖  Embedding Engine: {EMBEDDING_MODEL_NAME} (384 dims, FAISS)")
    if GROQ_API_KEY:
        print(f"🔑  Groq Key: Configured (Active Model: {get_active_model()})")
    else:
        print("⚠️   Groq Key: Missing! Set GROQ_API_KEY in .env")
    print("=" * 60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
