import os
from google import genai
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime

# 1. Load Environment Variables
load_dotenv()

app = Flask(__name__)
# Pastikan menggunakan absolute path atau lokasi yang valid
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///notemind.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_key")

db = SQLAlchemy(app)

# 2. Konfigurasi Gemini API
try:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    MODEL_NAME = "gemini-2.5-flash"
except Exception as e:
    print(f"Warning: API Key mungkin belum diset. Error: {e}")
    client = None

# 3. Database Model
class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    ai_insight = db.Column(db.Text, nullable=True)
    # [BARU] Kolom untuk status Pin
    is_pinned = db.Column(db.Boolean, default=False) 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'ai_insight': self.ai_insight,
            # [BARU] Sertakan status pin di JSON
            'is_pinned': self.is_pinned,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M')
        }

# Buat tabel database jika belum ada
with app.app_context():
    db.create_all()

# 4. Fungsi Helper AI
def generate_ai_response(prompt_type, text):
    if not client:
        return "API Key Error"

    prompts = {
        "summarize": "Buatlah ringkasan singkat (bullet points) dari catatan ini:",
        "expand": "Kembangkan ide catatan ini menjadi paragraf yang lebih detail dan profesional:",
        "understand": "Jelaskan konsep dalam catatan ini seolah saya adalah pemula (ELI5):",
        "action_items": "Buat daftar tugas (To-Do List) konkret berdasarkan catatan ini:",
        "auto_title": "Buatlah JUDUL yang sangat pendek (maksimal 6 kata), menarik, dan relevan untuk isi teks berikut. HANYA berikan teks judulnya saja tanpa tanda kutip atau awalan lain:"
    }

    base_instruction = prompts.get(prompt_type, "Analisis catatan ini:")
    
    if prompt_type == "auto_title":
        full_prompt = f"{base_instruction}\n\n{text}"
    else:
        full_prompt = f"{base_instruction}\n\nIsi Catatan:\n{text}"

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=full_prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini Error: {e}")
        return f"Gagal memproses AI: {str(e)}"

# 5. Routes

@app.route('/')
def index():
    return render_template('index.html')

# --- READ (Ambil semua catatan) ---
@app.route('/api/notes', methods=['GET'])
def get_notes():
    # [BARU] Urutkan berdasarkan Pin (True di atas) lalu Waktu (Terbaru di atas)
    notes = Note.query.order_by(Note.is_pinned.desc(), Note.created_at.desc()).all()
    return jsonify([note.to_dict() for note in notes])

# --- CREATE (Tambah Catatan Baru) ---
@app.route('/api/notes', methods=['POST'])
def add_note():
    data = request.json
    content = data.get('content')
    title = data.get('title')

    if not content:
        return jsonify({'error': 'Konten wajib diisi'}), 400
    
    if not title:
        try:
            generated_title = generate_ai_response("auto_title", content)
            if "Gagal" in generated_title or not generated_title:
                title = "Catatan Tanpa Judul"
            else:
                title = generated_title
        except:
            title = "Catatan Tanpa Judul"
        
    new_note = Note(title=title, content=content)
    db.session.add(new_note)
    db.session.commit()
    return jsonify(new_note.to_dict()), 201

# --- UPDATE (Edit Catatan & Toggle Pin) ---
@app.route('/api/notes/<int:id>', methods=['PUT'])
def update_note(id):
    note = Note.query.get(id)
    if not note:
        return jsonify({'error': 'Catatan tidak ditemukan'}), 404
    
    data = request.json
    
    if 'title' in data:
        note.title = data['title']
    if 'content' in data:
        note.content = data['content']
    
    # [BARU] Update status Pin jika dikirim dari frontend
    if 'is_pinned' in data:
        note.is_pinned = bool(data['is_pinned'])
    
    db.session.commit()
    return jsonify(note.to_dict())

# --- DELETE (Hapus Catatan) ---
@app.route('/api/notes/<int:id>', methods=['DELETE'])
def delete_note(id):
    note = Note.query.get(id)
    if not note:
        return jsonify({'error': 'Catatan tidak ditemukan'}), 404
    
    db.session.delete(note)
    db.session.commit()
    return jsonify({'message': 'Catatan berhasil dihapus'})

# --- AI Title Generator ---
@app.route('/api/generate-title', methods=['POST'])
def generate_title_only():
    data = request.json
    content = data.get('content')
    if not content:
        return jsonify({'error': 'Konten kosong'}), 400
        
    title = generate_ai_response("auto_title", content)
    return jsonify({'title': title})

# --- AI Processing ---
@app.route('/api/process-ai', methods=['POST'])
def process_ai():
    data = request.json
    note_id = data.get('note_id')
    action = data.get('action')
    
    note = Note.query.get(note_id)
    if not note:
        return jsonify({"error": "Note not found"}), 404

    result = generate_ai_response(action, note.content)
    
    note.ai_insight = result
    db.session.commit()

    return jsonify({"result": result})

if __name__ == '__main__':
    app.run(debug=True)