from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from groq import Groq
import PyPDF2
import docx
import os
import tempfile
from dotenv import load_dotenv

# OCR
from pdf2image import convert_from_path
import pytesseract

load_dotenv()

app = Flask(__name__)
CORS(app)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ---------------- HOME ----------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


# ---------------- OCR ----------------
def extract_text_with_ocr(pdf_path):
    text = ""
    images = convert_from_path(pdf_path, dpi=300)
    for i, image in enumerate(images):
        page_text = pytesseract.image_to_string(image, lang="eng")
        text += f"\n--- Page {i+1} ---\n{page_text}\n"
    return text


# ---------------- PDF ----------------
def extract_text_from_pdf(file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    text = ""
    with open(tmp_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            if page.extract_text():
                text += page.extract_text() + "\n"

    if len(text.strip()) < 200:
        text = extract_text_with_ocr(tmp_path)

    os.unlink(tmp_path)
    return text


# ---------------- DOCX ----------------
def extract_text_from_docx(file):
    doc = docx.Document(file)
    return "\n".join(p.text for p in doc.paragraphs)


# ---------------- TXT ----------------
def extract_text_from_txt(file):
    try:
        return file.read().decode("utf-8")
    except:
        file.seek(0)
        return file.read().decode("latin-1")


# ---------------- HELPER ----------------
def get_text_from_file():
    file = request.files.get("file")
    if not file:
        raise Exception("No file uploaded")

    name = file.filename.lower()

    if name.endswith(".pdf"):
        return extract_text_from_pdf(file)
    elif name.endswith(".docx"):
        return extract_text_from_docx(file)
    elif name.endswith(".txt"):
        return extract_text_from_txt(file)
    else:
        raise Exception("Unsupported file type")


# ---------------- SUMMARY ----------------
@app.route("/summarize", methods=["POST"])
def summarize():
    text = get_text_from_file()[:8000]
    chapter = request.form.get("chapter", "")
    word_count = int(request.form.get("word_count", 300))

    prompt = f"""
{text}

Create a {word_count}-word summary {"focusing on " + chapter if chapter else ""}.
"""

    client = Groq(api_key=GROQ_API_KEY)
    res = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        temperature=0.3,
        messages=[
            {"role": "system", "content": "You are an expert summarizer"},
            {"role": "user", "content": prompt},
        ],
    )

    summary = res.choices[0].message.content.strip()

    return jsonify(success=True, summary=summary)


# ---------------- NOTES ----------------
@app.route("/create-notes", methods=["POST"])
def create_notes():
    text = get_text_from_file()[:8000]
    chapter = request.form.get("chapter", "")

    prompt = f"""
{text}

Create structured topic-wise notes {"for " + chapter if chapter else ""}.
Use headings and bullet points.
"""

    client = Groq(api_key=GROQ_API_KEY)
    res = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        temperature=0.3,
        messages=[
            {"role": "system", "content": "You are an expert note maker"},
            {"role": "user", "content": prompt},
        ],
    )

    notes = res.choices[0].message.content.strip()

    return jsonify(success=True, notes=notes)


# ---------------- BOTH (FIX) ----------------
@app.route("/summarize-and-notes", methods=["POST"])
def summarize_and_notes():
    try:
        text = get_text_from_file()[:8000]
        chapter = request.form.get("chapter", "")
        word_count = int(request.form.get("word_count", 300))

        if not chapter:
            return jsonify(success=False, error="Chapter is required"), 400

        prompt = f"""
You are an academic assistant. You are given a textbook content.

TASK:
1. Search the text and extract ONLY the content for chapter "{chapter}".
2. If the chapter is not found, reply exactly: "Chapter not found in the document."
3. For the chapter found, provide:
   - The chapter title
   - A concise summary ({word_count} words)
   - Structured topic-wise notes using headings and bullet points

OUTPUT FORMAT:
---CHAPTER---
<chapter title or number>
---SUMMARY---
<summary here>
---NOTES---
<notes here>

Text:
{text}
"""

        client = Groq(api_key=GROQ_API_KEY)
        res = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are an expert academic assistant"},
                {"role": "user", "content": prompt},
            ],
        )

        content = res.choices[0].message.content.strip()

        chapter_title = ""
        summary = ""
        notes = ""

        if "Chapter not found in the document." in content:
            return jsonify(success=False, error="Chapter not found in the document"), 404

        if "---CHAPTER---" in content and "---SUMMARY---" in content and "---NOTES---" in content:
            chapter_title = content.split("---CHAPTER---")[1].split("---SUMMARY---")[0].strip()
            summary = content.split("---SUMMARY---")[1].split("---NOTES---")[0].strip()
            notes = content.split("---NOTES---")[1].strip()
        else:
            summary = content  # fallback

        return jsonify(
            success=True,
            chapter=chapter_title,
            summary=summary,
            notes=notes
        )

    except Exception as e:
        return jsonify(success=False, error=str(e)), 500



# ---------------- RUN ----------------
if __name__ == "__main__":
    print("📚 AI Document Assistant running on http://127.0.0.1:5002")
    app.run(host="0.0.0.0", port=5002, debug=True)
