import os
from google import genai
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime

# 1. Load Environment Variables
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///notemind.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev_key")

db = SQLAlchemy(app)

# 2. Konfigurasi Gemini API (SDK Baru: google-genai)
try:
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    MODEL_NAME = "gemini-2.5-flash"
except Exception as e:
    print(f"Warning: API Key mungkin belum diset. Error: {e}")

# 3. Database Model
class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    ai_insight = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'ai_insight': self.ai_insight,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M')
        }

# Buat tabel database jika belum ada
with app.app_context():
    db.create_all()

# 4. Fungsi Helper AI
def generate_ai_response(prompt_type, text):
    """Mengirim request ke Gemini menggunakan SDK google-genai terbaru"""
    
    prompts = {
        "summarize": "Buatlah ringkasan singkat (bullet points) dari catatan ini:",
        "expand": "Kembangkan ide catatan ini menjadi paragraf yang lebih detail dan profesional:",
        "understand": "Jelaskan konsep dalam catatan ini seolah saya adalah pemula (ELI5):",
        "action_items": "Buat daftar tugas (To-Do List) konkret berdasarkan catatan ini:"
    }

    base_instruction = prompts.get(prompt_type, "Analisis catatan ini:")
    full_prompt = f"{base_instruction}\n\nIsi Catatan:\n{text}"

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=full_prompt
        )
        return response.text
    except Exception as e:
        print(f"Gemini Error: {e}")
        return f"Maaf, gagal menghubungi AI. Error: {str(e)}"

# 5. Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/notes', methods=['GET'])
def get_notes():
    notes = Note.query.order_by(Note.created_at.desc()).all()
    return jsonify([note.to_dict() for note in notes])

@app.route('/api/notes', methods=['POST'])
def add_note():
    data = request.json
    if not data.get('title') or not data.get('content'):
        return jsonify({'error': 'Judul dan konten wajib diisi'}), 400
        
    new_note = Note(title=data['title'], content=data['content'])
    db.session.add(new_note)
    db.session.commit()
    return jsonify(new_note.to_dict()), 201

@app.route('/api/process-ai', methods=['POST'])
def process_ai():
    data = request.json
    note_id = data.get('note_id')
    action = data.get('action')
    
    note = Note.query.get(note_id)
    if not note:
        return jsonify({"error": "Note not found"}), 404

    # Panggil AI
    result = generate_ai_response(action, note.content)
    
    # Simpan hasil ke DB
    note.ai_insight = result
    db.session.commit()

    return jsonify({"result": result})

if __name__ == '__main__':
    app.run(debug=True)