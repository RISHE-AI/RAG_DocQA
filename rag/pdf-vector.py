import faiss
import openai
import PyPDF2
import numpy as np
import pickle

# Set your OpenAI API key
openai.api_key = "sk-proj--sdfsf...."


def pdf_to_vectors(pdf_path):
    # Read PDF
    print(f"📄 Reading PDF: {pdf_path}")
    with open(pdf_path, 'rb') as f:
        pdf_reader = PyPDF2.PdfReader(f)
        total_pages = len(pdf_reader.pages)

        # Extract text from each page separately
        page_texts = []
        for page_num, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text()
            page_texts.append({
                'text': page_text,
                'page_number': page_num + 1
            })

        # Combine all text for chunking
        text = ''.join([p['text'] for p in page_texts])

    print(f"📊 Total pages: {total_pages}")
    print(f"📊 Total text length: {len(text):,} characters")
    print(f"📊 Average characters per page: {len(text) // total_pages:,}")

    # Create chunks with page tracking
    chunks = []
    chunk_metadata = []

    for i in range(0, len(text), 400):
        chunk_text = text[i:i + 500]
        chunks.append(chunk_text)

        # Estimate which page this chunk belongs to
        estimated_page = min((i // (len(text) // total_pages)) + 1, total_pages)
        chunk_metadata.append({
            'start_pos': i,
            'estimated_page': estimated_page
        })

    print(f"✂️  Created {len(chunks)} chunks")

    # Get embeddings from OpenAI
    print("🔄 Getting embeddings from OpenAI...")
    embeddings = []
    for i, chunk in enumerate(chunks):
        print(f"Processing {i + 1}/{len(chunks)}")
        response = openai.Embedding.create(input=chunk, model="text-embedding-ada-002")
        embeddings.append(response['data'][0]['embedding'])

    # Create FAISS index
    print("🗂️  Creating FAISS index...")
    embeddings = np.array(embeddings)
    index = faiss.IndexFlatIP(1536)  # OpenAI embeddings are 1536 dimensions
    index.add(embeddings.astype('float32'))

    # Save to files
    print("💾 Saving to files...")
    faiss.write_index(index, "vectors.index")
    with open("chunks.pkl", "wb") as f:
        pickle.dump({
            'chunks': chunks,
            'metadata': chunk_metadata,
            'total_pages': total_pages
        }, f)

    print("✅ Vector database created successfully!")
    print(f"📁 Files saved: vectors.index, chunks.pkl")
    print(f"📊 Vector shape: {embeddings.shape}")
    print(f"🔢 Sample vector (first 5 dims): {embeddings[0][:5]}")

    return embeddings, chunks


# Usage
if __name__ == "__main__":
    # Convert PDF to vectors (run this once)
    pdf_file = "50 Gen AI Product Ideas E2E.pdf"  # Change to your PDF file
    embeddings, chunks = pdf_to_vectors(pdf_file)

    print("\n🎉 Setup complete! Now you can run 'ask_questions.py' to chat with your PDF!")